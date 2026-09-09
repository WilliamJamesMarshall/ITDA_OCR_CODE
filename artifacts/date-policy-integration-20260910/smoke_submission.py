"""Prepare identical local weights and exercise unchanged notebook cells offline.

This executes the three Python cells directly, not a Jupyter kernel benchmark.
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import socket
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--name', default='smoke')
args = parser.parse_args()
sys.path.insert(0,str(ROOT))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
manifest = json.loads((ROOT/'artifacts/validation-rebaseline-20260910/snapshot_before.json').read_text(encoding='utf-8'))
prepared = {}
for name,digest in manifest['weights_sha256'].items():
    source = Path(name)
    target = ROOT/'weights/paddle'/source.parent.name/source.name
    assert sha(source)==digest
    if target.exists():
        assert sha(target)==digest, 'Never overwrite existing nonmatching weights'
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    assert sha(target)==digest
    prepared[str(target)] = digest
smoke = OUT/args.name
inputs = smoke/'images'
inputs.mkdir(parents=True,exist_ok=False)
shutil.copy2(ROOT/'추가수집데이터/003359.jpg',inputs/'003359.jpg')
os.environ['ITDA_INPUT_DIR'] = str(inputs)
os.environ['ITDA_OUTPUT_PATH'] = str(smoke/'submission.csv')
notebook = ROOT/'predict.ipynb'
before = sha(notebook)
scope = {'__name__':'__main__'}
with patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden in submission smoke test')):
    for index,cell in enumerate(json.loads(notebook.read_text(encoding='utf-8'))['cells']):
        if cell['cell_type']=='code':
            exec(compile(''.join(cell['source']),f'predict.ipynb:cell-{index}', 'exec'),scope)
with (smoke/'submission.csv').open(encoding='utf-8',newline='') as source:
    reader = csv.DictReader(source)
    assert reader.fieldnames==['image_id','year','month','day','final_date']
    rows = list(reader)
assert rows==[{'image_id':'003359','year':'2022','month':'06','day':'20','final_date':'2022-06-20'}]
assert not scope['summary']['failures'] and sha(notebook)==before
result = {'notebook_unchanged':True,'network_connect_blocked':True,'execution':'Unmodified notebook Python cells; no Jupyter kernel',
          'output_rows':rows,'prepared_weights':prepared,'notebook_sha256':before,
          'code_sha256':{str(path):sha(path) for path in (ROOT/'src/pipeline.py',ROOT/'src/date_extraction.py')}}
(OUT/f'submission_{args.name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
