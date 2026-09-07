import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR

from label_from_rapidocr import extract_candidates


_ENGINE = None


def init_worker():
    global _ENGINE
    _ENGINE = RapidOCR(
        intra_op_num_threads=1,
        inter_op_num_threads=1,
        det_limit_side_len=960,
        max_side_len=3000,
        det_box_thresh=0.3,
        text_score=0.3,
    )


def ocr(image, variant):
    results, _ = _ENGINE(image)
    return [
        {
            "box": box,
            "text": text,
            "score": round(float(score), 4),
            "variant": variant,
        }
        for box, text, score in results or []
    ]


def process_image(
    path_string,
    single_pass=False,
    skip_high_res=False,
    skip_clahe=False,
    tiles_only=False,
    binary_tiles_only=False,
):
    path = Path(path_string)
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((2200, 2200))
        rgb = np.asarray(image)

    passes = []
    if tiles_only or binary_tiles_only:
        height, width = rgb.shape[:2]
        tile_height = int(height * 0.50)
        tile_width = int(width * 0.50)
        row_starts = [0, (height - tile_height) // 2, height - tile_height]
        col_starts = [0, (width - tile_width) // 2, width - tile_width]
        starts = [(top, left) for top in row_starts for left in col_starts]
        for index, (top, left) in enumerate(starts, start=1):
            tile = rgb[top : top + tile_height, left : left + tile_width]
            variant = f"binary_tile_{index}" if binary_tiles_only else f"tile_{index}"
            if binary_tiles_only:
                gray_tile = cv2.cvtColor(tile, cv2.COLOR_RGB2GRAY)
                binary = cv2.adaptiveThreshold(
                    gray_tile,
                    255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY,
                    51,
                    15,
                )
                tile = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
            lines = ocr(tile, variant)
            passes.append({"variant": variant, "lines": lines})
            if extract_candidates(lines):
                break
        return {"image_id": path.stem, "passes": passes}

    if not skip_high_res:
        high_res = ocr(rgb, "high_res")
        passes.append({"variant": "high_res", "lines": high_res})
        if single_pass or extract_candidates(high_res):
            return {"image_id": path.stem, "passes": passes}

    if not skip_clahe:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        enhanced = cv2.cvtColor(clahe, cv2.COLOR_GRAY2RGB)
        enhanced_lines = ocr(enhanced, "clahe")
        passes.append({"variant": "clahe", "lines": enhanced_lines})
        if single_pass or extract_candidates(enhanced_lines):
            return {"image_id": path.stem, "passes": passes}

    for angle, rotated in (
        ("rot90", cv2.rotate(rgb, cv2.ROTATE_90_CLOCKWISE)),
        ("rot270", cv2.rotate(rgb, cv2.ROTATE_90_COUNTERCLOCKWISE)),
    ):
        lines = ocr(rotated, angle)
        passes.append({"variant": angle, "lines": lines})
        if extract_candidates(lines):
            break
    return {"image_id": path.stem, "passes": passes}


def target_ids(path, supplemental_paths):
    rows = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            rows[row["image_id"].zfill(6)] = list(row.get("lines", []))
    for supplemental_path in supplemental_paths:
        with supplemental_path.open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                image_id = row["image_id"].zfill(6)
                for pass_item in row.get("passes", []):
                    rows[image_id].extend(pass_item.get("lines", []))
                rows[image_id].extend(row.get("lines", []))
    return [image_id for image_id, lines in rows.items() if not extract_candidates(lines)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("baseline_jsonl", type=Path)
    parser.add_argument("output_jsonl", type=Path)
    parser.add_argument("--supplemental-jsonl", type=Path, action="append", default=[])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--single-pass", action="store_true")
    parser.add_argument("--skip-high-res", action="store_true")
    parser.add_argument("--skip-clahe", action="store_true")
    parser.add_argument("--tiles-only", action="store_true")
    parser.add_argument("--binary-tiles-only", action="store_true")
    parser.add_argument("--only-id", action="append", default=[])
    args = parser.parse_args()

    files_by_id = {path.stem: path for path in args.input_dir.iterdir() if path.is_file()}
    ids = target_ids(args.baseline_jsonl, args.supplemental_jsonl)
    if args.only_id:
        requested = {value.zfill(6) for value in args.only_id}
        ids = [image_id for image_id in ids if image_id in requested]
    missing = sorted(set(ids) - set(files_by_id))
    if missing:
        raise FileNotFoundError(f"Missing input images: {missing[:5]}")

    rows = []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as pool:
        futures = {
            pool.submit(
                process_image,
                str(files_by_id[image_id]),
                args.single_pass,
                args.skip_high_res,
                args.skip_clahe,
                args.tiles_only,
                args.binary_tiles_only,
            ): image_id
            for image_id in ids
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if completed % 20 == 0 or completed == len(ids):
                print(f"Processed {completed}/{len(ids)}", flush=True)

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("w", encoding="utf-8") as output:
        for row in sorted(rows, key=lambda item: item["image_id"]):
            output.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
