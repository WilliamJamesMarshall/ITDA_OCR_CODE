"""Read-only prototype: reject two-digit dates assembled from an HH:MM token."""
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from src import date_extraction as d

original = d._iter_numeric_dates
def guarded(text, repaired):
    for match in original(text, repaired):
        if re.fullmatch(r'\d{1,2}\s+\d{1,2}:\d{2}', match.raw):
            continue
        yield match

labels = json.loads((OUT/'existing_labels.json').read_text(encoding='utf-8'))
truth_existing = {r['image_id']:r['truth'] for r in labels['rows'] if r['status']=='manual'}
truth_new = {r['image_id']:r['truth'] for r in json.loads((ROOT/'artifacts/validation-rebaseline-20260910/ground_truth.json').read_text(encoding='utf-8'))}
summaries = {}
for name,truth,path in [('new386',truth_new,ROOT/'artifacts/validation-rebaseline-20260910/baseline.jsonl'),
                        ('existing341',truth_existing,ROOT/'artifacts/origin-audit-20260909/ocr_evidence.jsonl')]:
    changes = []
    totals = [0,0]
    for raw in path.read_text(encoding='utf-8').splitlines():
        record=json.loads(raw)
        key=record['image_id']
        if key not in truth:
            continue
        source_lines=record['lines'] if 'lines' in record else [line for event in record['events'] for line in event['lines']]
        lines=[d.OCRLine(**line) for line in source_lines]
        predictions=[]
        for function in (original,guarded):
            d._iter_numeric_dates=function
            predictions.append(d.select_date(lines,final=True).final_date or 'NONE')
        for index,value in enumerate(predictions):
            totals[index]+=int(not record.get('error') and value==truth[key])
        if predictions[0]!=predictions[1]:
            changes.append({'image_id':key,'truth':truth[key],'before':predictions[0],'after':predictions[1]})
    summaries[name]={'correct_before':totals[0],'correct_after':totals[1],'changes':changes}
d._iter_numeric_dates=original
(OUT/'clock_guard_probe.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summaries,ensure_ascii=False,indent=2))
