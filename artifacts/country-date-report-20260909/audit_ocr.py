"""Read-only photo OCR for manufacturing-country evidence; resume from JSONL."""
import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np
from PIL import Image, ImageOps

ENGINE = None


def init_worker():
    global ENGINE
    from paddleocr import PaddleOCR
    models = Path("C:/Users/ujkio/.paddlex/official_models")
    ENGINE = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_detection_model_dir=str(models / "PP-OCRv5_mobile_det"),
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        text_recognition_model_dir=str(models / "korean_PP-OCRv5_mobile_rec"),
        use_doc_orientation_classify=False, use_doc_unwarping=False,
        use_textline_orientation=False, device="cpu", cpu_threads=1,
        enable_mkldnn=True, text_recognition_batch_size=8,
        text_det_limit_type="max", text_det_limit_side_len=1600,
        text_det_thresh=0.25, text_det_box_thresh=0.4,
        text_det_unclip_ratio=1.8, text_rec_score_thresh=0.15,
    )


def recognize(path_string):
    path = Path(path_string)
    try:
        with Image.open(path) as source:
            rgb = ImageOps.exif_transpose(source).convert("RGB")
            rgb.thumbnail((1600, 1600))
            array = np.asarray(rgb)[:, :, ::-1].copy()
        payload = list(ENGINE.predict(array))[0].json
        data = payload.get("res", payload)
        lines = [
            {"text": text, "score": round(float(score), 4), "box": box}
            for text, score, box in zip(
                data.get("rec_texts", []), data.get("rec_scores", []),
                data.get("rec_boxes", []))
        ]
        return {"image_id": path.stem, "filename": path.name,
                "ocr_size": list(rgb.size), "lines": lines}
    except Exception as exc:
        return {"image_id": path.stem, "filename": path.name,
                "lines": [], "error": str(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3352)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    root = Path("C:/ITDA_OCR_CODE/상품사진입니다")
    output = Path(__file__).parent / "ocr_evidence.jsonl"
    done = {json.loads(line)["image_id"] for line in
            output.read_text(encoding="utf-8").splitlines()} if output.exists() else set()
    files = sorted(p for p in root.iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    assert len(files) == 3352
    pending = [p for p in files[:args.limit] if p.stem not in done]
    start = time.monotonic()
    with output.open("a", encoding="utf-8") as stream:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as pool:
            futures = [pool.submit(recognize, str(path)) for path in pending]
            for count, future in enumerate(as_completed(futures), 1):
                stream.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
                stream.flush()
                if count % 25 == 0 or count == len(pending):
                    print(f"OCR {len(done)+count}/{len(done)+len(pending)}; "
                          f"elapsed {time.monotonic()-start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
