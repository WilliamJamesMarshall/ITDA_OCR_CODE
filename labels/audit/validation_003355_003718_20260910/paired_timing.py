"""Same-input, unchanged first OCR pass is a timing comparability control."""
import json
from pathlib import Path
from statistics import median
OUT=Path(__file__).resolve().parent
def read(stage):
    return {r['image_id']:r for r in map(json.loads,(OUT/f'{stage}.jsonl').read_text(encoding='utf-8').splitlines())}
a,b=read('baseline'),read('p3')
assert len(a)==len(b)== 364
paired=[]
for key in a:
    left,right=a[key]['events'][0],b[key]['events'][0]
    assert left['input_sha256']==right['input_sha256']
    assert left['shape']==right['shape'] and left['detector']==right['detector'] and left['variant']==right['variant']
    same=[x['text'] for x in left['lines']]==[x['text'] for x in right['lines']]
    paired.append({'image_id':key,'same_input':True,'same_text':same,'same_lines':left['lines']==right['lines'],
                   'baseline_seconds':left['ocr_seconds'],'p3_seconds':right['ocr_seconds'],
                   'ratio':right['ocr_seconds']/left['ocr_seconds']})
result={'pairs':len(paired),'same_text_count':sum(x['same_text'] for x in paired),
        'same_full_ocr_lines_count':sum(x['same_lines'] for x in paired),
        'median_p3_over_baseline_ratio':median(x['ratio'] for x in paired),
        'baseline_original_seconds':sum(x['baseline_seconds'] for x in paired),
        'p3_original_seconds':sum(x['p3_seconds'] for x in paired),
        'details':paired}
(OUT/'paired_timing.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print({k:v for k,v in result.items() if k!='details'})
