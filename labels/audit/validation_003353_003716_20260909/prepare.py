"""Read-only ground truth snapshot and source-integrity manifest."""
import hashlib
import json
from pathlib import Path
from collections import Counter
import openpyxl

OUT = Path(__file__).resolve().parent
LABELS = OUT.parents[1]
BASE = 'validation_003353_003716_manual'
files = [LABELS / (BASE + ext) for ext in ('.csv', '.xlsx', '.xlsx.inspect.ndjson')]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
wb = openpyxl.load_workbook(files[1], read_only=True, data_only=False)
ws = wb['검수 정답지']
rows = list(ws.iter_rows(values_only=True))
truth = [{'image_id': str(int(r[0])).zfill(6), 'truth': r[2]} for r in rows[1:]]
assert len(truth) == 364 and len({r['image_id'] for r in truth}) == 364
assert all(isinstance(r['truth'], str) and r['truth'] for r in truth)
images = Path('C:/ITDA_OCR_CODE/추가수집데이터')
manifest = {'sources': {str(p): sha(p) for p in files}, 'headers': rows[0],
            'images': {r['image_id']: {'path': str(images / (r['image_id'] + '.jpg')),
                       'sha256': sha(images / (r['image_id'] + '.jpg'))} for r in truth}}
(OUT / 'ground_truth.json').write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print({'rows': len(truth), 'categories': dict(Counter('none' if r['truth']=='NONE' else 'partial' if 'NONE' in r['truth'] else 'full' for r in truth)), 'sources': manifest['sources']})
