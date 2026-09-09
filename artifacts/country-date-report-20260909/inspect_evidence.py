"""Inspect OCR evidence without changing photographs."""
import argparse
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--start', type=int, default=1)
p.add_argument('--end', type=int, default=3352)
p.add_argument('--mode', choices=['origin','maker','date','all'], default='origin')
a = p.parse_args()
patterns = {
 'origin': r'원산지|제조국|생산국|made\s*in|product\s*of|imported\s*from|country\s*of',
 'maker': r'제조원|제조업|제조사|제조회사|제조및|제조 및|제조/|제조·|제조판매|공장|manufactur|produced',
 'date': r'일[ /,.\-·]*(월)[ /,.\-·]*(년|연)|(?:년|연)[ /,.\-·]*월[ /,.\-·]*일|월[ /,.\-·]*일[ /,.\-·]*(년|연)|dd[/ .-]*mm|yy[/ .-]*mm|mm[/ .-]*dd',
 'all': '.'}
rows = [json.loads(x) for x in Path(__file__).with_name('ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines()]
for r in sorted(rows, key=lambda r:r['image_id']):
 if not a.start <= int(r['image_id']) <= a.end: continue
 lines=[x['text'] for x in r['lines']]
 indices={j for i,t in enumerate(lines) if re.search(patterns[a.mode],t,re.I)
          for j in range(max(0,i-1),min(len(lines),i+4))}
 if indices: print(r['image_id'],'::',' | '.join(lines[j] for j in sorted(indices)))
