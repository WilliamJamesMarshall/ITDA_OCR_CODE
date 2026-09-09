"""Score completed runs separately from image-only inference and verify provenance."""
import csv
import argparse
import hashlib
import json
from collections import Counter
from math import ceil
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
OLD = ROOT/'artifacts/validation-rebaseline-20260910'
parser = argparse.ArgumentParser()
parser.add_argument('--run-dir', default='live_386_verified')
parser.add_argument('--out-name', default='assessment.json')
args = parser.parse_args()
LIVE = OUT/args.run_dir
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def records(path): return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
truth = {r['image_id']:r['truth'] for r in read(OLD/'ground_truth.json')}
manifest = read(OLD/'manifest.json')
integrity = {}
for filename,digest in manifest['sources'].items():
    source = Path(filename)
    # The manifest names the authoritative worktree sources. Same-named files
    # in another checkout are not necessarily byte-identical and are not scored.
    integrity[str(source)] = sha(source)==digest
assert all(integrity.values()), 'Original labels changed'
meta = read(LIVE/'runtime.json')
for collection in ('code_sha256','weights_sha256','images_sha256'):
    for filename,digest in meta[collection].items():
        assert sha(Path(filename))==digest, (collection,filename)
reference = read(OLD/'baseline_runtime.json')
assert meta['config']==reference['config']
assert meta['packages']==reference['packages']
resolved_images = {str(Path(name).resolve()): digest for name,digest in meta['images_sha256'].items()}
for key,entry in manifest['images'].items():
    assert resolved_images[str(Path(entry['path']).resolve())]==entry['sha256'],key
baseline = records(OLD/'baseline.jsonl')
improved = records(OLD/'p3.jsonl')
current = records(LIVE/'predictions.jsonl')
summaries,details = {},{}
for name,rows,runtime in (('baseline',baseline,reference),('previous_p3',improved,read(OLD/'p3_runtime.json')),('integrated',current,meta)):
    assert len(rows)==386 and {r['image_id'] for r in rows}==set(truth)
    groups = {k:{'total':0,'correct':0} for k in ('full','partial','none')}
    result = []
    for r in rows:
        expected = truth[r['image_id']]
        correct = expected==r['prediction'] and not r['error']
        kind = 'none' if expected=='NONE' else 'partial' if 'NONE' in expected else 'full'
        groups[kind]['total'] += 1
        groups[kind]['correct'] += int(correct)
        result.append({'image_id':r['image_id'],'expected':expected,'prediction':r['prediction'],'correct':bool(correct),'error':r['error'],'kind':kind,'passes':r['passes']})
    times = sorted(r['elapsed_seconds'] for r in rows)
    summaries[name] = {'correct':sum(r['correct'] for r in result),'total':386,'categories':groups,
                       'measurement':runtime.get('measurement','fresh image execution'),
                       'loop_seconds':runtime['loop_wall_seconds'],'total_seconds':runtime['total_wall_seconds'],
                       'median_seconds':median(times),'p95_seconds':times[ceil(len(times)*.95)-1],
                       'errors':sum(bool(r['error']) for r in rows),
                       'ocr_calls':sum(len(r['events']) for r in rows),
                       'passes':dict(Counter(p for r in rows for p in r['passes']))}
    details[name] = {r['image_id']:r for r in result}
changes = {}
for before in ('baseline','previous_p3'):
    a,b = details[before],details['integrated']
    changes[before] = {'gained':[key for key in a if not a[key]['correct'] and b[key]['correct']],
                       'lost':[key for key in a if a[key]['correct'] and not b[key]['correct']]}
with (LIVE/'submission.csv').open(encoding='utf-8',newline='') as source:
    reader = csv.DictReader(source)
    assert reader.fieldnames==['image_id','year','month','day','final_date']
    outputs = list(reader)
assert len(outputs)==386
for row in outputs:
    value = row['final_date']
    assert value==details['integrated'][row['image_id']]['prediction']
    assert value=='NONE' and all(row[k]=='NONE' for k in ('year','month','day')) or '-'.join(row[k] for k in ('year','month','day'))==value
paired = []
for previous,actual in zip(baseline,current):
    assert previous['image_id']==actual['image_id']
    a,b = previous['events'][0],actual['events'][0]
    assert a['input_sha256']==b['input_sha256'] and a['shape']==b['shape']
    paired.append({'same_lines':a['lines']==b['lines'],'time_ratio':b['ocr_seconds']/a['ocr_seconds']})
result = {'summary':summaries,'changes':changes,'details':details,'originals_unchanged':integrity,
          'source_config_weights_images_verified':True,'submission_contract_verified':True,
          'first_pass_control':{'pairs':len(paired),'same_lines':sum(r['same_lines'] for r in paired),
                                'median_integrated_over_baseline_time_ratio':(None if meta.get('cache_sources') else median(r['time_ratio'] for r in paired)),
                                'timing_comparable':not bool(meta.get('cache_sources'))},
          'limitations':['Development set; not blind','Historical reference runs reused','Not an official 4-vCPU/500-image benchmark']}
(OUT/args.out_name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False,indent=2))
