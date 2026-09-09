"""Conservative, auditable OCR-based origin screening, NOT ground-truth labels."""
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parent
COUNTRIES = {
 '대한민국': r'대한민국|국내산|한국산|KOREA|원산지[: ]*국내',
 '이탈리아': r'이탈리아|이탈리데|이탈리이|이탁리아|이달리아|이태리|ITALY|ITALIA',
 '폴란드': r'폴란드|플란드|POLAND|POLSKA', '중국': r'중\s*국|CHINA',
 '일본': r'일본|JAPAN', '미국': r'미국|U\.?S\.?A\.?\b|UNITED STATES',
 '캐나다': r'캐나다|CANADA', '호주': r'호주|AUSTRALIA|AUSTRALA|TASMANIA',
 '오스트리아': r'오스트리아|AUSTRIA', '말레이시아': r'말레이시아|말레이지아|MALAYSIA',
 '태국': r'태국|THAILAND|THALLAND', '베트남': r'베트남|VIETNAM', '대만': r'대만|TAIWAN',
 '스페인': r'스페인|SPAIN|ESPANA', '독일': r'독일|GERMANY|GEMANY|DEUTSCHLAND',
 '프랑스': r'프랑스|FRANCE', '벨기에': r'벨기에|BELGIUM',
 '네덜란드': r'네덜란드|네얼란드|NETHERLANDS|HOLLAND', '덴마크': r'덴마크|DENMARK',
 '뉴질랜드': r'뉴질랜드|NEW\s*ZEALAND', '튀르키예': r'튀르키예|터키|TURKEY|TURKIYE',
 '인도네시아': r'인도네시아|INDONESIA', '필리핀': r'필리핀|PHILIPPINES',
 '스위스': r'스위스|SWITZERLAND|SCHWEIZ', '영국': r'영국|UNITED KINGDOM|\bUK\b|(?<!NEW )ENGLAND|ENGIAND',
 '포르투갈': r'포르투갈|PORTUGAL', '싱가포르': r'싱가포르|SINGAPORE',
 '멕시코': r'멕시코|MEXICO', '페루': r'페루|PERU', '인도': r'인도(?!네)|\bINDIA\b',
 '그리스': r'그리스|GREECE', '핀란드': r'핀란드|FINLAND',
 '아일랜드': r'아일랜드|IRELAND', '리투아니아': r'리투아니아|LITHUANIA',
 '브라질': r'브라질|BRAZIL', '아르헨티나': r'아르헨티나|ARGENTINA',
 '크로아티아': r'크로아티아|크로아티이|CROATIA',
 '아랍에미리트': r'아랍에미리트|UN(?:IT|IR)ED ARAB EMIRATES',
 '몰도바': r'몰도바|MOLDOVA',
 '루마니아': r'루마니아|ROMANIA',
}
ORIGIN = re.compile(r'원산지|원신지|산지/제조사|제조국|made\s*in|product\s*of|imported\s*from|country\s*of',re.I)
MAKER = re.compile(r'제조원|제조업소|제조회사|제조사[: ]|제조및|제조 및|[가-힣]+공장',re.I)
ADDRESS = re.compile(r'경기도|경상[남북]도|충청[남북]도|전라[남북]도|전북|충북|충남|경북|경남|전남|강원|제주|[가-힣]+광역시|[가-힣]+특별자치도')
STOP = re.compile(r'수입|소분|유통전문|판매원|고객|상담|반품|교환')
DATE_PATTERNS = {
 'YMD': r'(?:년|연)[\s/,.\-·]*(?:월)[\s/,.\-·]*일|Y{2,4}[\s/.-]*M{2}[\s/.-]*D{2}',
 'DMY': r'일[\s/,.\-·]*월[\s/,.\-·]*(?:년|연)|D{1,2}[\s/.-]*M{2}[\s/.-]*Y{2,4}',
 'MDY': r'월[\s/,.\-·]*일[\s/,.\-·]*(?:년|연)|M{2}[\s/.-]*D{2}[\s/.-]*Y{2,4}',
}

def country_hits(text):
 return [name for name, pattern in COUNTRIES.items() if re.search(pattern,text,re.I)]

