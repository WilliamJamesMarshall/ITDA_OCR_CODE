"""Final development-only accounting and production runner check."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src.date_extraction import submission_fields
from scripts.evaluate_pipeline import score_predictions


def main():
    files = ('src/pipeline.py','src/date_extraction.py','src/line_recovery.py',
             'src/recognition_evidence.py','src/ocr_trace.py','scripts/evaluate_pipeline.py','scripts/validation_runner.py')
    hashes = {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
    old = ROOT/'artifacts/validation-deadline-20260910'
    inputs = ROOT/'artifacts/date-target-role-1500-20260910/live_inputs'
    manifest = json.loads((old/'manifest.json').read_text(encoding='utf-8'))['images']
    assert len(list(inputs.iterdir())) == len(manifest) == 14
    assert all(hashlib.sha256((inputs/(r['current_id']+Path(r['path']).suffix)).read_bytes()).hexdigest()==r['sha256'] for r in manifest)
    if '--summary-only' in sys.argv:
        previous = json.loads((OUT/'verified.json').read_text(encoding='utf-8'))
        assert previous['source_sha256']==hashes
    else:
        subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_pipeline.py'),str(inputs),str(old/'labels.csv'),
                        str(OUT/'runner_predictions.csv'),'--report-json',str(OUT/'runner_report.json')],cwd=ROOT,check=True)
    replay = json.loads((OUT/'replay.json').read_text(encoding='utf-8'))
    live = json.loads((OUT/'live_result.json').read_text(encoding='utf-8'))
    if live.get('code_sha256'):
        assert all(hashes[name]==value for name,value in live['code_sha256'].items())
    metrics = {}
    for name,rows,id_key in [('cached705',replay['details'],'image_id'),('paired28',live['rows'],'current_id')]:
        labels = {r[id_key]:{'정답 날짜':r['expected'],'라벨 상태':'frozen-development-reference'} for r in rows}
        metrics[name] = {}
        for key in ('before','after'):
            predictions = [dict(image_id=r[id_key],**submission_fields(r[key] if name=='cached705' else r[key]['value'])) for r in rows]
            metrics[name][key] = score_predictions(labels,predictions,[],all_label_statuses=True)
    runner = json.loads((OUT/'runner_report.json').read_text(encoding='utf-8'))
    assert runner['runtime']['status']=='completed'
    assert runner['runtime']['completed_images']==14
    assert runner['submission_format']['all_rows_compliant']
    assert runner['targets']['actual_500_timeout_met'] is None
    assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in hashes.items())
    assert all(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'] for r in live['rows'])
    result = dict(scope='Frozen development references; 705 replay is not image OCR. 28 and 14 are not independent accuracy estimates.',
                  source_sha256=hashes, input_hashes_verified=True, metrics=metrics,
                  runner_targets=runner['targets'], tests_command='.venv/Scripts/python.exe -m unittest discover -s tests -q')
    (OUT/'verified.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(runner_exact=runner['exact_matches'],runner_targets=runner['targets']),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
