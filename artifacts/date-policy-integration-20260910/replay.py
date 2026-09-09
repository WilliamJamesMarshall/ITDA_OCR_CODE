"""Evaluate production postprocessing on fixed evidence, not an E2E benchmark."""
import sys
import json
import time
from pathlib import Path
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.date_extraction import OCRLine, select_date, submission_fields

AUDIT = ROOT/'artifacts/validation-rebaseline-20260910'
OUT = Path(__file__).resolve().parent
truth = {r['image_id']: r['truth'] for r in json.loads((AUDIT/'ground_truth.json').read_text(encoding='utf-8'))}
start = time.perf_counter()
rows = []
for raw in (AUDIT/'baseline.jsonl').read_text(encoding='utf-8').splitlines():
    r = json.loads(raw)
    lines = [OCRLine(**line) for e in r['events'] for line in e['lines']]
    selected = select_date(lines, final=True)
    value = submission_fields(selected.final_date)['final_date']
    rows.append({'image_id':r['image_id'], 'truth':truth[r['image_id']], 'prediction':value,
                 'correct':not r['error'] and value == truth[r['image_id']], 'baseline':r['prediction'],
                 'reason':selected.reason,'candidates':[asdict(c) for c in selected.candidates[:8]]})
summary = {'measurement':'fixed evidence, postprocessing only', 'rows':len(rows),
           'correct':sum(r['correct'] for r in rows), 'seconds':time.perf_counter()-start,
           'gained':[r['image_id'] for r in rows if r['correct'] and r['baseline']!=r['truth']],
           'lost':[r['image_id'] for r in rows if not r['correct'] and r['baseline']==r['truth']]}
(OUT/'replay.json').write_text(json.dumps({'summary':summary,'rows':rows},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
for r in rows:
    if r['image_id'] in ('003451','003482','003738'):
        print(json.dumps(r,ensure_ascii=False,default=str))
