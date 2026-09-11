"""Bounded recognition-only feasibility probe on already-used development regions."""
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.pipeline import PipelineConfig, PaddleOCRBackend, _load_bgr


def main():
    backend = PaddleOCRBackend(PipelineConfig())
    pipe = backend._mobile.paddlex_pipeline
    print('PIPE', type(pipe), [name for name in dir(pipe) if 'pipeline' in name or 'rec' in name], flush=True)
    if not hasattr(pipe, 'text_rec_model'):
        pipe = pipe._pipeline
    model = pipe.text_rec_model
    print('REC', type(model), [name for name in dir(model) if 'post' in name or 'predictor' in name], flush=True)
    manifest = json.loads((ROOT/'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))
    results = []
    for item in manifest['included']:
        if item['current_id'] not in {'000276', '003645', '003666'}:
            continue
        pixels = _load_bgr(Path(item['path']))
        events = [json.loads(raw) for raw in (ROOT/f"artifacts/ocr-region-trace-20260911/{item['current_id']}.trace.jsonl").read_text(encoding='utf-8').splitlines()]
        observations = next(e['observations'] for e in events if e['kind']=='ocr_pass')
        for obs in observations:
            text = obs['text']
            if not (obs['date_like'] and sum(c.isdigit() for c in text)>=3 and len(text)<60):
                continue
            left, top, right, bottom = [int(v) for v in obs['original_box']]
            crops = []
            names = []
            for pad in (0, 4, 12):
                crop = pixels[max(0,top-pad):min(pixels.shape[0],bottom+pad), max(0,left-pad):min(pixels.shape[1],right+pad)]
                crops.append(crop)
                names.append(f'pad{pad}')
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                crops.append(cv2.cvtColor(cv2.createCLAHE(clipLimit=2., tileGridSize=(4,4)).apply(gray), cv2.COLOR_GRAY2BGR))
                names.append(f'clahe{pad}')
            started = time.perf_counter()
            predicted = list(model(crops))
            record = dict(image_id=item['current_id'], original=text, box=obs['original_box'], seconds=time.perf_counter()-started,
                          results=[dict(variant=name, text=res['rec_text'], score=float(res['rec_score'])) for name,res in zip(names,predicted)])
            results.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
    (OUT/'probe_rec.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
