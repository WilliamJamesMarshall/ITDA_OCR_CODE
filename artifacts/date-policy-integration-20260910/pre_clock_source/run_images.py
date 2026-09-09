"""Image-only production execution with immutable OCR evidence and timings."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('input_dir', type=Path)
parser.add_argument('output_dir', type=Path)
parser.add_argument('--limit', type=int)
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[2]
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT))
started = time.perf_counter()
from src import pipeline as p

config = p.PipelineConfig(weights_dir=Path('C:/ITDA_OCR_WORKTREES/lee-hoyeon/weights/paddle'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
meta = {'python':sys.version,'platform':platform.platform(),'config':asdict(config),
        'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata['Name'].lower().startswith(('paddle','opencv','numpy'))},
        'code_sha256':{str(path):sha(path) for path in (ROOT/'src/pipeline.py',ROOT/'src/date_extraction.py')},
        'weights_sha256':{str(path):sha(path) for path in config.weights_dir.glob('*/*') if path.is_file()},
        'runner_sha256':sha(Path(__file__))}
images = p.discover_images(args.input_dir)
if args.limit:
    images = images[:args.limit]
meta['images_sha256'] = {str(path):sha(path) for path in images}
(OUT/'start.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
init = time.perf_counter()
real = p.PaddleOCRBackend(config)
meta['model_init_seconds'] = time.perf_counter()-init
meta['import_and_init_seconds'] = time.perf_counter()-started

class TraceBackend:
    def __init__(self): self.events = []
    def recognize(self, image, *, detector, variant):
        begin = time.perf_counter()
        lines = real.recognize(image,detector=detector,variant=variant)
        self.events.append({'detector':detector,'variant':variant,'shape':list(image.shape),
                            'input_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
                            'ocr_seconds':time.perf_counter()-begin,'lines':[asdict(line) for line in lines]})
        return lines

backend = TraceBackend()
loop = time.perf_counter()
with (OUT/'predictions.jsonl').open('x',encoding='utf-8') as log, (OUT/'submission.csv').open('x',encoding='utf-8',newline='') as output:
    writer = csv.DictWriter(output,fieldnames=p.OUTPUT_COLUMNS,lineterminator='\n')
    writer.writeheader()
    for index,path in enumerate(images,1):
        backend.events = []
        begin = time.perf_counter()
        try:
            pred = p.predict_image(path,backend,config)
            fields = p.submission_fields(pred.final_date)
            record = {'image_id':path.stem,'prediction':fields['final_date'],'reason':pred.selection.reason,
                      'confident':pred.selection.confident,'passes':list(pred.passes),'elapsed_seconds':pred.elapsed_seconds,
                      'candidates':[asdict(c) for c in pred.selection.candidates],'error':None}
        except Exception as exc:
            fields = p.submission_fields(None)
            record = {'image_id':path.stem,'prediction':'NONE','reason':'exception','passes':[],
                      'elapsed_seconds':time.perf_counter()-begin,'error':f'{type(exc).__name__}: {exc}'}
        writer.writerow({'image_id':path.stem,**fields})
        record['events'] = backend.events
        log.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
        log.flush()
        if index==1 or index%10==0 or index==len(images):
            print(json.dumps({'completed':index,'total':len(images),'seconds':round(time.perf_counter()-loop,2),'error':record['error']}),flush=True)
meta['loop_wall_seconds'] = time.perf_counter()-loop
meta['total_wall_seconds'] = time.perf_counter()-started
assert all(sha(Path(path))==digest for path,digest in meta['code_sha256'].items()), 'Code changed during inference'
(OUT/'runtime.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print('COMPLETE',flush=True)
