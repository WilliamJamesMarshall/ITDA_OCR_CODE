"""Paired fixed development inputs only. No held-out test directory access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src import pipeline, date_extraction


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def main():
    old_dates=load('src.followup_old_dates',OUT/'starting_source/date_extraction.py')
    manifest=json.loads((ROOT/'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))['included']
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('src/pipeline.py','src/date_extraction.py')}
    if '--cache' in sys.argv:
        rows=[]
        for row in manifest:
            item=dict(image_id=row['current_id'],expected=row['expected'])
            for key,module in [('before',old_dates),('after',date_extraction)]:
                lines=[module.OCRLine(**line) for event in row['evidence']['events'] for line in event['lines']]
                selected=module.select_date(lines,final=True)
                item[key]=selected.final_date or 'NONE'
            rows.append(item)
        result=dict(scope='705 saved OCR records, no live OCR',count=len(rows),
                    before=sum(r['before']==r['expected'] for r in rows),after=sum(r['after']==r['expected'] for r in rows),
                    gained=[r['image_id'] for r in rows if r['before']!=r['expected']==r['after']],
                    lost=[r['image_id'] for r in rows if r['before']==r['expected']!=r['after']],rows=rows)
        output='cache.json'
    else:
        old_pipeline=load('src.followup_old_pipeline',OUT/'starting_source/pipeline.py')
        old_pipeline.select_date=old_dates.select_date
        sample=json.loads((ROOT/'artifacts/structural-integration-20260911/live_result.json').read_text(encoding='utf-8'))['rows']
        runner=json.loads((ROOT/'artifacts/validation-deadline-20260910/manifest.json').read_text(encoding='utf-8'))['images']
        ids={r['current_id'] for r in sample+runner}
        selected=[r for r in manifest if r['current_id'] in ids]
        config=pipeline.PipelineConfig(progress_every=0)
        start=time.perf_counter();backend=pipeline.PaddleOCRBackend(config);backend._recovery_model()
        initialization=time.perf_counter()-start
        rows=[]
        for index,row in enumerate(selected):
            path=Path(row['path'])
            assert '테스트용데이터' not in str(path)
            assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
            item={k:row[k] for k in ('current_id','path','expected','sha256')}
            modes=[('before',old_pipeline),('after',pipeline)]
            for key,module in (modes if index%2==0 else modes[::-1]):
                result=module.predict_image(path,backend,config)
                item[key]=dict(value=result.final_date or 'NONE',seconds=result.elapsed_seconds,passes=result.passes,
                               reason=result.selection.reason,trace=result.trace)
            rows.append(item)
            print(json.dumps(dict(done=len(rows),total=len(selected),id=row['current_id'],expected=row['expected'],
                                  before=item['before']['value'],after=item['after']['value']),ensure_ascii=False),flush=True)
            (OUT/'live_progress.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        result=dict(scope='Union of prior 28 and 14 development samples; alternating paired live OCR, shared initialization excluded from per-image timings.',
                    count=len(rows),initialization_seconds=initialization,
                    summary={key:dict(correct=sum(r[key]['value']==r['expected'] for r in rows),
                                       seconds_per_image=sum(r[key]['seconds'] for r in rows)/len(rows),
                                       ocr_seconds_per_image=sum(r[key]['trace']['summary']['ocr_seconds'] for r in rows)/len(rows)) for key in ('before','after')},
                    gained=[r['current_id'] for r in rows if r['before']['value']!=r['expected']==r['after']['value']],
                    lost=[r['current_id'] for r in rows if r['before']['value']==r['expected']!=r['after']['value']],rows=rows)
        output='live.json'
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in hashes.items())
    result['code_sha256']=hashes
    (OUT/output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
