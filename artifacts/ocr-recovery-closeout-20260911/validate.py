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
        old_lines=load('src.dot_old_lines',OUT/'starting_source/line_recovery.py')
        old_lines._link_roles=old_dates._link_roles
        old_lines.parse_dates=old_dates.parse_dates
        old_pipeline.recover_lines=old_lines.recover_lines
        old_pipeline.recovery_targets=old_lines.recovery_targets
        old_pipeline.recover_missing_rows=old_lines.recover_missing_rows
        sample=json.loads((ROOT/'artifacts/structural-integration-20260911/live_result.json').read_text(encoding='utf-8'))['rows']
        runner=json.loads((ROOT/'artifacts/validation-deadline-20260910/manifest.json').read_text(encoding='utf-8'))['images']
        ids={r['current_id'] for r in sample+runner}
        # Exhaust every saved-record trigger for missing-label recovery, not
        # a hand-picked list of known correct cases. Existing development only.
        trigger_ids=[]
        # Bounds depend on image size; use a geometry-only large canvas.
        for row in manifest:
            if not row['evidence']['events']:continue
            first=[date_extraction.OCRLine(**line) for line in row['evidence']['events'][0]['lines']]
            if (not any(date_extraction.parse_dates(line.text) for line in first)
                    and pipeline._label_crop_bounds(np.empty((10000,10000,0),dtype=np.uint8),first) is not None):
                ids.add(row['current_id'])
                if row['current_id'] not in trigger_ids:trigger_ids.append(row['current_id'])
        selected=[r for r in manifest if r['current_id'] in ids]
        if '--quick' in sys.argv:
            selected=[r for r in selected if r['current_id'] in {'003355','003489','003512','003560','003705','000080','000088'}]
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
