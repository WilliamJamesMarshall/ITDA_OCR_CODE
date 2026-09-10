"""Validate the final month/year addition and replay the previous live traces."""
import hashlib
import json
from pathlib import Path
import time
from paired_live import RecordingBackend, ROOT, OUT, pipeline, current, save


def main():
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("src/date_extraction.py", "src/pipeline.py")}
    previous = json.loads((OUT / "live_result.json").read_text(encoding="utf-8"))
    verified, changed = [], []
    for row in previous["details"]:
        lines, count = [], 0
        for event in row["after"]["events"]:
            lines.extend(current.OCRLine(**line) for line in event["lines"])
            count += 1
            selection = current.select_date(lines)
            if selection.stop_ocr:
                break
        if not selection.stop_ocr:
            selection = current.select_date(lines, final=True)
        if (selection.final_date or "NONE") != row["after"]["prediction"] or count != len(row["after"]["passes"]):
            changed.append(dict(historical_id=row["historical_id"], prediction=selection.final_date or "NONE", passes=count))
        verified.append(row["historical_id"])
    save("final_trace_check.json", dict(source_sha256=hashes, replayed=verified, changed=changed,
                                       scope="Replay of actual OCR traces, not a new timing measurement"))
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))["included"]
    comparison = json.loads((OUT / "comparison.json").read_text(encoding="utf-8"))["details"]
    targets = {r["historical_id"] for r in comparison if r["expected"].endswith("-NONE")
               and r["before"] != r["expected"] and r["after"] == r["expected"]}
    targets.update(r["historical_id"] for r in changed)
    rows = [r for r in manifest if r["historical_id"] in targets]
    started = time.perf_counter()
    config = pipeline.PipelineConfig(progress_every=0)
    backend = RecordingBackend(config)
    details = []
    for row in rows:
        path = Path(row["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        backend.events = []
        tick = time.perf_counter()
        prediction = pipeline.predict_image(path, backend, config)
        record = dict(historical_id=row["historical_id"], current_id=row["current_id"], expected=row["expected"],
                      prediction=prediction.final_date or "NONE", seconds=time.perf_counter() - tick,
                      passes=prediction.passes, path=str(path), sha256=row["sha256"])
        print(json.dumps(record, ensure_ascii=False), flush=True)
        record["events"] = backend.events
        details.append(record)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    save("partial_release_live_result.json", dict(source_sha256=hashes, count=len(details),
                                          correct=sum(r["expected"] == r["prediction"] for r in details),
                                          model_init_and_inference_seconds=time.perf_counter() - started, details=details,
                                          scope="Targeted five partial dates. Not a random accuracy or 500-image timing test."))


if __name__ == "__main__":
    main()
