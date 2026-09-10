"""Image-only inference. Does not open ground_truth.json or annotation files."""
import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = '1'
import sys
import time
import json
import hashlib
import platform
import importlib.metadata
from pathlib import Path
from dataclasses import asdict

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/ITDA_OCR_WORKTREES/lee-hoyeon')
sys.path.insert(0, str(ROOT))
started = time.perf_counter()
from src import pipeline as p
import numpy as np

stage = sys.argv[1] if len(sys.argv) > 1 else 'baseline'
if stage != 'baseline':
    from experiments import install
    install(stage, p)
config = p.PipelineConfig(weights_dir=ROOT / 'weights/paddle')
meta = {'stage': stage, 'python': sys.version, 'platform': platform.platform(),
        'config': asdict(config), 'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions() if d.metadata['Name'].lower().startswith(('paddle', 'opencv', 'numpy'))},
        'code_sha256': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'src/pipeline.py', ROOT/'src/date_extraction.py']}}
if stage != 'baseline':
    meta['experiment_sha256'] = hashlib.sha256((OUT/'experiments.py').read_bytes()).hexdigest()
init_start = time.perf_counter()
real = p.PaddleOCRBackend(config)
meta['model_init_seconds'] = time.perf_counter() - init_start
meta['import_and_init_seconds'] = time.perf_counter() - started

class TraceBackend:
    def __init__(self):
        self.image_id = ''
        self.events = []
    def recognize(self, image, *, detector, variant):
        begin = time.perf_counter()
        lines = real.recognize(image, detector=detector, variant=variant)
        self.events.append({'detector': detector, 'variant': variant,
                            'shape': list(image.shape), 'input_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
                            'ocr_seconds': time.perf_counter()-begin,
                            'lines': [asdict(line) for line in lines]})
        return lines

backend = TraceBackend()
images = [Path('C:/ITDA_OCR_CODE/추가수집데이터') / f'{i:06d}.jpg' for i in range(3355, 3719)]
assert all(f.is_file() for f in images)
loop_start = time.perf_counter()
with (OUT / f'{stage}.jsonl').open('x', encoding='utf-8') as output:
    for index, path in enumerate(images, 1):
        backend.image_id = path.stem
        backend.events = []
        begin = time.perf_counter()
        try:
            pred = p.predict_image(path, backend, config)
            record = {'image_id': path.stem, 'prediction': pred.final_date or 'NONE',
                      'reason': pred.selection.reason, 'confident': pred.selection.confident,
                      'passes': list(pred.passes), 'elapsed_seconds': pred.elapsed_seconds,
                      'candidates': [asdict(c) for c in pred.selection.candidates], 'error': None}
        except Exception as exc:
            record = {'image_id': path.stem, 'prediction': 'NONE', 'reason': 'exception',
                      'confident': False, 'passes': [], 'elapsed_seconds': time.perf_counter()-begin,
                      'candidates': [], 'error': f'{type(exc).__name__}: {exc}'}
        record['events'] = backend.events
        output.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
        output.flush()
        if index == 1 or index % 10 == 0 or index == len(images):
            print(json.dumps({'stage':stage,'completed':index,'total':len(images),
                              'seconds':round(time.perf_counter()-loop_start,2),
                              'last':path.stem,'prediction':record['prediction'],'error':record['error']}), flush=True)
        if record['error'] and index <= 3:
            raise RuntimeError(record['error'])
meta['loop_wall_seconds'] = time.perf_counter() - loop_start
meta['total_wall_seconds'] = time.perf_counter() - started
(OUT / f'{stage}_runtime.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print('COMPLETE ' + stage, flush=True)
