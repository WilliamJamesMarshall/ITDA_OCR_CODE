"""Read-only preservation checks; writes evidence outside the submitted repository."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
EVIDENCE=Path('C:/ITDA_OCR_WORKSPACE/strict-layout-20260912')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(f.read()).hexdigest()
def main():
    before=json.loads((EVIDENCE/'protected-before.json').read_text(encoding='utf-8-sig'))
    errors=[]
    for row in before:
        p=Path(row['path'])
        if not p.is_file() or p.stat().st_size!=row['size'] or sha(p)!=row['sha256'].lower():errors.append(str(p))
    names={Path(row['path']).relative_to(ROOT).parts[0] for row in before}
    current={str(p) for name in names for p in (ROOT/name).rglob('*') if p.is_file()}
    expected={row['path'] for row in before}
    errors.extend(sorted(current^expected))
    indexed=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    roots={p.split('/')[0] for p in indexed if p}
    allowed={'predict.ipynb','requirements.txt','README.md','.gitignore','download_weights.sh','notebooks','weights'}
    if roots!=allowed:raise ValueError(f'Unexpected submission roots: {roots}')
    old=json.loads((EVIDENCE/'predict.ipynb').read_text(encoding='utf-8'))
    new=json.loads((ROOT/'predict.ipynb').read_text(encoding='utf-8'))
    assert old['cells'][0]==new['cells'][0]
    from scripts import ocr_annotations as ann
    records=[ann.read(p) for p in (ann.OUT/'records').glob('*.json')]
    assert len(records)==2610 and all(r['review']['status']=='approved' and not ann.validate(r,True) for r in records)
    changes=[]
    for oldfile in (EVIDENCE/'src').glob('*.py'):
        oldtext=oldfile.read_text(encoding='utf-8')
        newtext=(ROOT/'notebooks/project/src'/oldfile.name).read_text(encoding='utf-8')
        if oldfile.name=='pipeline.py':oldtext=oldtext.replace('parents[1] / "weights"','parents[3] / "weights"')
        if oldtext!=newtext:changes.append(oldfile.name)
    assert not changes,changes
    report=dict(protected_files=len(before),protected_changes=errors,submission_roots=sorted(roots),
        config_cell_unchanged=True,approved_annotations=2610,ocr_changes_other_than_weights_path=changes)
    (EVIDENCE/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(report,flush=True)
    if errors:raise ValueError('Protected data changed')
if __name__=='__main__':main()
