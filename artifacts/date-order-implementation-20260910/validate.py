"""Policy validation: fixed evidence comparison or bounded fresh OCR smoke run.

Neither cached evidence nor the smoke sample is a 500-image speed benchmark.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import types

STARTED = time.perf_counter()
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import date_extraction as current


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def records(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def evidence_sets():
    base = ROOT / "artifacts/date-policy-integration-20260910"
    extra = read(ROOT / "artifacts/validation-rebaseline-20260910/ground_truth.json")
    existing = read(base / "existing_labels.json")["rows"]
    return [
        ("additional386", records(base / "release_386_cache/predictions.jsonl"), {r["image_id"]: r["truth"] for r in extra}, ROOT / "추가수집데이터"),
        ("existing352", records(base / "release_existing_cache/predictions.jsonl"), {r["image_id"]: r["truth"] for r in existing if r["status"] == "manual"}, ROOT / "상품사진입니다"),
    ]


def replay():
    old = types.ModuleType("policy_baseline")
    sys.modules[old.__name__] = old
    baseline_source = subprocess.check_output(["git", "show", "HEAD:src/date_extraction.py"], cwd=ROOT).decode("utf-8")
    exec(compile(baseline_source, "git:HEAD:src/date_extraction.py", "exec"), old.__dict__)
    reports = {}
    for name, rows, truth, _ in evidence_sets():
        details = []
        counts = Counter()
        timings = Counter()
        for row in rows:
            selections = {}
            for key, module in (("before", old), ("after", current)):
                lines = [module.OCRLine(**line) for event in row["events"] for line in event["lines"]]
                begin = time.perf_counter()
                selected = module.select_date(lines, final=True)
                timings[key] += time.perf_counter() - begin
                selections[key] = selected
            if row["image_id"] not in truth:
                continue
            expected = truth[row["image_id"]]
            before = selections["before"].final_date or "NONE"
            after = selections["after"].final_date or "NONE"
            counts["total"] += 1
            counts["before_correct"] += before == expected and not row["error"]
            counts["after_correct"] += after == expected and not row["error"]
            counts["gained"] += before != expected and after == expected and not row["error"]
            counts["lost"] += before == expected and after != expected and not row["error"]
            fallback = selections["after"].reason == "fallback_dmy"
            counts["fallback"] += fallback
            counts["fallback_wrong"] += fallback and after != expected
            details.append({"id": row["image_id"], "expected": expected, "before": before, "after": after,
                            "reason": selections["after"].reason,
                            "order_reason": selections["after"].candidates[0].order_reason if selections["after"].candidates else None})
        reports[name] = {"counts": counts, "parser_seconds_not_ocr": timings, "details": details}
        print(name, dict(counts), flush=True)
    save("fixed_evidence.json", {"measurement": "All previously recorded OCR evidence; NOT new OCR accuracy or E2E runtime",
                                  "baseline_sha256": hashlib.sha256(baseline_source.encode()).hexdigest(),
                                  "current_sha256": hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(), "sets": reports})


def live(limit):
    from src import pipeline
    config = pipeline.PipelineConfig(progress_every=0)
    # Evenly spaced, predetermined records; no selection by policy outcome.
    chosen = []
    for name, rows, truth, image_root in evidence_sets():
        eligible = [row for row in rows if row["image_id"] in truth]
        count = min(limit // 2, len(eligible))
        files = {p.stem: p for p in pipeline.discover_images(image_root)}
        for index in range(count):
            row = eligible[index * len(eligible) // count]
            chosen.append((name, files[row["image_id"]], truth[row["image_id"]]))
    hashes = {str(ROOT / name): hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in ("src/date_extraction.py", "src/pipeline.py")}
    save("live_manifest.json", {"sampling": "evenly spaced per source, selected before inference", "code_sha256": hashes,
                                "images": [{"set": name, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "expected": truth} for name, path, truth in chosen], "config": asdict(config)})
    backend = pipeline.PaddleOCRBackend(config)
    details = []
    for name, path, truth in chosen:
        begin = time.perf_counter()
        try:
            pred = pipeline.predict_image(path, backend, config)
            fields = pipeline.submission_fields(pred.final_date)
            record = {"set": name, "id": path.stem, "expected": truth, "after": fields["final_date"],
                      "reason": pred.selection.reason, "passes": pred.passes, "seconds": time.perf_counter() - begin,
                      "correct": fields["final_date"] == truth, "error": None}
        except Exception as exc:
            record = {"set": name, "id": path.stem, "expected": truth, "after": "NONE", "correct": False, "error": repr(exc)}
        details.append(record)
        save("live_progress.json", details)
        print(json.dumps({"completed": len(details), "total": len(chosen), **record}, ensure_ascii=False), flush=True)
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in hashes.items()), "Code changed during run"
    save("live_result.json", {"measurement": "Fresh OCR smoke sample on local Windows; NOT a 500-image official benchmark",
                              "script_start_through_ocr_seconds": time.perf_counter() - STARTED,
                              "images": len(details), "correct": sum(r["correct"] for r in details), "details": details})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("replay", "live"))
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.output_dir:
        OUT = args.output_dir.resolve()
        OUT.mkdir(parents=True, exist_ok=True)
    replay() if args.mode == "replay" else live(args.limit)
