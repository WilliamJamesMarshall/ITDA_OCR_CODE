"""Keep scoring inputs and prior result backups separate from image inference."""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
import openpyxl

HERE=Path(__file__).resolve().parent
LABELS=Path('C:/ITDA_OCR_WORKTREES/lee-hoyeon/labels')
OLD=LABELS/'audit/validation_003355_003718_20260910'
NEW=LABELS/'audit/validation_003355_003718_20260910_year_unrestricted'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if len(sys.argv)>1 and sys.argv[1]=='collect':
    assert (NEW/'baseline_runtime.json').is_file(), 'Wait for full inference completion'
    raw=[json.loads(s) for s in (NEW/'baseline.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(raw)== 364 and {r['image_id'] for r in raw}=={f'{i:06d}' for i in range(3355, 3719)}
    for name in ('baseline.jsonl','baseline_runtime.json'):
        shutil.copy2(NEW/name,HERE/name)
    print('Collected complete 386-image baseline')
    raise SystemExit

assert not (HERE/'snapshot_before.json').exists()
(HERE/'outputs').mkdir(exist_ok=True)
(HERE/'previous_results').mkdir(exist_ok=True)
m=json.loads((OLD/'manifest.json').read_text(encoding='utf-8'))
for p,h in m['sources'].items(): assert sha(p)==h,p
for record in m['images'].values(): assert sha(record['path'])==record['sha256']
oldruntime=json.loads((OLD/'p3_runtime.json').read_text(encoding='utf-8'))
for p,h in oldruntime['code_sha256'].items(): assert sha(p)==h,p
oldprov=json.loads((OLD/'provenance_final.json').read_text(encoding='utf-8'))
for p,h in oldprov['weights_current_sha256'].items(): assert sha(p)==h,p
truth=json.loads((OLD/'ground_truth.json').read_text(encoding='utf-8'))
ws=openpyxl.load_workbook(LABELS/'validation_003355_003718_manual.xlsx',data_only=True).active
assert len(truth)== 364 and ws.max_row==387
for row,t in enumerate(truth,2):
    assert str(ws.cell(row,1).value).zfill(6)==t['image_id'] and ws.cell(row,3).value==t['truth']
for name in ('manifest.json','ground_truth.json','p3.jsonl','p3_runtime.json','p3_tests.json','p3_regression.json'):
    shutil.copy2(OLD/name,HERE/name)
files=[p for p in LABELS.glob('validation_003355_003718_*20260910*') if p.is_file()]
assert len(files)==11 and all('manual' not in p.name for p in files)
previous={p.name:sha(p) for p in files}
for p in files: shutil.copy2(p,HERE/'previous_results'/p.name)
verification=json.loads((OLD/'output_verification.json').read_text(encoding='utf-8'))
for stage in ('baseline','p3'):
    assert previous[f'validation_003355_003718_{stage}_20260910.xlsx']==verification[stage]['sha256'], 'Result workbook changed since last verification'
snapshot={'created_at_utc':datetime.now(timezone.utc).isoformat(),'original_sources':m['sources'],
          'previous_outputs':previous,'code_sha256':oldruntime['code_sha256'],
          'weights_sha256':oldprov['weights_current_sha256'],
          'reused_p3_log_sha256':sha(HERE/'p3.jsonl'),'reused_p3_runtime_sha256':sha(HERE/'p3_runtime.json'),
          'old_audit':str(OLD),'new_audit':str(NEW)}
(HERE/'snapshot_before.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
print('Verified original sources, 386 images, code, 9 weight files and reused p3. Backed up 11 prior outputs locally.')
