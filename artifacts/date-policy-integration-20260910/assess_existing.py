"""Score a completed 352-image run against the 341 currently confirmed labels."""
import csv
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--run-dir', default='live_existing_352')
parser.add_argument('--out-name', default='existing_assessment.json')
args = parser.parse_args()
LIVE = OUT/args.run_dir
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
labels = read(OUT/'existing_labels.json')
assert sha(Path(labels['source']))==labels['sha256']
truth = {r['image_id']:r['truth'] for r in labels['rows'] if r['status']=='manual'}
runtime = read(LIVE/'runtime.json')
for collection in ('code_sha256','weights_sha256','images_sha256'):
    assert all(sha(Path(name))==digest for name,digest in runtime[collection].items())
records = [json.loads(line) for line in (LIVE/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(records)==352 and len({r['image_id'] for r in records})==352
assert set(truth).issubset({r['image_id'] for r in records}) and len(truth)==341
reference_file = ROOT/'labels/audit/validation_000001_003352/pipeline_submission_3352.csv'
with reference_file.open(encoding='utf-8-sig',newline='') as source:
    archived = {r['image_id']:r['final_date'] for r in csv.DictReader(source)}
rows = []
for row in records:
    key = row['image_id']
    if key not in truth:
        continue
    rows.append({'image_id':key,'truth':truth[key],'prediction':row['prediction'],
                 'correct':not row['error'] and row['prediction']==truth[key],
                 'archived_prediction':archived[key], 'archived_matches':archived[key]==truth[key],
                 'error':row['error']})
summary = {'executed_images':352,'evaluated_manual_labels':341,'excluded_unconfirmed':11,
           'measurement':runtime.get('measurement','fresh image execution'),
           'correct':sum(r['correct'] for r in rows),'archived_csv_matches':sum(r['archived_matches'] for r in rows),
           'gained':[r['image_id'] for r in rows if r['correct'] and not r['archived_matches']],
           'lost':[r['image_id'] for r in rows if not r['correct'] and r['archived_matches']],
           'runtime_errors':sum(bool(r['error']) for r in records),
           'loop_seconds':runtime['loop_wall_seconds'],'total_seconds':runtime['total_wall_seconds'],
           'source_sha256':labels['sha256'],'archived_csv_sha256':sha(reference_file),
           'reference_limit':'Archived CSV has no per-image error/timing provenance; not a fresh controlled baseline run.'}
(OUT/args.out_name).write_text(json.dumps({'summary':summary,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
