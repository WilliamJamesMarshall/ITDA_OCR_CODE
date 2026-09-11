"""Paired fixed development inputs only. No held-out test directory access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import subprocess
import os
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src import pipeline, date_extraction


def checkpoint(path,value):
    """Keep the prior checkpoint intact when a bounded write/replace retry fails."""
    temporary=path.with_name(path.name+f'.{os.getpid()}.pending')
    payload=json.dumps(value,ensure_ascii=False,indent=2)
    for attempt in range(3):
        try:
            temporary.write_text(payload,encoding='utf8')
            temporary.replace(path)
            return
        except OSError:
            if attempt==2:raise
            time.sleep(.2*(attempt+1))


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def main():
    old_dates=load('src.followup_old_dates',OUT/'starting_source/date_extraction.py')
    manifest=json.loads((ROOT/'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))['included']
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('src/pipeline.py','src/date_extraction.py','src/line_recovery.py')}
    if '--cache' in sys.argv:
        rows=[]
        for row in manifest:
            item=dict(image_id=row['current_id'],expected=row['expected'])
            for key,module in [('before',old_dates),('after',date_extraction)]:
                lines=[module.OCRLine(**line) for event in row['evidence']['events'] for line in event['lines']]
                options={'context':date_extraction.DateContext()} if key=='after' else {}
                selected=module.select_date(lines,final=True,**options)
                item[key]=selected.final_date or 'NONE'
                if key=='after':
                    item['policy_details']=selected.policy_details
            rows.append(item)
        result=dict(scope='705 saved OCR records, no live OCR',count=len(rows),
                    before=sum(r['before']==r['expected'] for r in rows),after=sum(r['after']==r['expected'] for r in rows),
                    gained=[r['image_id'] for r in rows if r['before']!=r['expected']==r['after']],
                    lost=[r['image_id'] for r in rows if r['before']==r['expected']!=r['after']],rows=rows)
        output='cache.json'
    else:
        old_pipeline=load('src.followup_old_pipeline',OUT/'starting_source/pipeline.py')
        old_pipeline.select_date=old_dates.select_date
        old_lines=load('src.dot_old_lines',OUT/'starting_source/line_recovery.py')
        old_lines._link_roles=old_dates._link_roles
        old_lines.parse_dates=old_dates.parse_dates
        old_pipeline.recover_lines=old_lines.recover_lines
        old_pipeline.recovery_targets=old_lines.recovery_targets
        old_pipeline.recover_missing_rows=old_lines.recover_missing_rows
        previous=json.loads((ROOT/'artifacts/ocr-recovery-closeout-20260911/live.json').read_text(encoding='utf8'))
        ids={r['current_id'] for r in previous['rows']}
        trigger_ids=previous['missing_label_trigger_ids']
        selected=[r for r in manifest if r['current_id'] in ids]
        if '--quick' in sys.argv:
            selected=[r for r in selected if r['current_id'] in {'000018','000033','000034','000061','000255','000256','000305'}]
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
                               reason=result.selection.reason,policy_details=getattr(result.selection,'policy_details',None),trace=result.trace)
            rows.append(item)
            print(json.dumps(dict(done=len(rows),total=len(selected),id=row['current_id'],expected=row['expected'],
                                  before=item['before']['value'],after=item['after']['value']),ensure_ascii=False),flush=True)
            checkpoint(OUT/'live_progress.json',rows)
        result=dict(scope='Prior 34 unique development inputs plus every saved-record missing-label trigger: 55 unique inputs. Alternating paired live OCR; shared initialization excluded from per-image timings; lazy recognizer initialization is charged to its triggering call.',
                    missing_label_trigger_ids=trigger_ids,
                    count=len(rows),initialization_seconds=initialization,
                    summary={key:dict(correct=sum(r[key]['value']==r['expected'] for r in rows),
                                       seconds_per_image=sum(r[key]['seconds'] for r in rows)/len(rows),
                                       ocr_seconds_per_image=sum(r[key]['trace']['summary']['ocr_seconds'] for r in rows)/len(rows)) for key in ('before','after')},
                    gained=[r['current_id'] for r in rows if r['before']['value']!=r['expected']==r['after']['value']],
                    lost=[r['current_id'] for r in rows if r['before']['value']==r['expected']!=r['after']['value']],rows=rows)
        output='quick.json' if '--quick' in sys.argv else 'live.json'
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in hashes.items())
    result['code_sha256']=hashes
    checkpoint(OUT/output,result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    if '--worker' in sys.argv or '--cache' in sys.argv:
        main()
    else:
        # Paired diagnostic OCR also has an outer hard watchdog.
        subprocess.run([sys.executable,__file__,*sys.argv[1:],'--worker'],cwd=ROOT,check=True,timeout=2400)
