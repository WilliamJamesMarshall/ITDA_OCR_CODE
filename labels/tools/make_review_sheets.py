import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


DATE_TEXT = re.compile(
    r"(?:20[2-3]\d|(?:^|\D)2[4-9][./,/: -]\d{1,2}[./,/: -]\d{1,2}|"
    r"\d{1,2}[./,/: -]\d{1,2}[./,/: -](?:20)?2[4-9]|EXP|E\.DATE|PROD|PRD|PD)",
    re.IGNORECASE,
)


def candidate_lines(lines):
    selected = [line for line in lines if DATE_TEXT.search(line["text"])]
    return selected[:4]


def evidence_block(image_path, lines, width=1400):
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1600, 1600))

    font = ImageFont.load_default(size=24)
    header_height = 42
    band_height = 210
    selected = candidate_lines(lines)
    if not selected:
        preview = image.copy()
        preview.thumbnail((width, 900))
        block = Image.new("RGB", (width, header_height + preview.height), "white")
        ImageDraw.Draw(block).text((10, 8), f"{image_path.stem} | NO DATE-LIKE OCR", fill="black", font=font)
        block.paste(preview, ((width - preview.width) // 2, header_height))
        return block

    block = Image.new("RGB", (width, header_height + band_height * len(selected)), "white")
    draw = ImageDraw.Draw(block)
    texts = " | ".join(line["text"] for line in selected)
    draw.text((10, 8), f"{image_path.stem} | {texts[:100]}", fill="black", font=font)
    for index, line in enumerate(selected):
        ys = [point[1] for point in line["box"]]
        top = max(0, int(min(ys) - 75))
        bottom = min(image.height, int(max(ys) + 75))
        crop = image.crop((0, top, image.width, bottom))
        crop.thumbnail((width, band_height))
        y = header_height + index * band_height
        block.paste(crop, ((width - crop.width) // 2, y))
    return block


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("ocr_jsonl", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--per-sheet", type=int, default=8)
    args = parser.parse_args()

    files_by_id = {path.stem: path for path in args.input_dir.iterdir() if path.is_file()}
    rows = [json.loads(line) for line in args.ocr_jsonl.read_text(encoding="utf-8").splitlines()]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for offset in range(0, len(rows), args.per_sheet):
        group = rows[offset : offset + args.per_sheet]
        blocks = [evidence_block(files_by_id[row["image_id"]], row["lines"]) for row in group]
        sheet = Image.new("RGB", (1400, sum(block.height for block in blocks)), "#d0d0d0")
        y = 0
        for block in blocks:
            sheet.paste(block, (0, y))
            y += block.height
        start = group[0]["image_id"]
        end = group[-1]["image_id"]
        sheet.save(args.output_dir / f"review_{start}_{end}.jpg", quality=92)


if __name__ == "__main__":
    main()
