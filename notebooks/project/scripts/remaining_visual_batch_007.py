"""Explicit visual transcriptions from inspected remaining-cohort crop sheets."""
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH
from scripts.remaining_visual_review import apply

rows={}
def edit(n,region,**values):
    image_id=('BMLC' if n>=2247 else 'AMLC')+f'{n:06d}'
    entry=rows.setdefault(image_id,dict(image_id=image_id,evidence='AI 확대 이미지 직접 판독 초안. 사람 승인 아님.',regions=[]))
    entry['regions'].append(dict(region_id=region,**values))
def full(n,region,text,role=None):
    values=dict(transcription=text,field_states=dict(year='present',month='present',day='present'))
    if role: values.update(role=role,role_evidence='AI 시각 초안: 인쇄 표제/까지 확인')
    edit(n,region,**values)
def partial(n,region,text):
    edit(n,region,transcription=text,field_states=dict(year='present',month='present',day='absent'))

for n,rs in {61:[0],191:[0,2],203:[1],210:[0,1],233:[1],287:[0],305:[0,1],361:[0],368:[0],370:[0],373:[0,1,2],1739:[1,2,3],1741:[0,2],2183:[1]}.items():
    for r in rs: edit(n,f'deep_{r:03d}',kind='other',role='other',role_evidence='AI 시각 초안: 날짜가 아닌 로고/영양성분/전화번호/설명문')
full(119,'supplement_000','2026.08.24')
full(153,'supplement_001','EXP:2026/10/12 BA','expiry')
full(182,'deep_000','01 10 2026')
full(208,'deep_000','4.13.2026/B-V')
full(212,'deep_000','2026.12.16까지','expiry')
full(229,'deep_000','2025.10.28까지','expiry')
full(247,'deep_000','BBD:20/05/2026 YVT 05','expiry')
full(377,'recovery_000','2026.07.01까지\n17:00 6/안성호','expiry')
edit(624,'ocr_010',kind='other',transcription='까지 8 8010',role='other',role_evidence='AI 시각 초안: 표제 조각과 바코드 숫자')
edit(846,'supplement_015',kind='other',role='other',role_evidence='AI 시각 초안: 유통기한 표시 읽는 법 설명문')
full(838,'supplement_000','EXP FEB 21 26 K1 1','expiry')
partial(1413,'cache_000','BEST BY JUL 2022')
# Restore the unrelated region accidentally selected in visual_004.
old=ann.read(BATCH/'before/AMLC001413.json')
original=next(r for r in old['regions'] if r['region_id']=='cache_015')
edit(1413,'cache_015',**{k:original[k] for k in ('transcription','field_states','role','role_evidence','kind')})
partial(1813,'deep_000','12/2021 120154 08:38')
partial(1820,'deep_000','L30408J 04-2023')
partial(1820,'deep_001','04-2023')
partial(1835,'deep_000','11.2022 L10452 a')
full(1838,'deep_000','01.07.2021')
partial(1901,'deep_000',':12.2020')
partial(1901,'deep_001','(17) S.K.T. :12.2020')
edit(1943,'deep_000',kind='lot',transcription='B12 05:50',time_text='05:50',lot_text='B12')
partial(1952,'deep_000','06.2023 L164A')
full(1963,'deep_000','02/03/2023')
edit(1964,'deep_000',kind='lot',transcription='L20238',lot_text='L20238')
full(2015,'deep_000','2021.10.8 까지02','expiry')
full(2060,'deep_000','21 11 2022 PX')
edit(2126,'deep_000',kind='lot',transcription='L010276 141000',lot_text='L010276 141000')
edit(2126,'deep_001',kind='lot',transcription='L010276',lot_text='L010276')
full(2153,'deep_000','12.10.2025')
partial(2155,'deep_000','EXP 10/2021')
partial(2170,'deep_000','BEST BY 07/2022 0068')
partial(2174,'deep_000','11/2022-L103190 1112')
partial(2183,'deep_000','04/2023-L5011901716')
full(2196,'deep_000','31 10 2021')
partial(2217,'deep_000','03/2025')

for n,r,text in [(2258,1,'EXP'),(2265,2,'A'),(2298,2,'D'),(2348,1,'13:59'),(2360,2,'C'),(2410,2,'D'),(2416,1,'제조'),(2438,1,'E'),(2443,2,'A'),(2452,1,'까지'),(2457,1,'A'),(2459,1,'L'),(2473,1,'EXP'),(2513,1,'EXP'),(2536,2,'A'),(2577,1,'BY'),(2590,0,'22:23'),(2596,1,'까지'),(2603,2,'07:23'),(2604,2,'11:15'),(2605,2,'까지')]:
    edit(n,f'source_{r:03d}',transcription=text,legibility='readable')

if __name__=='__main__':
    path=BATCH/'visual_007.json'
    ann.write(path,list(rows.values()))
    apply(path)
