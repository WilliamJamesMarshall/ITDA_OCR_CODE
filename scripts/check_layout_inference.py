"""Compare immutable pre-migration source against current source on one exposed image."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=Path('C:/ITDA_OCR_WORKSPACE/migration-20260912')

def main():
    from scripts import ocr_annotations as ann
    record=ann.read(ann.record_path('BMLC002247'))
    if not record['seen_in_development']:
        raise ValueError('Only previously exposed development data may be used')
    inputs=EVIDENCE/'inference-input';inputs.mkdir(exist_ok=True)
    image=ann.source_path(record)
    shutil.copy2(image,inputs/image.name)
    results=[]
    for label,code_root in [('before',EVIDENCE),('after',ROOT)]:
        for repeat in range(3):
            output=EVIDENCE/f'{label}-{repeat}.csv'
            script='''import sys,time,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
t=time.perf_counter()
from src.pipeline import run_pipeline,PipelineConfig
summary=run_pipeline(sys.argv[2],sys.argv[3],config=PipelineConfig(weights_dir=Path(sys.argv[4]),cpu_threads=4,progress_every=0))
Path(sys.argv[5]).write_text(json.dumps(dict(wall_seconds=time.perf_counter()-t,summary=summary)),encoding='utf-8')
'''
            result_path=EVIDENCE/f'{label}-{repeat}.json'
            with (EVIDENCE/f'{label}-{repeat}.log').open('w',encoding='utf-8') as log:
                subprocess.run([sys.executable,'-c',script,str(code_root),str(inputs),str(output),str(ROOT/'weights/paddle'),str(result_path)],cwd=code_root,stdout=log,stderr=log,check=True)
            results.append(dict(variant=label,repeat=repeat,**json.loads(result_path.read_text(encoding='utf-8'))))
            print(label,repeat,'complete',flush=True)
    outputs=[(EVIDENCE/f'{label}-{repeat}.csv').read_bytes() for label in ['before','after'] for repeat in range(3)]
    report=dict(sample='BMLC002247',previously_exposed=True,csv_identical=all(x==outputs[0] for x in outputs),runs=results,
                scope='One exposed-image Windows smoke benchmark; not Linux offline qualification or full accuracy certification.')
    (EVIDENCE/'inference_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not report['csv_identical']:raise ValueError('Inference CSV changed')

if __name__=='__main__':main()
