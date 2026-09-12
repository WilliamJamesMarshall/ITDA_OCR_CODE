"""Final classification corrections from directly inspected crop sheets."""
from scripts.remaining_visual_batch_007 import rows,edit,full,partial
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH
from scripts.remaining_visual_review import apply
rows.clear()
for n,rs in {587:[0],665:[0,2],717:[0],763:[0],777:[1],790:[0,1,3,4,5],820:[1],832:[0,1,2,3],862:[0],1078:[0],1103:[1],1196:[1],1350:[0],1411:[1],1431:[1]}.items():
    for r in rs:edit(n,f'deep_{r:03d}',kind='other',role='other',role_evidence='AI가 확대 이미지에서 확인: 영양성분/바코드/연락처/설명문, 날짜 아님.')
edit(832,'deep_004',kind='header',role='expiry',role_evidence='소비기한 표시방법 안내문')
edit(904,'deep_001',kind='time',transcription='06:17:28',time_text='06:17:28')
full(1372,'deep_000','20.08.13 F1')
partial(1394,'deep_000','004CG4CB19 BB 12/2020')
partial(1394,'deep_001','9 BB12/2020')
partial(1400,'deep_000','05-2021(B)')
edit(1400,'deep_001',kind='lot',transcription='LE147 15:20',time_text='15:20',lot_text='LE147')
full(1411,'deep_000','04/08/2023')
partial(1451,'deep_000','016CM4CB19 BB 03/2021')
partial(1451,'deep_001','BB 03/2021')
partial(1468,'deep_000','08/2021')
edit(1468,'deep_001',kind='header',role='expiry',role_evidence='제품 별도표시 월/년 읽는법 안내')
if __name__=='__main__':
    p=BATCH/'visual_009.json';ann.write(p,list(rows.values()));apply(p)
