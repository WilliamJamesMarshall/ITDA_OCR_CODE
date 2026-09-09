"""Scoring is separate from image inference. Preserves source template columns."""
import csv
import json
import hashlib
from collections import Counter
from pathlib import Path
from math import ceil
from statistics import median

OUT = Path(__file__).resolve().parent
LABELS = OUT.parents[1]
manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
truth = json.loads((OUT/'ground_truth.json').read_text(encoding='utf-8'))
stages = ['baseline','baseline_replay','p1_replay','p2_replay','p3_replay','p3']
result = {}
detail = {}
for stage in stages:
    path = OUT/f'{stage}.jsonl'
    if not path.exists():
        continue
    predictions = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    if len(predictions) != len(truth):
        continue
    lookup = {r['image_id']:r for r in predictions}
    assert set(lookup) == {r['image_id'] for r in truth}
    csvrows, rows = [], []
    groups = {k:Counter() for k in ('full','partial','none')}
    errors = Counter()
    for source in truth:
        image_id, expected = source['image_id'], source['truth']
        p = lookup[image_id]
        observed = p['prediction']
        # Runtime failures remain failures, including when the expected answer is NONE.
        equal = observed == expected and not p['error']
        kind = 'none' if expected=='NONE' else 'partial' if 'NONE' in expected else 'full'
        error = '' if equal else '실행 오류' if p['error'] else '오검출' if expected=='NONE' else '미검출' if observed=='NONE' else '부분 날짜 불일치' if kind=='partial' else '날짜 불일치'
        groups[kind]['total'] += 1
        groups[kind]['correct'] += int(equal)
        if error:
            errors[error] += 1
        note = f'{p["elapsed_seconds"]:.3f}s; {len(p["passes"])} passes'
        if 'replay' in stage:
            note = 'OCR 재사용·후처리만 측정; ' + note
        csvrows.append([int(image_id), observed if not p['error'] else 'ERROR', expected,
                        'True' if equal else 'False','평가 완료' if not p['error'] else '실행 오류','',error,note])
        rows.append({'image_id':image_id,'truth':expected,'prediction':observed,'correct':bool(equal),'kind':kind,'error_type':error,'seconds':p['elapsed_seconds'],'reason':p['reason'],'passes':p['passes']})
    filename = f'validation_003355_003740_{stage}_20260910.csv'
    with (LABELS/filename).open('w',encoding='utf-8-sig',newline='') as output:
        writer = csv.writer(output,lineterminator='\n')
        writer.writerow(manifest['headers'])
        writer.writerows(csvrows)
    runtimefile = OUT/f'{stage}_runtime.json'
    runtime = json.loads(runtimefile.read_text(encoding='utf-8')) if runtimefile.exists() else {}
    times = sorted(r['seconds'] for r in rows)
    n = len(rows)
    correct = sum(r['correct'] for r in rows)
    rate = correct/n
    result[stage] = {'total':n,'correct':correct,'incorrect':n-correct,'accuracy':rate,
                     'categories':groups,'error_types':errors,
                     'sum_image_seconds':sum(times),'median_image_seconds':median(times),
                     'p95_image_seconds':times[ceil(n*.95)-1],'runtime':runtime,
                     'pass_counts':dict(Counter(p for r in rows for p in r['passes']))}
    if 'replay' not in stage:
        ocr_seconds = sum(e['ocr_seconds'] for r in predictions for e in r['events'])
        result[stage]['ocr_call_and_input_hash_seconds'] = ocr_seconds
        result[stage]['other_image_work_seconds'] = sum(times)-ocr_seconds
    detail[stage] = {'rows':csvrows,'records':rows,'csv':filename}
checks = {path:hashlib.sha256(Path(path).read_bytes()).hexdigest()==value for path,value in manifest['sources'].items()}
assert all(checks.values()), 'Original source changed during evaluation.'
(OUT/'scores.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'workbook_data.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'integrity.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:{'correct':v['correct'],'total':v['total'],'accuracy':v['accuracy'],'categories':v['categories']} for k,v in result.items()},ensure_ascii=False,indent=2))
