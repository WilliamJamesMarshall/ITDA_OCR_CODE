"""Assemble manual full-pass decisions; never write to source images or labels."""
import json,re,hashlib
from pathlib import Path
from datetime import date
from collections import Counter
B=Path(__file__).parent; R=B.parent.parent; S=R/'상품사진입니다'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(name,value): (B/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
manifest=read(B/'manifest.json')
old={int(r['image_id']):r for r in read(R/'artifacts/date-order-audit-20260909/reviewed.json')}
zooms={int(k):v for k,v in read(B/'zoom_review_final3.json').items()}
states={}; raw={}; notes={}; batches={}
for f in sorted(B.glob('batch_*.json')):
 b=read(f)
 for n in range(b['range'][0],b['range'][1]+1):
  assert n not in states
  states[n]='not_ambiguous_candidate';batches[n]=f.name
 for k in ['ambiguous','explicit','partial','pending','nonexpiry','nonfood']:
  for n in map(int,b.get(k,'').split()):states[n]=k
 raw.update({int(k):v for k,v in b.get('raw',{}).items()})
 notes.update({int(k):v for k,v in b.get('notes',{}).items()})
assert set(states)==set(range(1,3353))
def interpretations(raw):
 nums=re.findall(r'\d+',raw or '')
 if len(nums)==1 and len(nums[0])==6:nums=[nums[0][j:j+2] for j in (0,2,4)]
 if len(nums)!=3:return {}
 a,b,c=map(int,nums);out={}
 configs=[]
 if len(nums[0])==4:configs=[('ymd',(a,b,c))]
 elif len(nums[2])==4:configs=[('dmy',(c,b,a)),('mdy',(c,a,b))]
 elif all(len(x)<=2 for x in nums):configs=[('ymd',(2000+a,b,c)),('dmy',(2000+c,b,a)),('mdy',(2000+c,a,b))]
 for k,v in configs:
  try:out[k]=date(*v).isoformat()
  except ValueError:pass
 return out
records=[];unknown=[];conflicts=[]
for m in manifest:
 n=int(m['id']);o=old.get(n,{});z=zooms.get(n,{})
 st=z.get('status',states[n]);text=z.get('raw') or raw.get(n) or o.get('raw')
 note=z.get('note') or notes.get(n) or o.get('note') or ''
 order=z.get('order')
 if st=='ambiguous' and order is None:
  os=o.get('status','')
  if os.endswith('_context'):order=os.split('_')[0]
  elif os=='hold':order='hold'
  elif os.endswith('_explicit'):
   conflicts.append([n,text,os,note]);st='explicit_previous_evidence'
  else:order='hold';unknown.append([n,text,os,note])
 dates=interpretations(text)
 if st=='ambiguous' and len(set(dates.values()))<2:
  unknown.append([n,text,'invalid_or_single_candidate',dates])
 if st=='ambiguous' and order not in dates and order!='hold':
  unknown.append([n,text,'recommended_order_invalid',order,dates])
 rec={**m,'image_id':m['id'],'status':st,'raw':text,'interpretations':dates,'recommendation':order if st=='ambiguous' else None,'recommended_date':dates.get(order) if st=='ambiguous' else None,'evidence_level':'context_not_ground_truth' if st=='ambiguous' and order!='hold' else 'hold' if st=='ambiguous' else None,'note':note,'full_pass_batch':batches[n],'zoom_review':n in zooms,'date_kind':'expiry_or_best_before_or_sellby' if st=='ambiguous' else None}
 records.append(rec)
save('inspection_ledger.json',records)
save('assembly_checks.json',{'unknown':unknown,'explicit_conflicts':conflicts,'statuses':dict(Counter(r['status'] for r in records))})
print('CHECK',json.dumps({'unknown':unknown,'explicit_conflicts':conflicts},ensure_ascii=False))
print('STATUS',Counter(r['status'] for r in records)); print('ORDER',Counter(r['recommendation'] for r in records if r['status']=='ambiguous'))
