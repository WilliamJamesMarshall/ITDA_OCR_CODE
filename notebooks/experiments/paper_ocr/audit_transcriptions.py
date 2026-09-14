"""Prioritize crop review; image-level expiry is not substituted for crop truth."""
import csv
import json
import sys
from pathlib import Path

ROOT=Path('C:/ITDA_OCR_CODE')
BASE=Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
DEV=BASE/'paper-ocr-20260914'
sys.path.insert(0,str(DEV/'code/notebooks/project'))
from src.date_extraction import parse_dates


def main():
    crops=json.loads((DEV/'training-review/crops.draft.json').read_text(encoding='utf-8'))
    with (BASE/'test_to_original_mapping.csv').open(encoding='utf-8-sig',newline='') as stream:
        originals={r['original_id']:r for r in csv.DictReader(stream) if r['round'] in ('2','3')}
    queue=[]
    records={}
    for crop in crops:
        i=crop['image_id']
        if i not in originals:
            continue
        if i not in records:
            records[i]=json.loads(Path(originals[i]['annotation_path']).read_text(encoding='utf-8-sig'))
        text=crop['transcription']
        if sum(c.isdigit() for c in text)<4 or not any(c in text for c in './-년월일'):
            continue
        parsed=list(parse_dates(text))
        values=sorted({p.value.isoformat() for p in parsed if not p.repaired})
        expiry=records[i]['final_date']
        if expiry in values:
            continue
        queue.append(dict(image_id=i,transcription=text,unrepaired_parses=values,
            image_expiry=expiry,original_path=originals[i]['original_path'],crop_path=crop['crop_path'],
            reason='no_unrepaired_date' if not values else 'different_from_image_expiry',
            review_status='pending',warning='Could be manufacture/lot/partial text, not necessarily a wrong label. '
                'Verify the actual crop. Do not replace its transcription with image expiry automatically.'))
    queue.sort(key=lambda r:(bool(r['unrepaired_parses']),r['image_id']))
    with (DEV/'training-review/transcription-review.json').open('x',encoding='utf-8') as stream:
        json.dump(dict(scope='Review priority only, no label mutation or approval',items=queue),stream,ensure_ascii=False,indent=2)
    lines=['# 학습 전사 검토 우선 목록','',
        '아래 항목은 오류 확정이 아닙니다. 제조일·LOT·부분 날짜일 수 있습니다.',
        '이미지 전체의 소비기한을 crop 전사로 자동 대체하지 않습니다. 원본과 crop의 실제 인쇄 글자를 확인해야 합니다.',
        f'전체 {len(queue)}건. 아래는 첫 30건이며 전체 목록은 transcription-review.json에 있습니다.','',
        '| 원본 | 현재 crop 전사 | 이미지 소비기한(참고) | crop |',
        '|---|---|---|---|']
    for r in queue[:30]:
        trans=r['transcription'].replace('|','\\|').replace('\n',' ')
        lines.append(f"| [{r['image_id']}](<{Path(r['original_path']).as_posix()}>) | {trans} | {r['image_expiry']} | "
                     f"[보기](<{Path(r['crop_path']).as_posix()}>) |")
    with (DEV/'training-review/transcription-review.md').open('x',encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
    print(json.dumps(dict(review_items=len(queue),no_unrepaired_date=sum(not r['unrepaired_parses'] for r in queue))))


if __name__=='__main__':
    main()
