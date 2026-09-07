import argparse
import json
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR


DATE_LIKE = re.compile(
    r"(?:20[2-3]\d|2[4-9])(?:[\s./,:-]*\d){4}|"
    r"(?:EXP|E\.?DATE|BEST\s*BEFORE|BB|\uae4\uc9c0)",
    re.IGNORECASE,
)

_ENGINE = None


def init_worker():
    global _ENGINE
    _ENGINE = RapidOCR(
        intra_op_num_threads=1,
        inter_op_num_threads=1,
        det_limit_side_len=1280,
        max_side_len=3000,
        det_box_thresh=0.3,
        text_score=0.3,
    )


def ocr(image, variant):
    results, _ = _ENGINE(image)
    lines = []
    for box, text, score in results or []:
        lines.append(
            {
                "box": box,
                "text": text,
                "score": round(float(score), 4),
                "variant": variant,
            }
        )
    return lines


def has_date_like(lines):
    return any(DATE_LIKE.search(line["text"]) for line in lines)


def process_image(path_string):
    path = Path(path_string)
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((2600, 2600))
        rgb = np.asarray(image)

    passes = [{"variant": "high_res", "lines": ocr(rgb, "high_res")}]
    if not has_date_like(passes[0]["lines"]):
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        enhanced = cv2.cvtColor(clahe, cv2.COLOR_GRAY2RGB)
        passes.append({"variant": "clahe", "lines": ocr(enhanced, "clahe")})

    if not any(has_date_like(item["lines"]) for item in passes):
        for angle, rotated in (
            ("rot90", cv2.rotate(rgb, cv2.ROTATE_90_CLOCKWISE)),
            ("rot270", cv2.rotate(rgb, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ):
            lines = ocr(rotated, angle)
            passes.append({"variant": angle, "lines": lines})
            if has_date_like(lines):
                break

    return {"image_id": path.stem, "passes": passes}


def baseline_ids_without_date(path):
    missing = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(raw_line)
        if not has_date_like(row.get("lines", [])):
            missing.add(row["image_id"])
    return missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("baseline_jsonl", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    target_ids = baseline_ids_without_date(args.baseline_jsonl)
    files_by_id = {path.stem: path for path in args.input_dir.iterdir() if path.is_file()}
    missing_files = sorted(target_ids - files_by_id.keys())
    if missing_files:
        raise FileNotFoundError(f"Missing input images: {missing_files[:5]}")

    paths = [files_by_id[image_id] for image_id in sorted(target_ids)]
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as pool:
        futures = {pool.submit(process_image, str(path)): path for path in paths}
        for completed, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if completed % 20 == 0 or completed == len(paths):
                print(f"Processed {completed}/{len(paths)}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        for row in sorted(rows, key=lambda item: item["image_id"]):
            output_file.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
