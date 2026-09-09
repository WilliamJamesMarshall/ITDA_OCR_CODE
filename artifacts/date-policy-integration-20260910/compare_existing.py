"""A separate fixed-original-OCR check, not the historical 341-label benchmark."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src import date_extraction as current

source = Path('C:/ITDA_OCR_WORKTREES/lee-hoyeon/src/date_extraction.py')
spec = importlib.util.spec_from_file_location('reference_date_extraction',source)
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)
reference.MIN_YEAR = 1
labels = json.loads((OUT/'existing_labels.json').read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(Path(labels['source']))==labels['sha256']
truth = {row['image_id']:row for row in labels['rows']}
cache = ROOT/'artifacts/origin-audit-20260909/ocr_evidence.jsonl'
rows = []
seen = set()
for raw in cache.read_text(encoding='utf-8').splitlines():
    record = json.loads(raw)
    key = record['image_id']
    assert key not in seen
    seen.add(key)
    label = truth.get(key)
    if label is None or label['status']!='manual':
        continue
    values = {}
    for name,module in (('baseline',reference),('integrated',current)):
        lines = [module.OCRLine(**line) for line in record['lines']]
        value = module.select_date(lines,final=True).final_date or 'NONE'
        values[name] = value
        values[name+'_correct'] = not record.get('error') and value==label['truth']
    rows.append({'image_id':key,'truth':label['truth'],**values})
eligible = {key for key,row in truth.items() if row['status']=='manual'}
assert {r['image_id'] for r in rows}==eligible and len(rows)==341
summary = {'measurement':'Fixed downscaled original OCR; no recovery/early exit; current manual labels only',
           'total':len(rows),'cached_images':len(seen),'manual_coverage_complete':True,
           'baseline':sum(r['baseline_correct'] for r in rows),
           'integrated':sum(r['integrated_correct'] for r in rows),
           'gained':[r['image_id'] for r in rows if not r['baseline_correct'] and r['integrated_correct']],
           'lost':[r['image_id'] for r in rows if r['baseline_correct'] and not r['integrated_correct']],
           'label_source':labels['source'],'label_sha256':labels['sha256'],
           'ocr_sha256':sha(cache),'baseline_code_sha256':sha(source),
           'integrated_code_sha256':sha(ROOT/'src/date_extraction.py')}
assert sha(Path(labels['source']))==labels['sha256']
(OUT/'existing_comparison.json').write_text(json.dumps({'summary':summary,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
