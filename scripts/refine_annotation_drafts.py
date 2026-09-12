"""Reduce review noise and complete evidence-labelled, never-approved drafts."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann
from scripts.build_annotation_drafts import enrich, role_hint


def visible_fields(text):
    # Visibility, not the interpretation of an ambiguous date ordering.
    if re.search(r'(?<!\d)(?:20)?\d{2}[./년年-]+(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)',text):
        return dict(year='present',month='present',day='present')
    if re.search(r'\d{4}年\d{1,2}月\d{1,2}日',text):
        return dict(year='present',month='present',day='present')
    month=re.search(r'JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC',text,re.I)
    if month and len(re.findall(r'\d+',text))>=2:
        return dict(year='present',month='present',day='present')
    three = re.search(r'(?<!\d)(\d{2,4})[. /년-]+(\d{1,2})[. /월-]+(\d{1,4})(?!\d)', text)
    if three:
        a,b,c = map(int, three.groups())
        if (1 <= b <= 12 and 1 <= c <= 31) or (1 <= a <= 31 and 1 <= b <= 12 and 1900 <= c <= 2099):
            return dict(year='present', month='present', day='present')
    if re.search(r'(?<!\d)(?:20)?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)', text):
        return dict(year='present', month='present', day='present')
    if re.search(r'(?<!\d)20\d{2}[./년-]+(?:0?[1-9]|1[0-2])[./월-]+(?:0?[1-9]|[12]\d|3[01])', text):
        return dict(year='present', month='present', day='present')
    if re.search(r'(?<!\d)20\d{2}[./년-]+(?:0?[1-9]|1[0-2])(?:월|(?=$|\s))', text):
        return dict(year='present', month='present', day='absent')
    if re.search(r'(?<!\d)(?:0?[1-9]|1[0-2])[./월-]+(?:0?[1-9]|[12]\d|3[01])(?:일|(?=$|\s))', text):
        return dict(year='absent', month='present', day='present')
    return None


def plausible_date(text):
    if re.search(r'TEL|FAX|전화|상담|고객|신고|품목보고|특허|등록번호|\d\s*%|kcal', text, re.I) and not role_hint(text):
        return False
    return bool(visible_fields(text) or
        re.search(r'(?<!\d)20\d{2}[./년-]+\d', text) or
        (role_hint(text) and re.search(r'\d.*[./월-].*\d', text)) or
        re.search(r'\d.*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC).*\d', text, re.I))


def refine(record):
    if record['review']['status'] != 'pending' or record['review']['reviewer']:
        return record
    context = record.setdefault('ocr_context', [])
    for r in list(record['regions']):
        if r['status'] != 'pending' or r['provenance'].get('type') != 'automatic_ocr_candidate':
            continue
        if r['kind'] == 'date_line' and not plausible_date(r['transcription']):
            record['regions'].remove(r)
            r['kind'] = 'other'
            context.append(r)
    for r in list(context):
        if plausible_date(r['transcription']):
            context.remove(r)
            r['kind'] = 'date_line'
            record['regions'].append(r)
    for r in record['regions']:
        if r['status'] != 'pending':
            continue
        if r['role'] is None:
            r['role'] = 'other'
            r['role_evidence'] = '초안: 인쇄 표제와 역할 연결 근거가 없어 기타·불명으로 제안. 사진에서 확인 필요.'
        if r['kind'] in ('date_line','date_block') and 'unknown' in r['field_states'].values():
            fields = visible_fields(r['transcription'])
            if fields:
                r['field_states'] = fields
        if 'unknown' not in r['field_states'].values() and r.get('draft'):
            r['draft']['issues']=[s for s in r['draft'].get('issues',[]) if s!='날짜 순서·부분 날짜·가려짐 확인']
        r.setdefault('draft', {})['method'] = 'literal_evidence_v2'
    if record['difficulty'] == 'unassessed':
        scores = [r['provenance'].get('text_candidate', r['provenance']).get('score', 1) for r in record['regions']]
        record['difficulty'] = 'hard' if not scores or min(scores)<.65 else 'medium' if min(scores)<.9 else 'easy'
        record['draft']['difficulty_basis'] = 'OCR 신뢰도에 따른 임시 난이도; 시각 검수로 변경 가능'
    # No tags is explicitly unmeasured, not a claim of flawless image quality.
    record['draft']['version'] = 2
    record['draft']['human_verified'] = False
    return record


def main():
    changed=0
    for path in sorted((ann.OUT/'records').glob('*.json')):
        before=ann.read(path)
        record=refine(ann.read(path))
        if not record['review']['reviewer'] and record['review']['status']=='pending' and not record.get('quality_draft_measurements'):
            import cv2
            import numpy as np
            with ann.Image.open(ann.source_path(record)) as image:
                if ann.sha(ann.source_path(record)) != record['image_sha256']:
                    raise ValueError('Image SHA mismatch: '+record['image_id'])
                measurements=[]
                for region in record['regions']:
                    if region['kind']!='date_line' or region['status']=='rejected':
                        continue
                    tile=ann.crop(image,region['polygon'])
                    gray=np.asarray(tile.convert('L'))
                    measurements.append(dict(region_id=region['region_id'],height=tile.height,
                        contrast=round(float(gray.std()),2),laplacian_variance=round(float(cv2.Laplacian(gray,cv2.CV_64F).var()),2)))
            suggestions=set(record['quality_tags'])
            for m in measurements:
                if m['height']<20:
                    suggestions.add('low_resolution')
                if m['contrast']<25:
                    suggestions.add('low_contrast')
                if m['laplacian_variance']<30:
                    suggestions.add('blur')
            record['quality_tags']=sorted(suggestions)
            record['quality_draft_measurements']=dict(method='raw_date_crop_pixel_heuristics_v1',
                regions=measurements,unmeasured=['reflection','curved','bleed','dot_print','occlusion'],
                warning='미검수 픽셀 기반 후보이며, 태그가 없다고 결함이 없는 것은 아님')
        if record != before:
            ann.save_review(record['image_id'],record,record['revision'],False)
            changed+=1
    print(dict(updated=changed, human_approvals_created=0))


if __name__=='__main__':
    main()
