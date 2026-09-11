"""Hash-fixed existing development sample, alternating paired real OCR."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import pipeline


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    code_hashes = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                   ('src/pipeline.py','src/date_extraction.py','src/line_recovery.py','src/recognition_evidence.py','src/ocr_trace.py')}
    manifest = json.loads((ROOT/'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))['included']
    old_sample = json.loads((ROOT/'artifacts/date-recognition-repair-20260910/live_manifest.json').read_text(encoding='utf-8'))['images']
    ids = {r['current_id'] for r in old_sample} | {'003645', '003666', '003714', '000276'}
    selected = [r for r in manifest if r['current_id'] in ids]
    before = load('src.integration_before', OUT/'starting_source/pipeline.py')
    before.select_date = load('src.integration_before_dates', OUT/'starting_source/date_extraction.py').select_date
    config = pipeline.PipelineConfig(progress_every=0)
    start = time.perf_counter()
    backend = pipeline.PaddleOCRBackend(config)
    backend._recovery_model()
    initialization = time.perf_counter()-start
    rows = []
    for index, item in enumerate(selected):
        path = Path(item['path'])
        assert '테스트용데이터' not in str(path)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
        row = {k:item[k] for k in ('current_id','expected','sha256','path')}
        for key, module in ([('before',before),('after',pipeline)] if index%2==0 else [('after',pipeline),('before',before)]):
            prediction = module.predict_image(path, backend, config)
            row[key] = dict(value=prediction.final_date or 'NONE', seconds=prediction.elapsed_seconds,
                            passes=prediction.passes, reason=prediction.selection.reason,
                            trace=prediction.trace)
        rows.append(row)
        (OUT/'live_progress.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(completed=len(rows),total=len(selected),id=item['current_id'],
                              before=row['before']['value'],after=row['after']['value'],expected=item['expected']),ensure_ascii=False),flush=True)
    summary = {}
    for key in ('before','after'):
        summary[key] = dict(correct=sum(r[key]['value']==r['expected'] for r in rows),
                            seconds_per_image=sum(r[key]['seconds'] for r in rows)/len(rows),
                            ocr_seconds_per_image=sum(r[key]['trace']['summary']['ocr_seconds'] for r in rows)/len(rows))
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in code_hashes.items())
    result = dict(scope='Existing development sample only; alternating paired runs, reused backend; not independent 500-image accuracy.',
                  code_sha256=code_hashes,
                  count=len(rows), shared_initialization_seconds=initialization, summary=summary,
                  gained=[r['current_id'] for r in rows if r['before']['value']!=r['expected']==r['after']['value']],
                  lost=[r['current_id'] for r in rows if r['before']['value']==r['expected']!=r['after']['value']], rows=rows)
    (OUT/'live_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
