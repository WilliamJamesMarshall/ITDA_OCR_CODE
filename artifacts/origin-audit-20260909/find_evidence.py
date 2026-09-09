"""Print manufacturing/origin cue context from cached OCR (not a classifier)."""
import argparse
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--start", type=int, default=1)
parser.add_argument("--end", type=int, default=3352)
parser.add_argument("--all-text", action="store_true")
args = parser.parse_args()
cue = re.compile(r"제조|원산|생산국|made\s*in|product\s*of|manufactur|produced|country\s*of", re.I)
path = Path(__file__).parent / "ocr_evidence.jsonl"
rows = sorted((json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()),
              key=lambda row: row["image_id"])
print(f"CACHED: {len(rows)}/3352")
for row in rows:
    if not args.start <= int(row["image_id"]) <= args.end:
        continue
    texts = [line["text"] for line in row["lines"]]
    hits = [i for i, t in enumerate(texts) if cue.search(t)]
    if args.all_text or hits:
        indices = range(len(texts)) if args.all_text else sorted({
            j for i in hits for j in range(max(0, i-1), min(len(texts), i+5))})
        print(row["image_id"] + " :: " + " | ".join(texts[j] for j in indices))
