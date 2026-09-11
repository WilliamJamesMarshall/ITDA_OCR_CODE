"""Persist final local verification without touching source images or labels."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import re

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent


def main():
    live=json.loads((OUT/'live.json').read_text(encoding='utf8'))
    cache=json.loads((OUT/'cache.json').read_text(encoding='utf8'))
    assert live['code_sha256']==cache['code_sha256']
    assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest for path,digest in live['code_sha256'].items())
    assert all(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256'] for row in live['rows'])
    assert not live['lost'] and not cache['lost']
    assert all(not outcome['error'] for row in live['rows'] for key in ('before','after') for outcome in row[key]['trace']['outcomes'])
    assert all(not decision.get('error') for row in live['rows'] for key in ('before','after')
               for decision in row[key]['trace']['recovery_decisions'])
    models=[]
    downloads=(ROOT/'download_weights.sh').read_text(encoding='utf8')
    for name,revision,filename,expected in re.findall(r'fetch "([^"]+)" "([^"]+)" "([^"]+)"\s*\\\s*"([0-9a-f]{64})"',downloads):
        path=ROOT/'weights/paddle'/name/filename
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual==expected,str(path)
        models.append(dict(model=name,revision=revision,file=filename,sha256=actual,bytes=path.stat().st_size))
    assert len(models)==12
    completed=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-q'],cwd=ROOT,text=True,encoding='utf8',capture_output=True)
    (OUT/'unit-tests.txt').write_text(completed.stdout+completed.stderr,encoding='utf8')
    assert completed.returncode==0,completed.stderr
    subprocess.run([sys.executable,'-m','compileall','-q','src','tests'],cwd=ROOT,check=True)
    whitespace=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True)
    assert whitespace.returncode==0,whitespace.stdout
    result=dict(code_sha256=live['code_sha256'],development_input_count=live['count'],development_input_hashes_verified=True,
                paired_live_errors=0,live_regressions=live['lost'],cache_regressions=cache['lost'],
                unittest_returncode=completed.returncode,unittest_summary=completed.stderr.strip(),
                compileall_passed=True,git_diff_check_passed=True,offline_models=models)
    (OUT/'final_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
