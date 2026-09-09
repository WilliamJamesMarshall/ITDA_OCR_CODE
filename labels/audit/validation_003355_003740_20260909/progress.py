import json
import sys
from pathlib import Path
from collections import Counter
OUT=Path(__file__).resolve().parent
for stage in ([sys.argv[1]] if len(sys.argv)>1 else ('baseline','p3')):
    path=OUT/f'{stage}.jsonl'
    if not path.exists():
        continue
    rows=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    seconds=sum(r['elapsed_seconds'] for r in rows)
    print(json.dumps({'stage':stage,'completed':len(rows),'total':386,
                      'image_seconds':round(seconds,1),'average_seconds':round(seconds/len(rows),2),
                      'remaining_minutes_estimate':round(seconds/len(rows)*(386-len(rows))/60,1),
                      'errors':sum(bool(r['error']) for r in rows),
                      'pass_counts':dict(Counter(p for r in rows for p in r['passes']))},ensure_ascii=False))
