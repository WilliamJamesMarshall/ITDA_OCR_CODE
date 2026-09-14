"""Expose only already-fixed validation crops, without creating field truth."""
import json
from pathlib import Path

BASE=Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
carry=json.loads((BASE/'groups/group_01/historical_carryover.json').read_text(encoding='utf-8'))
samples=[s for s in carry['samples'] if carry['group_roles'][s['group_id']]=='inner_validation']
lines=['# 기존 내부 검증 crop 필드 확인','',
       f'기존에 역할이 고정된 내부 검증 crop은 {len(samples)}개입니다.',
       '현재 전사는 참고일 뿐입니다. crop에 실제 인쇄된 연·월·일을 확인해 확정해야 합니다.',
       '날짜가 없는 crop은 세 필드가 모두 NONE인지 확인합니다. 정답을 자동 생성하지 않았습니다.',
       '2·3회 신규 내부 검증 crop은 상품 그룹 검토 후 별도로 정합니다.','',
       '| 원본 | 현재 전사 | crop | 연 | 월 | 일 |','|---|---|---|---|---|---|']
for s in samples:
    text=s['transcription'].replace('|','\\|').replace('\n',' ')
    lines.append(f"| {s['image_id']} | {text} | [확인](<{Path(s['crop_path']).as_posix()}>) | 미확정 | 미확정 | 미확정 |")
dest=BASE/'paper-ocr-20260914/training-review/historical-validation-review.md'
with dest.open('x',encoding='utf-8') as stream:
    stream.write('\n'.join(lines)+'\n')
print(json.dumps(dict(fixed_validation_crops=len(samples),path=str(dest))))
