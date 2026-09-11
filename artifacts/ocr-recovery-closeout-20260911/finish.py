"""Production runner smoke check plus final field and timing accounting."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src.date_extraction import submission_fields
from scripts.evaluate_pipeline import score_predictions


def main():
    live=json.loads((OUT/'live.json').read_text(encoding='utf-8'))
    hashes=live['code_sha256']
    assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in hashes.items())
    assert all(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'] for r in live['rows'])
    old=ROOT/'artifacts/validation-deadline-20260910'
    inputs=ROOT/'artifacts/date-target-role-1500-20260910/live_inputs'
    manifest=json.loads((old/'manifest.json').read_text(encoding='utf-8'))['images']
    assert len(list(inputs.iterdir()))==len(manifest)==14
    assert all(hashlib.sha256((inputs/(r['current_id']+Path(r['path']).suffix)).read_bytes()).hexdigest()==r['sha256'] for r in manifest)
    subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_pipeline.py'),str(inputs),str(old/'labels.csv'),
                    str(OUT/'runner_predictions.csv'),'--report-json',str(OUT/'runner_report.json')],cwd=ROOT,check=True)
    fields={}
    labels={r['current_id']:{'정답 날짜':r['expected'],'라벨 상태':'frozen-development-reference'} for r in live['rows']}
    for key in ('before','after'):
        predictions=[dict(image_id=r['current_id'],**submission_fields(r[key]['value'])) for r in live['rows']]
        fields[key]=score_predictions(labels,predictions,[],all_label_statuses=True)
    report=json.loads((OUT/'runner_report.json').read_text(encoding='utf-8'))
    assert report['runtime']['completed_images']==14 and report['runtime']['status']=='completed'
    assert report['targets']['actual_500_timeout_met'] is None
    assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in hashes.items())
    result=dict(code_sha256=hashes,input_hashes_verified=True,live_metrics=fields,runner_targets=report['targets'])
    (OUT/'verified.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(exact=report['exact_matches'],seconds=report['runtime']['total_elapsed_seconds'],
                          per_image=report['runtime']['seconds_per_image'],targets=report['targets']),ensure_ascii=False))


if __name__=='__main__':main()
