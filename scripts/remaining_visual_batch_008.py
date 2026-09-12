"""AI visual fixes based on expanded context sheets; never human approval."""
from scripts.remaining_visual_batch_007 import rows,edit,full,partial
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH
from scripts.remaining_visual_review import apply
rows.clear()
for n,rs in {429:[0,1],441:[0,1,2],486:[0],537:[0,1],549:[0,1],1479:[1,2],1494:[0],1515:[1,2],1545:[1,2,3],1613:[1,2],1738:[0,1],2243:[1]}.items():
    for r in rs: edit(n,f'deep_{r:03d}',kind='other',role='other',role_evidence='확대 문맥에서 확인한 주소/성분/설명/바코드. 날짜 아님.')

# Expansion uses original polygon bounds, not the previous crop image.
def extend(n,r,text,box,role=None):
    full(n,r,text,role)
    rows[('BMLC' if n>=2247 else 'AMLC')+f'{n:06d}']['regions'][-1]['relative_crop']=box

extend(53,'deep_000','2025.12.20까지',[-1.2,-.1,1.15,1.1],'expiry')
extend(191,'deep_001','2026.06.15까지',[-.05,0,1.05,1.9],'expiry')
extend(202,'deep_000','2027.02.06',[-.05,-.1,1.6,1.1])
extend(378,'deep_000','29 05 2026 B1',[-.8,-.1,1.05,1.1])
extend(428,'deep_000','26.04.23까지',[-.8,-.15,1.5,1.15],'expiry')
extend(473,'ocr_012','2026.03.01',[-.05,-.15,1.5,1.15])
full(481,'deep_000','2026.03.09')
extend(596,'recovery_000','2026.08.13.B1',[-.05,-.1,1.75,1.1])
extend(710,'ocr_005','2025.10.14까지.F3',[-2.5,-.1,1.05,1.1],'expiry')
extend(937,'ocr_005','07 SEP 21',[-.05,-.1,1.55,1.1])
partial(1134,'cache_052','12.2020-13:28/1819011')
partial(1136,'cache_042','04.2021-10:13/1906064')
extend(1159,'recovery_000','2022.01.28',[0,0,1,.59],'expiry')
edit(1159,'visual_lot',from_region='recovery_000',relative_crop=[.5,.5,1,1],kind='lot',transcription='00658',legibility='readable',lot_text='00658')
extend(1215,'cache_018','2021.06.24',[-.05,-.1,1.55,1.1])
full(1239,'cache_008','PROD:29/09/2020\nEXP:28/09/2022 202T02')
extend(1250,'cache_011','23 APR 2020',[-.05,-.1,1.9,1.1])
partial(1471,'cache_030','09.2021-14:35/1914619')
full(1479,'deep_000','2021.12.28')
full(1496,'deep_000','19-03-2022')
partial(1515,'deep_000','12 2021')
full(1517,'deep_000','2022.06.22 L30')
partial(1519,'deep_000','02/2023')
full(1545,'deep_000','EXP:01 09 2020','expiry')
extend(1555,'cache_001','24 APR/21',[-.55,-.1,1.1,1.1])
edit(1582,'deep_001',kind='header',role='expiry',role_evidence='소비기한 용기상단 표시일까지 안내')
extend(1601,'recovery_004','2020.06.11',[-.05,-.1,1.65,1.1])
partial(1643,'deep_000','07.2022')
extend(1703,'deep_000','01 JUL 2020',[-.05,-.1,1.65,1.1])
partial(1713,'deep_000','04.2022')
partial(1952,'deep_001','06.2023 L164A')
extend(2037,'cache_002','2022.10.15',[-.05,-.1,1.6,1.1])
extend(2053,'cache_017','2021.11.01',[-.05,-.1,1.25,1.1])
extend(2160,'recovery_003','BEST BY AUG 11 2021',[-.05,-.1,1.35,1.1],'expiry')
extend(2220,'deep_001','11.03.2021',[-.5,-.1,1.05,1.1])

if __name__=='__main__':
    path=BATCH/'visual_008.json';ann.write(path,list(rows.values()));apply(path)
