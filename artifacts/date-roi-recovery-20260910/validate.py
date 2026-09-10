"""Frozen-input ROI audit and alternating paired, actual OCR validation."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import pipeline
from src.date_extraction import OCRLine, select_date


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline():
    spec = importlib.util.spec_from_file_location("src.roi_baseline", OUT / "starting_source/pipeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def audit(old):
    prior = ROOT / "artifacts/date-recognition-repair-20260910"
    manifest = json.loads((prior / "manifest.json").read_text(encoding="utf-8"))["included"]
    results = {r["historical_id"]: r for r in json.loads((prior / "comparison.json").read_text(encoding="utf-8"))["details"]}
    rows = []
    for row in manifest:
        assert digest(row["path"]) == row["sha256"], row["path"]
        lines = [OCRLine(**v) for v in row["evidence"]["events"][0]["lines"]]
        before, after = old._date_fragment_lines(lines), pipeline._date_fragment_lines(lines)
        rows.append(dict(**{k: row[k] for k in ("historical_id", "current_id", "expected", "path", "sha256")},
                         before=[asdict(x) for x in before], after=[asdict(x) for x in after],
                         reachable=not select_date(lines).stop_ocr, changed=before != after,
                         cached_correct=results[row["historical_id"]]["after"] == row["expected"]))
    save("audit.json", rows)
    print(json.dumps(dict(total=len(rows), reachable_changed=sum(r["reachable"] and r["changed"] for r in rows),
                          changed_correct=sum(r["reachable"] and r["changed"] and r["cached_correct"] for r in rows))), flush=True)
    return rows


class RecordingBackend(pipeline.PaddleOCRBackend):
    def recognize(self, image, *, detector, variant):
        lines = super().recognize(image, detector=detector, variant=variant)
        self.events.append(dict(detector=detector, variant=variant, lines=[asdict(x) for x in lines]))
        return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--all-changed", action="store_true")
    parser.add_argument("--prefix", default="pilot")
    args = parser.parse_args()
    old = baseline()
    rows = audit(old)
    if not args.live:
        for row in rows:
            if row["reachable"] and row["changed"]:
                print(row["historical_id"], row["cached_correct"], [v["text"] for v in row["before"]], "->", [v["text"] for v in row["after"]])
        return
    changed = [r for r in rows if r["reachable"] and r["changed"]]
    if args.all_changed:
        selected = changed
    else:
        selected = []
        for correct in (False, True):
            group = [r for r in changed if r["cached_correct"] == correct]
            selected.extend(group[i * len(group) // min(10, len(group))] for i in range(min(10, len(group))))
        for row in changed:
            if row["historical_id"] in {"003654", "000198"} and row not in selected:
                selected.append(row)
    # Unchanged/early-exit controls, selected before fresh inference outcomes.
    controls = [r for r in rows if not r["changed"] or not r["reachable"]]
    selected += [controls[i * len(controls) // 6] for i in range(6)]
    files = ("src/pipeline.py", "src/date_extraction.py", "artifacts/date-roi-recovery-20260910/starting_source/pipeline.py")
    hashes = {f: digest(ROOT / f) for f in files}
    save(args.prefix + "_manifest.json", dict(scope="Development ROI validation, not independent accuracy or 500-image speed", code_sha256=hashes, images=selected))
    config = pipeline.PipelineConfig(progress_every=0)
    tick = time.perf_counter()
    backend = RecordingBackend(config)
    backend._recovery_model()
    init = time.perf_counter() - tick
    details = []
    for index, row in enumerate(selected):
        record = {k: row[k] for k in ("historical_id", "current_id", "expected", "path", "sha256")}
        policies = [("before", old), ("after", pipeline)]
        if index % 2:
            policies.reverse()
        for name, module in policies:
            assert digest(row["path"]) == row["sha256"]
            backend.events = []
            tick = time.perf_counter()
            prediction = module.predict_image(Path(row["path"]), backend, config)
            elapsed = time.perf_counter() - tick
            assert digest(row["path"]) == row["sha256"]
            record[name] = dict(prediction=prediction.final_date or "NONE", correct=(prediction.final_date or "NONE") == row["expected"],
                                seconds=elapsed, passes=prediction.passes, reason=prediction.selection.reason, events=backend.events)
        details.append(record)
        save(args.prefix + "_progress.json", details)
        print(json.dumps(dict(completed=len(details), total=len(selected), id=row["historical_id"], expected=row["expected"],
                              before=record["before"]["prediction"], after=record["after"]["prediction"])), flush=True)
    assert all(digest(ROOT / f) == h for f, h in hashes.items())
    summary = {name: dict(correct=sum(r[name]["correct"] for r in details), ocr_calls=sum(len(r[name]["passes"]) for r in details),
                          prediction_seconds=sum(r[name]["seconds"] for r in details)) for name in ("before", "after")}
    summary.update(gains=[r["historical_id"] for r in details if not r["before"]["correct"] and r["after"]["correct"]],
                   losses=[r["historical_id"] for r in details if r["before"]["correct"] and not r["after"]["correct"]])
    save(args.prefix + "_result.json", dict(summary=summary, backend_init_seconds=init, code_sha256=hashes, details=details))
    print(summary, flush=True)


if __name__ == "__main__":
    main()
