"""Publish only the 11 requested result artifacts after verification and backup."""
import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
LABELS=Path('C:/ITDA_OCR_WORKTREES/lee-hoyeon/labels').resolve()
AUDIT=(LABELS/'audit/validation_003355_003740_20260910_year_unrestricted').resolve()
assert AUDIT.parent==LABELS/'audit' and AUDIT.is_dir()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
snapshot=json.loads((HERE/'snapshot_before.json').read_text(encoding='utf-8'))
verification=json.loads((HERE/'output_verification.json').read_text(encoding='utf-8'))
assert verification['all_stage_csvs_match'] and verification['config_packages_and_experiment_verified']
for stage in ('baseline','p3'):
    assert verification[stage]['style_difference_count']==0 and verification[stage]['values_and_formulas_match']
    target=HERE/'outputs'/f'validation_003355_003740_{stage}_20260910.xlsx'
    assert sha(target)==verification[stage]['sha256']
for collection in ('original_sources','code_sha256','weights_sha256'):
    for name,digest in snapshot[collection].items(): assert sha(name)==digest,name
for name,digest in snapshot['previous_outputs'].items():
    assert (LABELS/name).resolve().parent==LABELS and 'manual' not in name
    assert sha(LABELS/name)==digest, f'Result edited since snapshot: {name}'
files={p.name:p for p in (HERE/'outputs').iterdir() if p.is_file()}
assert set(files)==set(snapshot['previous_outputs']) and len(files)==11
assert sha(HERE/'p3.jsonl')==snapshot['reused_p3_log_sha256']
assert sha(HERE/'p3_runtime.json')==snapshot['reused_p3_runtime_sha256']

backup=AUDIT/'previous_results'
backup.mkdir(exist_ok=False)
for name in files: shutil.copy2(LABELS/name,backup/name)
for source in HERE.iterdir():
    if not source.is_file() or source.suffix not in ('.py','.mjs','.json','.jsonl','.md','.png'):
        continue
    target=AUDIT/source.name
    if target.exists():
        assert sha(target)==sha(source),f'Audit collision: {target}'
    else:
        shutil.copy2(source,target)

pending={}
for name,source in files.items():
    target=LABELS/('.'+name+'.rebaseline.tmp')
    assert not target.exists()
    shutil.copy2(source,target)
    assert sha(source)==sha(target)
    pending[name]=target
replaced=[]
try:
    for name,target in pending.items():
        target.replace(LABELS/name)
        replaced.append(name)
except Exception:
    for name in replaced: shutil.copy2(backup/name,LABELS/name)
    raise
for name,source in files.items(): assert sha(LABELS/name)==sha(source)
for name,digest in snapshot['original_sources'].items(): assert sha(name)==digest
receipt={'published_at_utc':datetime.now(timezone.utc).isoformat(),'backup_directory':str(backup),
         'originals_unchanged':True,'published':{name:sha(LABELS/name) for name in sorted(files)}}
(AUDIT/'publish_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
