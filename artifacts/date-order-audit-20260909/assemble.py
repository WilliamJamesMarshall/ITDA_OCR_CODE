"""Combine visual review decisions and validate coverage without touching source data."""
import json,re
from pathlib import Path
from datetime import date
from collections import Counter
BASE=Path(__file__).parent;ROOT=BASE.parent.parent
ocr={r['image_id']:r for r in map(json.loads,(ROOT/'artifacts/country-date-report-20260909/ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines())}
candidates={r['image_id']:r for r in json.loads((BASE/'candidates.json').read_text(encoding='utf-8'))}
extra=json.loads((BASE/'extra_queue.json').read_text(encoding='utf-8'))
states={};overrides={};notes={}
keys=['ymd_context','ymd_explicit','dmy_context','dmy_explicit','mdy_explicit','hold']
for f in [BASE/'review_log.json']+sorted(BASE.glob('review_[0-9]*.json')):
 r=json.loads(f.read_text(encoding='utf-8'))
 for k in keys:
  for i in r.get(k,'').split():states[i.zfill(6)]=(k,f.name)
 for i,reason in r.get('exclude',{}).items():states[i.zfill(6)]=('exclude',f.name);notes[i.zfill(6)]=reason
 for i,v in r.get('raw_overrides',{}).items():overrides[i.zfill(6)]=v
 for i,v in r.get('notes',{}).items():notes[i.zfill(6)]=v
missing=sorted((set(candidates)|set(extra))-set(states));print('MISSING',missing)
assert not missing
assert len(ocr)==3352
results=[]
for i,(status,origin) in sorted(states.items()):
 raw=overrides.get(i)
 if raw is None and i in candidates:raw=candidates[i]['hits'][0]['raw']
 dates={}
 if raw:
  nums=re.findall(r'\d+',raw)
  if len(nums)==1 and len(nums[0])==6:nums=[nums[0][j:j+2] for j in (0,2,4)]
  if len(nums)==3 and all(len(n)<=2 for n in nums):
   a,b,c=map(int,nums)
   for label,tup in [('ymd',(2000+a,b,c)),('dmy',(2000+c,b,a)),('mdy',(2000+c,a,b))]:
    try:dates[label]=date(*tup).isoformat()
    except ValueError:pass
 record={'image_id':i,'filename':ocr[i]['filename'],'status':status,'raw':raw,'interpretations':dates,'note':notes.get(i,''),'review_file':origin,'date_kind':'manufacture' if i in ['002432','002433'] else 'expiry_or_best_before'}
 if i=='000234':record['date_kind']='non_food'
 if i in ['002025','002026']:record['date_kind']='date_kind_unconfirmed'
 if not record['note'] and status.endswith('_context'):
  record['note']='포장의 국내 유통용 기한/까지/부터 표기 및 제품 문맥으로 YMD 권고. 형식 명시는 확인되지 않음.' if status.startswith('ymd') else '원포장 기한 문구와 제품/판매시장 문맥으로 DMY 권고. 형식 명시는 확인되지 않음.'
 if not record['note'] and status.endswith('_explicit'):
  hint=candidates.get(i,{}).get('order_evidence',[])
  record['note']='원본 포장의 형식 안내 또는 동일 제품의 대응 라벨 확인.'+(' OCR 보조 근거: '+str(hint) if hint else '')
 if not record['note'] and status=='hold':record['note']='날짜 숫자는 보이지만 포장에 날짜 순서·판매시장·대응 날짜를 확정할 근거가 부족함.'
 results.append(record)
 if status!='exclude' and (not {'ymd','dmy'}<=dates.keys() or dates['ymd']==dates['dmy']):print('CHECK RAW',i,status,raw,dates)
(BASE/'reviewed.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('COUNTS',Counter(r['status'] for r in results),'reviewed',len(results),'queue',len(candidates)+len(extra))
print('HOLD',[(r['image_id'],r['raw']) for r in results if r['status']=='hold'])

main=[r for r in results if r['status']!='exclude' and r['date_kind'] not in ['manufacture','non_food']]
appendix=[r for r in results if r['status']!='exclude' and r['date_kind'] in ['manufacture','non_food']]
groups=[('년월일','년-월-일 권고',[r for r in main if r['status'].startswith('ymd')]),('일월년','일-월-년 권고',[r for r in main if r['status'].startswith('dmy')]),('월일년','월-일-년 확인',[r for r in main if r['status'].startswith('mdy')]),('판정보류','판정보류',[r for r in main if r['status']=='hold'])]
counts={key:len(rows) for key,title,rows in groups}
summary={'ocr_screened':len(ocr),'visually_reviewed_candidates':len(results),'not_visually_reviewed':len(ocr)-len(results),'main_candidates':len(main),'counts':counts,'appendix':len(appendix),'excluded_after_visual_review':sum(r['status']=='exclude' for r in results),'completeness_guaranteed':False}
(BASE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
def link(path,label):return f'[{label}](<{path.as_posix()}>)'
def table(rows):
 out=['| 일련번호 / 원본 | 인쇄 날짜 | YMD 후보 | DMY 후보 | 권고 날짜 | 근거 수준 | 판독 근거 |','|---|---|---|---|---|---|---|']
 for r in rows:
  d=r['interpretations'];s=r['status'];order=s.split('_')[0]
  level='형식/대응 날짜 확인' if s.endswith('_explicit') else '문맥 권고·미확정' if s.endswith('_context') else '보류'
  selected=d.get(order,'확정하지 않음')
  note=r['note'].replace('|','/').replace('\n',' ')
  if r['date_kind']=='manufacture':note='[제조일, 소비기한 아님] '+note
  if r['date_kind']=='date_kind_unconfirmed':note='[날짜 종류 미확인] '+note
  if r['date_kind']=='non_food':note='[비식품] '+note
  out.append('| '+' | '.join([link(ROOT/'상품사진입니다'/r['filename'],r['image_id']),r['raw'],d.get('ymd','불가'),d.get('dmy','불가'),selected,level,note])+' |')
 return '\n'.join(out)
index=['# 날짜 순서별 일련번호 목록','',f'식품 관련 후보 {len(main)}장. 숫자만 YMD/DMY로 해석하면 서로 다른 두 날짜가 유효한 사진입니다. 형식이 라벨에 명시된 사진도 포함합니다.','', '주의: 이 목록은 전수 OCR 후 후보 원본 검토 결과이며, 전체 3,352장을 육안으로 전수 검수한 확정 정답지가 아닙니다. 문맥 권고는 정답 라벨로 자동 반영하지 마세요.','']
for key,title,rows in groups:
 (BASE/f'{key}_일련번호.txt').write_text('\n'.join(r['image_id'] for r in rows)+'\n',encoding='utf-8')
 detail=f'# {title}: {len(rows)}장\n\n형식/대응 날짜 확인과 문맥 추정을 구분했습니다. 두 자리 연도 후보는 2000+YY로 계산했으며 현재 시각을 기준으로 과거/미래 후보를 제거하지 않았습니다.\n\n'+table(rows)+'\n'
 (BASE/f'{key}_사진별_판독표.md').write_text(detail,encoding='utf-8')
 index += [f'## {title}: {len(rows)}장','',link(BASE/f'{key}_사진별_판독표.md','인쇄 날짜·두 해석·근거·원본 사진 보기'),'']
 for level,label in [('explicit','형식 또는 대응 날짜 확인'),('context','문맥상 권고 — 형식 미확정'),('hold','보류')]:
  subset=[r for r in rows if r['status'].endswith(level)]
  if subset:index += [f'{label} ({len(subset)}장):','',', '.join(r['image_id'] for r in subset),'']
index+=['## 별도 부록 — 제조일 및 비식품','',table(appendix),'']
(BASE/'일련번호_전체목록.md').write_text('\n'.join(index),encoding='utf-8')
excluded=['# 원본 대조 후 제외한 후보','', '전체 OCR/기존 검수표의 두 자리 연도 태그로 후보에 올랐지만 대상이 아닌 사진입니다. 원본 사진은 삭제하지 않았습니다.','', '| 일련번호 | 제외 이유 |','|---|---|']
excluded += ['| '+link(ROOT/'상품사진입니다'/r['filename'],r['image_id'])+' | '+r['note'].replace('|','/')+' |' for r in results if r['status']=='exclude']
(BASE/'제외한_후보와_이유.md').write_text('\n'.join(excluded)+'\n',encoding='utf-8')
report=f'''# 날짜 순서 모호성 검토 결과

검토일: 2026-09-09

## 결과

`C:\\ITDA_OCR_CODE\\상품사진입니다`의 000001–003352, 총 3,352장에 대한 기존 전체 이미지 OCR 결과를 검색하고 후보 700장의 원본/날짜 확대 영역을 육안으로 대조했습니다. 식품 관련 모호 날짜 후보는 **{len(main)}장**입니다.

| 분류 | 사진 수 | 해석의 확실성 |
|---|---:|---|
| 년-월-일 권고 | {counts['년월일']} | 형식/대응 날짜 확인 6장, 나머지는 문맥 권고 |
| 일-월-년 권고 | {counts['일월년']} | 형식/대응 날짜 확인 29장, 나머지는 문맥 권고 |
| 월-일-년 확인 | {counts['월일년']} | 002681·002682, 한글 번역 날짜 대조 |
| 판정보류 | {counts['판정보류']} | 원본만으로 순서를 확정할 근거 부족; 날짜 종류 미확인 포함 |

별도로 제조일만 있는 002432·002433와 비식품(샴푸) 000234를 부록에 남겼습니다. 후보 중 281장은 네 자리 연도·문자 월·시간·제품코드·앞뒤가 같은 날짜 등으로 제외했습니다.

**완전성 제한:** 3,352장 전체를 육안으로 전수 검수한 것은 아닙니다. OCR이 완전히 놓친 날짜, 가려진/번진 날짜, 검수표에 태그가 없는 OCR 누락 사진은 빠졌을 수 있으므로 “모호 사진을 한 장도 빠짐없이 찾았다”는 보증이나 확정 정답지로 사용하면 안 됩니다. 후보 700장의 판정 누락은 0건이며, 채택 날짜의 두 해석은 모두 실제 달력 날짜인지 검증했습니다.

{link(BASE/'일련번호_전체목록.md','전체 일련번호 목록 — 분류별 번호 전부')}

## 요청한 사진

| 일련번호 | 인쇄 날짜 | 권고 순서 | 권고 해석 | 근거 |
|---|---|---|---|---|
| 001975·001976 | TETT 26.02.21 | 일-월-년 | 2021-02-26 | 튀르키예 Knorr, 튀르키예어 TETT 및 제조 표시. 첨부 1은 001976과 일치, 001975는 같은 상품의 다른 사진 |
| 001977 | TETT 14.01.21 | 일-월-년 | 2021-01-14 | 첨부 2와 일치, 튀르키예 Knorr |
| 003172 | 20-06-21 | 일-월-년 | 2021-06-20 | 네덜란드 Beemster 치즈, Imported from Holland/제조자 및 Best before 문맥 |

이 네 사진은 형식 문자가 직접 인쇄된 사례와 구분하여 **제품·표시 문맥에 따른 DMY 권고**로 기록했습니다. 튀르키예 공식 식품표시 자료의 Ek-7은 TETT를 일·월·필요시 년 순으로 설명합니다. [튀르키예 농림부 게시 식품표시 규정](https://istanbul.tarimorman.gov.tr/BelgelerArsiv/SolMenu/RESM%C4%B0%20GAZETE/GidaEtiketlemeYonetmeligi.pdf). TETT는 권장 섭취/품질 유지 기한이며 STT와 구분됩니다. [튀르키예 농림부 안내](https://www.tarimorman.gov.tr/GKGM/Duyuru/516/Gida-Etiketlerinde-Raf-Omru-Bilgisi).

EU 원포장의 Best before/Use by 문맥은 일·월·필요시 년 순서 판단을 뒷받침하지만, 수출용·한국어 별도 라벨에까지 생산국 규칙을 무조건 적용하지 않았습니다. [EU 1169/2011 Annex X](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32011R1169).

## 판독 원칙

1. 숫자 세 묶음(두 자리 연도) 또는 연속 6자리가 YMD와 DMY에서 모두 유효하고 서로 다른 날짜가 되는지를 검사했습니다. 예: 26.02.21 → YMD 2026-02-21 / DMY 2021-02-26.
2. 라벨의 `년월일`, `D/M/Y`, `DD/MM/YY`, `日/月/年` 또는 한글로 풀어 쓴 대응 날짜가 있으면 우선했습니다. 같은 상품의 대응 사진을 근거로 삼은 경우 판독표에 표시했습니다.
3. 형식이 없으면 제품·판매용 포장·기한 문구와 제조/종료일의 관계를 근거로 권고만 했습니다. 국가·브랜드·바코드 앞자리 하나로 확정하지 않았습니다.
4. YMD/DMY를 강제로 이분하지 않았습니다. 002681·002682의 10/09/21은 한글 라벨 `2021년 10월 09일까지`와 일치하는 MDY입니다.
5. 기한과 제조일이 함께 있는 경우 판독표는 기한을 대표 날짜로 기록합니다. 제조일만 확인된 두 사진은 부록입니다. 앞뒤가 같은 21.05.21 등은 YMD/DMY가 같은 날짜라 본 목록에서 제외했습니다.
6. 두 자리 연도의 세기는 이 데이터 비교용으로 2000+YY를 가정했습니다. 촬영 시점을 모르는 상태에서 “지금 이미 지났다” 또는 “너무 먼 미래다”만으로 후보를 탈락시키지 않았습니다.

`karpathy-guidelines`에 따라 확인 근거와 추정을 분리하고, 원본 이미지와 기존 정답 라벨은 변경하지 않았습니다. 분석용 OCR은 기존 `artifacts/country-date-report-20260909/ocr_evidence.jsonl`을 재사용했습니다. 기존 검수표의 JSON 캐시(`labels/validation_000001_003352_manual.xlsx.inspect.ndjson`)는 추가 후보 검색에만 썼고 정답 근거로 쓰지 않았습니다.

## 결과 파일

'''
for key,title,rows in groups:report+=f'- {link(BASE/f"{key}_사진별_판독표.md",title+" 사진별 판독표")} / {link(BASE/f"{key}_일련번호.txt","번호만 있는 TXT")}\n'
report+=f'- {link(BASE/"제외한_후보와_이유.md","제외 후보 및 이유")}\n- {link(BASE/"reviewed.json","기계 판독용 전체 검토 기록(JSON)")}\n'
(BASE/'날짜순서_검토보고서.md').write_text(report,encoding='utf-8')
assert sum(counts.values())==len(main)
assert len({r['image_id'] for r in results})==len(results)
assert all({'ymd','dmy'}<=r['interpretations'].keys() and r['interpretations']['ymd']!=r['interpretations']['dmy'] for r in results if r['status']!='exclude')
print('SUMMARY',summary)