def classify(r):
 lines = [x['text'] for x in r.get('lines',[])]
 result = {'image_id':r['image_id'],'filename':r['filename'],'country':'미확정',
           'method':'insufficient_evidence','evidence':[], 'visual_review':False,
           'date_order_explicit':[],'date_evidence':[], 'country_candidates':[],
           'product_scope':'nonfood_candidate' if re.search(r'치실|마스크|콘택트|렌즈|의약외품|Alcon|일회용밴드|칫솔',' '.join(lines),re.I) else 'not_reviewed'}
 for t in lines:
  for order,pattern in DATE_PATTERNS.items():
   if re.search(pattern,t,re.I) and (re.search(r'순|읽는|DD|YY|MM',t,re.I) or re.fullmatch(r'[년연월일 /.,·-]+',t)):
    result['date_order_explicit'].append(order)
    result['date_evidence'].append(t)
 result['date_order_explicit']=sorted(set(result['date_order_explicit']))
 hits=[]
 for i,t in enumerate(lines):
  if not ORIGIN.search(t): continue
  if re.search(r'완구|\btin\b|\bcan\b|원재료|원료원산지|원료및',t,re.I): continue
  if '완구' in ''.join(lines[max(0,i-1):i+3]): continue
  # Country words in the origin field, not arbitrary ingredient paragraphs.
  direct=t[ORIGIN.search(t).start():]
  countries=country_hits(direct)
  evidence=t
  if not countries and len(direct)<35:
   for j in [i+1,i-1,i+2,i+3,i+4]:
    if not 0<=j<len(lines): continue
    candidate=lines[j]
    if len(candidate)>35 or re.search(r'원재료|함유|수입|판매|소분',candidate): continue
    nearby=country_hits(candidate)
    if nearby:
     countries=nearby; evidence=t+' | '+candidate; break
  if len(countries)==1:
   hits.append((countries[0],evidence))
 if len({x[0] for x in hits})==1:
  result.update(country=hits[0][0],method='origin_text_ocr',evidence=[x[1] for x in hits])
 elif hits:
  result.update(method='conflicting_origin',evidence=[x[1] for x in hits])
 if result['country']=='미확정' and not hits:
  for i,t in enumerate(lines):
   if not MAKER.search(t) or re.search(r'구입처|교환|동일한|같은|제조시설|소분',t): continue
   # Only a local factory/manufacturer address, never a sales/import office alone.
   context=[t[MAKER.search(t).start():]]
   if i and ADDRESS.search(lines[i-1]) and not STOP.search(lines[i-1]): context.insert(0,lines[i-1])
   for follow in lines[i+1:i+4]:
    if STOP.search(follow): break
    context.append(follow)
   joined=' | '.join(context)
   if ADDRESS.search(joined) and not re.search(r'수입|유통전문',joined):
    result.update(country='대한민국',method='manufacturer_address_inference',evidence=[joined]); break
 if result['country']=='미확정' and not hits and not re.search(r'수입|소분',' '.join(lines)):
  for i,t in enumerate(lines):
   if not re.search(r'품목(?:제조)?보고번호',re.sub(r'\s','',t)):continue
   context=' | '.join(lines[max(0,i-1):i+3])
   if re.search(r'\d{9,}',re.sub(r'\s','',context)):
    result.update(country='대한민국',method='domestic_item_report_inference',evidence=[context]);break
 result['country_candidates']=sorted(set(c for t in lines for c in country_hits(t)))
 return result

def main():
 raw=[json.loads(t) for t in (BASE/'ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines()]
 rows=[classify(r) for r in sorted(raw,key=lambda r:r['image_id'])]
 overrides=json.loads((BASE/'manual_review.json').read_text(encoding='utf-8')) if (BASE/'manual_review.json').exists() else {}
 for row in rows:
  if row['image_id'] in overrides: row.update(overrides[row['image_id']])
 (BASE/'country_screening.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 print('TOTAL',len(rows),'ERRORS',sum('error'in r for r in raw))
 print(json.dumps(Counter(r['country'] for r in rows),ensure_ascii=False))
 print(json.dumps(Counter(r['method'] for r in rows),ensure_ascii=False))
 print('DATE_GUIDES',dict(Counter(','.join(r['date_order_explicit']) for r in rows)))
 if __import__('sys').argv[-1]=='--list':
  for r in rows:
   if r['country']!='미확정':print(r['image_id'],r['country'],r['method'],' :: ',' | '.join(r['evidence']))

if __name__=='__main__': main()
