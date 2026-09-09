"""Run the unchanged baseline with MIN_YEAR=1, reusing identical OCR inputs.

Cache misses invoke the original local model. This validates adaptive predictions,
but elapsed time is NOT an end-to-end speed benchmark. No label files are read.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/ITDA_OCR_WORKTREES/lee-hoyeon')
sys.path.insert(0,str(ROOT))
from src import pipeline as p
from src import date_extraction as d
d.MIN_YEAR = 1
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
baseline = json.loads((Path('C:/ITDA_OCR_CODE/artifacts/validation-rebaseline-20260910')/'baseline_runtime.json').read_text(encoding='utf-8'))
assert all(sha(Path(name))==digest for name,digest in baseline['code_sha256'].items())
live = OUT/'live_existing_352'
meta = json.loads((live/'runtime.json').read_text(encoding='utf-8'))
assert meta['config']==baseline['config'] and meta['packages']==baseline['packages']
assert all(sha(Path(name))==digest for name,digest in meta['images_sha256'].items())
cache = {}
for raw in (live/'predictions.jsonl').read_text(encoding='utf-8').splitlines():
    for event in json.loads(raw)['events']:
        key = (event['detector'],event['variant'],tuple(event['shape']),event['input_sha256'])
        if key in cache:
            assert cache[key]==event['lines']
        cache[key] = event['lines']

class CachedBackend:
    def __init__(self):
        self.real = None
        self.hits = self.misses = 0
    def recognize(self,image,*,detector,variant):
        key = (detector,variant,tuple(image.shape),hashlib.sha256(image.tobytes()).hexdigest())
        if key in cache:
            self.hits += 1
            return [d.OCRLine(**line) for line in cache[key]]
        self.misses += 1
        if self.real is None:
            self.real = p.PaddleOCRBackend(p.PipelineConfig())
        return self.real.recognize(image,detector=detector,variant=variant)

backend = CachedBackend()
started = time.perf_counter()
target = OUT/'reference_existing.jsonl'
with target.open('x',encoding='utf-8') as output:
    for index,path in enumerate(p.discover_images('C:/ITDA_OCR_CODE/상품사진입니다')[:352],1):
        try:
            result = p.predict_image(path,backend,p.PipelineConfig())
            row = {'image_id':path.stem,'prediction':result.final_date or 'NONE','error':None,'passes':list(result.passes)}
        except Exception as exc:
            row = {'image_id':path.stem,'prediction':'NONE','error':str(exc),'passes':[]}
        output.write(json.dumps(row,ensure_ascii=False)+'\n')
        output.flush()
        if index%25==0 or index==352:
            print(json.dumps({'completed':index,'total':352,'cached_calls':backend.hits,'fresh_calls':backend.misses}),flush=True)
assert all(sha(Path(name))==digest for name,digest in baseline['code_sha256'].items())
report = {'measurement':'Adaptive baseline with identical-input OCR cache and real-model misses; NOT E2E timing',
          'images':352,'cached_calls':backend.hits,'fresh_calls':backend.misses,
          'execution_seconds':time.perf_counter()-started,'code_sha256':baseline['code_sha256']}
(OUT/'reference_existing_runtime.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
