#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
import os
from pathlib import Path
root = Path(os.environ['ITDA_INPUT_DIR'])
images = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png'}]
assert len(images) == 500, f'Expected 500 images, found {len(images)}'
assert len({p.stem for p in images}) == 500, 'Duplicate image IDs'
assert not Path(os.environ['ITDA_OUTPUT_PATH']).exists(), 'Use a fresh output directory'
PY
timeout --signal=TERM --kill-after=10s 2400s \
    jupyter nbconvert --to notebook --execute predict.ipynb \
    --ExecutePreprocessor.timeout=2400 --output /output/executed.ipynb
python - <<'PY'
import csv
import json
import os
from pathlib import Path
root = Path(os.environ['ITDA_INPUT_DIR'])
output = Path(os.environ['ITDA_OUTPUT_PATH'])
ids = {p.stem for p in root.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png'}}
with output.open(encoding='utf-8', newline='') as stream:
    reader = csv.DictReader(stream)
    assert reader.fieldnames == ['image_id', 'year', 'month', 'day', 'final_date']
    rows = list(reader)
assert len(rows) == 500 and {r['image_id'] for r in rows} == ids
for row in rows:
    for field, width in [('year', 4), ('month', 2), ('day', 2)]:
        value = row[field]
        assert value == 'NONE' or (value.isascii() and value.isdigit() and len(value) == width)
    parts = [row[k] for k in ('year', 'month', 'day')]
    expected = 'NONE' if parts == ['NONE'] * 3 else '-'.join(parts)
    assert row['final_date'] == expected, row
status = json.loads(Path(str(output) + '.status.json').read_text(encoding='utf-8'))
assert status['output_complete'] and status['processed_images'] == 500
assert not status['failures'], status['failures']
print('PASS: 500 input IDs, 500 CSV rows, approved partial-date format, no inference failures')
PY
