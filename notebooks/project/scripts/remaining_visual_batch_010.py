"""Last context-verified draft corrections; never grants human approval."""
from scripts.remaining_visual_batch_007 import rows,edit,full
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH
from scripts.remaining_visual_review import apply
rows.clear()
for n,rid,text in [(2248,'source_003','18:52'),(2336,'source_002','까지'),(2429,'source_001','까지'),(2477,'source_001','EXP'),(2505,'source_002','EXP'),(2588,'source_001','BY')]:
    edit(n,rid,transcription=text,legibility='readable')
edit(2248,'source_003',kind='time',time_text='18:52')
for rid in ['cache_004','cache_006','cache_010']:
    edit(1124,rid,kind='other',role='other',role_evidence='확대 원본 확인: 유통기한 읽는 법의 예시와 영문 월 설명. 실제 상품 날짜 아님.')
for i in range(7):
    edit(831,f'deep_{i:03d}',kind='other',role='other',role_evidence='확대 원본 확인: 영양성분 및 소비기한 표시방법 설명. 실제 날짜 아님.')
edit(1518,'deep_004',kind='time',role='other',role_evidence='확대 원본 확인: 시각 문자열 조각')
edit(821,'deep_002',kind='lot',role='other',role_evidence='날짜 아래 생산 코드 및 시각 행')
for rid in ['deep_000','deep_002']:
    edit(824,rid,field_states=dict(year='absent',month='present',day='present'))
full(488,'ocr_066','2026. 02. 27까지')
if __name__=='__main__':
    p=BATCH/'visual_010.json';ann.write(p,list(rows.values()));apply(p)
