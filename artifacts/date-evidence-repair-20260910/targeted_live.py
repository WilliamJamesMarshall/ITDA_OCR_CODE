"""Fresh OCR of replay gains: intentionally targeted, not accuracy estimation."""
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
from src.pipeline import PaddleOCRBackend, PipelineConfig, predict_image

PREFIX = "targeted_live_v2"


class RecordingBackend(PaddleOCRBackend):
    def recognize(self, image, *, detector, variant):
        lines = super().recognize(image, detector=detector, variant=variant)
        self.events.append(dict(detector=detector, variant=variant, lines=[asdict(line) for line in lines]))
        return lines


def main():
    audit = json.loads((OUT / "review_69.json").read_text(encoding="utf-8"))
    rows = [r for r in audit if r["recovered"]]
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in ("src/date_extraction.py", "src/pipeline.py")}
    # Another task renumbered images after the audit. Resolve identity by bytes,
    # never by the now-reused historical filename. Do not change that dataset.
    current_paths = {hashlib.sha256(path.read_bytes()).hexdigest(): path
                     for path in (ROOT / "추가수집데이터").glob("*.jpg")}
    for row in rows:
        original = Path(row["path"])
        if original.exists() and hashlib.sha256(original.read_bytes()).hexdigest() == row["sha256"]:
            row["resolved_path"] = original
        else:
            row["resolved_path"] = current_paths[row["sha256"]]
    config = PipelineConfig(progress_every=0)
    backend = RecordingBackend(config)
    results = []
    for row in rows:
        begin = time.perf_counter()
        path = row["resolved_path"]
        backend.events = []
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        pred = predict_image(path, backend, config)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        result = dict(id=row["id"], expected=row["expected"], after=pred.final_date or "NONE",
                      current_image_id=path.stem, path=str(path), image_sha256=row["sha256"],
                      passes=pred.passes, seconds=time.perf_counter() - begin,
                      reason=pred.selection.reason, order_resolved=pred.selection.order_resolved,
                      digits_confident=pred.selection.digits_confident)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        result["events"] = backend.events
        (OUT / f"{PREFIX}_progress.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    report = dict(measurement="15 replay improvements deliberately selected: fresh OCR reproduction, NOT independent accuracy",
                  source_sha256=hashes, images=len(results), correct=sum(r["expected"] == r["after"] for r in results),
                  script_start_through_ocr_seconds=time.perf_counter() - START, details=results)
    (OUT / f"{PREFIX}_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
