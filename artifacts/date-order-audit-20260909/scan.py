"""Read-only full-image OCR screening for reversible YMD/DMY dates."""
import json, re
from datetime import date
from pathlib import Path

BASE=Path(__file__).parent
ROOT=BASE.parent.parent
raw={r['image_id']:r for r in map(json.loads,(ROOT/'artifacts/country-date-report-20260909/ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines())}
countries={r['image_id']:r for r in json.loads((ROOT/'artifacts/country-date-report-20260909/country_screening.json').read_text(encoding='utf-8'))}
separated=re.compile(r'(?<![\d.])([0-9]{1,2})\s*[./·\- ]\s*([0-9]{1,2})\s*[./·\- ]\s*([0-9]{2})(?![\d.])')
compact=re.compile(r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)')
def interpretations(a,b,c):
 try:
  ymd=date(2000+a,b,c).isoformat();dmy=date(2000+c,b,a).isoformat()
  return (ymd,dmy) if ymd!=dmy else None
 except ValueError:return None

out=[];symmetric=[]
for image_id,r in sorted(raw.items()):
 hits=[]
 for i,line in enumerate(r['lines']):
  t=line['text']
  for kind,pattern in [('separated',separated),('compact',compact)]:
   for m in pattern.finditer(t):
    nums=list(map(int,m.groups()));parsed=interpretations(*nums)
    if parsed:
     hits.append({'raw':m.group(),'ymd':parsed[0],'dmy':parsed[1],'text':t,'kind':kind,'box':line['box'],'line_index':i,'score':line['score']})
    elif nums[0]==nums[2] and 1<=nums[0]<=31 and 1<=nums[1]<=12:
     symmetric.append({'image_id':image_id,'raw':m.group(),'text':t})
 if hits:
  c=countries[image_id]
  out.append({'image_id':image_id,'filename':r['filename'],'ocr_size':r['ocr_size'],'hits':hits,'country':c['country'],'country_evidence':c['evidence'],'explicit_order':c['date_order_explicit'],'order_evidence':c['date_evidence']})
(BASE/'candidates.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
(BASE/'symmetric.json').write_text(json.dumps(symmetric,ensure_ascii=False,indent=2),encoding='utf-8')
print('OCR images',len(raw),'candidate images',len(out),'hits',sum(len(r['hits']) for r in out),'symmetric hits',len(symmetric))
for r in out:print(r['image_id'],r['country'],','.join(r['explicit_order']),' :: ',' | '.join(h['text'] for h in r['hits']))
