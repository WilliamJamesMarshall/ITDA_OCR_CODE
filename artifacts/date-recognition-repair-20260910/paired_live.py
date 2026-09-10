"""Fresh paired OCR, alternating order, with hash-verified fixed inputs."""
import hashlib
import json
from pathlib import Path
import sys
import time
from dataclasses import asdict

START = time.perf_counter()
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import pipeline
from src import date_extraction as current
from evaluate import load, save


class RecordingBackend(pipeline.PaddleOCRBackend):
    def recognize(self, image, *, detector, variant):
        lines = super().recognize(image, detector=detector, variant=variant)
        self.events.append(dict(detector=detector, variant=variant, lines=[asdict(x) for x in lines]))
        return lines


def main():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))["included"]
    comparison = json.loads((OUT / "comparison.json").read_text(encoding="utf-8"))
    targets = {r["historical_id"] for r in comparison["details"] if r["before"] != r["expected"] and r["after"] == r["expected"]}
    targets.update(("000014", "000315"))
    selected = [r for r in manifest if r["historical_id"] in targets]
    for i in range(24):
        row = manifest[i * len(manifest) // 24]
        if row not in selected and len(selected) < 24:
            selected.append(row)
    code_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("src/date_extraction.py", "src/pipeline.py")}
    save("live_manifest.json", dict(scope="Targeted repairs plus evenly spaced controls; development validation, not independent accuracy",
                                    code_sha256=code_hashes,
                                    images=[{k: r[k] for k in ("historical_id", "current_id", "path", "sha256", "expected")} for r in selected]))
    for row in selected:
        assert hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"]
    before = load("paired_starting_policy", OUT / "starting_source/date_extraction.py")
    config = pipeline.PipelineConfig(progress_every=0)
    init = time.perf_counter()
    backend = RecordingBackend(config)
    backend._recovery_model()  # Exclude lazy model construction from per-policy timing.
    init_seconds = time.perf_counter() - init
    details = []
    try:
        for index, row in enumerate(selected):
            result = {k: row[k] for k in ("historical_id", "current_id", "expected", "sha256", "path")}
            for key, module in ((("before", before), ("after", current)) if index % 2 == 0 else (("after", current), ("before", before))):
                assert hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"]
                pipeline.select_date = module.select_date
                backend.events = []
                tick = time.perf_counter()
                pred = pipeline.predict_image(Path(row["path"]), backend, config)
                elapsed = time.perf_counter() - tick
                assert hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"]
                result[key] = dict(prediction=pred.final_date or "NONE", seconds=elapsed,
                                   correct=(pred.final_date or "NONE") == row["expected"], passes=pred.passes,
                                   reason=pred.selection.reason, events=backend.events)
            details.append(result)
            save("live_progress.json", details)
            print(json.dumps(dict(completed=len(details), total=len(selected), id=row["historical_id"],
                                  expected=row["expected"], before=result["before"]["prediction"], after=result["after"]["prediction"],
                                  before_seconds=result["before"]["seconds"], after_seconds=result["after"]["seconds"])), flush=True)
    finally:
        pipeline.select_date = current.select_date
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in code_hashes.items())
    summary = {key: dict(correct=sum(r[key]["correct"] for r in details),
                         ocr_calls=sum(len(r[key]["passes"]) for r in details),
                         prediction_seconds=sum(r[key]["seconds"] for r in details)) for key in ("before", "after")}
    save("live_result.json", dict(summary=summary, count=len(details), backend_init_seconds=init_seconds,
                                  scope="Paired development sample; fresh OCR; inference timers exclude imports/model construction. Not 500-image benchmark.",
                                  script_start_through_comparison_seconds=time.perf_counter() - START, details=details))
    print(summary, flush=True)


if __name__ == "__main__":
    main()
