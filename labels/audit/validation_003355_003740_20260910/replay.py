"""Fixed-evidence parser ablation; elapsed time excludes OCR and is NOT E2E time."""
import sys
import json
import time
import hashlib
from pathlib import Path
from types import SimpleNamespace
from dataclasses import asdict
sys.path.insert(0, 'C:/ITDA_OCR_WORKTREES/lee-hoyeon')
from src import date_extraction as d
from experiments import install
OUT = Path(__file__).resolve().parent
stage = sys.argv[1]
pipeline = SimpleNamespace()
if stage == 'baseline':
    pipeline.select_date = d.select_date
else:
    install(stage, pipeline)
records = [json.loads(s) for s in (OUT/'baseline.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(records) == 386, 'Baseline must finish before scored replay.'
start = time.perf_counter()
with (OUT/f'{stage}_replay.jsonl').open('w',encoding='utf-8') as output:
    for r in records:
        begin = time.perf_counter()
        lines = [d.OCRLine(**line) for event in r['events'] for line in event['lines']]
        s = pipeline.select_date(lines,final=True)
        row = {'image_id':r['image_id'],'prediction':s.final_date or 'NONE',
               'reason':s.reason,'confident':s.confident,'error':r['error'],
               'candidates':[asdict(c) for c in s.candidates],
               'elapsed_seconds':time.perf_counter()-begin,'passes':r['passes'],
               'measurement':'fixed baseline OCR evidence; parser-only replay; no adaptive early exit'}
        output.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
runtime = {'stage':f'{stage}_replay','parser_only_seconds':time.perf_counter()-start,
           'experiment_sha256':hashlib.sha256((OUT/'experiments.py').read_bytes()).hexdigest() if stage!='baseline' else None,
           'production_parser_sha256':hashlib.sha256(Path(d.__file__).read_bytes()).hexdigest(),
           'warning':'Not end-to-end runtime. Uses all OCR passes collected by the baseline.'}
(OUT/f'{stage}_replay_runtime.json').write_text(json.dumps(runtime,indent=2),encoding='utf-8')
print(runtime)
