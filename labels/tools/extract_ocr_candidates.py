import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR


_ENGINE = None


def init_worker():
    global _ENGINE
    _ENGINE = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)


def process_image(path_string):
    path = Path(path_string)
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1600, 1600))
        results, _ = _ENGINE(np.asarray(image))

    lines = []
    for box, text, score in results or []:
        lines.append({"box": box, "text": text, "score": round(float(score), 4)})
    return {"image_id": path.stem, "lines": lines}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=352)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    files_by_id = {path.stem: path for path in args.input_dir.iterdir() if path.is_file()}
    paths = [files_by_id.get(f"{number:06d}") for number in range(args.start, args.end + 1)]
    missing = [f"{number:06d}" for number, path in zip(range(args.start, args.end + 1), paths) if path is None]
    if missing:
        raise FileNotFoundError(f"Missing input images: {missing[:5]}")

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
