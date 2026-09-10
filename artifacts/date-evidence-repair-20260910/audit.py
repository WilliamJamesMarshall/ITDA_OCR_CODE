"""Freeze the starting implementation and inventory every reported regression."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.date_extraction import _format_hints, parse_dates


def main():
    if (OUT / "regressions.json").exists():
        raise RuntimeError("Historical audit is frozen. Dataset filenames were reused after renumbering; do not overwrite image identity.")
    baseline = OUT / "starting_source"
    baseline.mkdir(exist_ok=True)
    for name in ("date_extraction.py", "pipeline.py"):
        target = baseline / name
        if not target.exists():
            shutil.copy2(ROOT / "src" / name, target)
    result = json.loads((ROOT / "artifacts/date-order-implementation-20260910/release/fixed_evidence.json").read_text(encoding="utf-8"))
    records = []
    for name, directory, images in (("additional386", "release_386_cache", "추가수집데이터"),
                                    ("existing352", "release_existing_cache", "상품사진입니다")):
        losses = {r["id"]: r for r in result["sets"][name]["details"] if r["before"] == r["expected"] and r["after"] != r["expected"]}
        source = ROOT / "artifacts/date-policy-integration-20260910" / directory / "predictions.jsonl"
        for row in map(json.loads, source.read_text(encoding="utf-8").splitlines()):
            if row["image_id"] not in losses:
                continue
            texts = list(dict.fromkeys(line["text"] for event in row["events"] for line in event["lines"]))
            files = list((ROOT / images).glob(row["image_id"] + ".*"))
            records.append({**losses[row["image_id"]], "set": name, "path": str(files[0]),
                            "sha256": hashlib.sha256(files[0].read_bytes()).hexdigest(),
                            "ocr_text": texts, "format_hints": [t for t in texts if _format_hints(t)],
                            "full_dates": [t for t in texts if any(p.year_digits == 4 for p in parse_dates(t))]})
    assert len(records) == 69
    (OUT / "regressions.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    from PIL import Image, ImageOps, ImageDraw
    for batch in range(0, len(records), 8):
        sheet = Image.new("RGB", (2000, 2400), "white")
        draw = ImageDraw.Draw(sheet)
        for offset, record in enumerate(records[batch:batch+8]):
            tile = ImageOps.exif_transpose(Image.open(record["path"])).convert("RGB")
            tile.thumbnail((990,550))
            x, y = (offset % 2) * 1000, (offset // 2) * 600
            sheet.paste(tile, (x, y + 35))
            draw.text((x+5,y+5), f'{record["id"]} truth={record["expected"]} fallback={record["after"]}', fill="black")
        sheet.save(OUT / f"sheet_{batch//8+1:02d}.jpg", quality=90)
    print(json.dumps({"regressions": len(records), "with_detected_hints": [r["id"] for r in records if r["format_hints"]],
                      "with_four_digit_dates": [r["id"] for r in records if r["full_dates"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
