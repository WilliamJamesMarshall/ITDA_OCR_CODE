"""Resumable CPU candidates. Never substitute final-date truth for printed text."""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann


def role_hint(text):
    expiry = bool(re.search(r'소비기한|유통기한|까지|\bEXP\b|BEST\s*BEFORE|USE\s*BY', text, re.I))
    manufacture = bool(re.search(r'제조|부터|\bMFG\b|\bMFD\b|PROD', text, re.I))
    return 'expiry' if expiry and not manufacture else 'manufacture' if manufacture and not expiry else None


def region_kind(text):
    if (re.search(r'\d.*[./년월-].*\d', text)
            or re.search(r'(?<!\d)(?:19|20)\d{6}(?!\d)', text)
            or re.search(r'\d.*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', text, re.I)
            or re.search(r'(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC).*\d', text, re.I)):
        return 'date_line'
    return 'header' if role_hint(text) else 'other'


def date_fields(text):
    # Only syntactically explicit Y-M-D. Ambiguous formats remain questions.
    match = re.search(r'(?<!\d)(\d{4}|\d{2})[. /년-]+(\d{1,2})[. /월-]+(\d{1,2})(?!\d)', text)
    if match and 1 <= int(match[2]) <= 12 and 1 <= int(match[3]) <= 31:
        return dict(year='present', month='present', day='present')
    if re.search(r'\d{1,2}월\s*\d{1,2}일', text):
        return dict(year='absent', month='present', day='present')
    return dict(year='unknown', month='unknown', day='unknown')


def enrich(record):
    """Populate untouched candidates only; every suggestion retains pending status."""
    if record['review']['status'] != 'pending' or record['review']['reviewer']:
        return record
    # Retain general package OCR for context without making every nutrition word
    # a required training annotation. Humans must still confirm date completeness.
    context = record.setdefault('ocr_context', [])
    restored = [r for r in context if region_kind(r['transcription']) != 'other']
    for region in restored:
        region['kind'] = region_kind(region['transcription'])
        record['regions'].append(region)
        context.remove(region)
    kept = []
    for region in record['regions']:
        if region['kind'] == 'other' and region['status'] == 'pending' and region['provenance'].get('type') == 'automatic_ocr_candidate':
            region['kind'] = region_kind(region['transcription'])
        if (region['kind'] == 'other' and region['status'] == 'pending'
                and region['provenance'].get('type') == 'automatic_ocr_candidate'
                and not role_hint(region['transcription'])):
            context.append(region)
        else:
            kept.append(region)
    record['regions'] = kept
    for region in record['regions']:
        if region['status'] != 'pending' or region.get('draft'):
            continue
        text = region['transcription']
        issues = []
        hint = role_hint(text)
        source_class = region['provenance'].get('source_class')
        if region['kind'] == 'other' and hint:
            region['kind'] = 'header'
        if text.strip() and region['legibility'] == 'unknown':
            region['legibility'] = 'readable'
        if not text.strip():
            issues.append('원문 후보 없음: 사진에서 확인')
        score = region['provenance'].get('text_candidate', region['provenance']).get('score')
        if score is not None and score < .85:
            issues.append('OCR 신뢰도 낮음: 원문 확인')
        if region['kind'] in ('date_line', 'date_block'):
            if all(v == 'unknown' for v in region['field_states'].values()):
                region['field_states'] = date_fields(text)
            if 'unknown' in region['field_states'].values():
                issues.append('날짜 순서·부분 날짜·가려짐 확인')
            if not region['separators']:
                region['separators'] = ''.join(dict.fromkeys(re.findall(r'[./년월일-]', text)))
        if region['kind'] == 'lot' and not region['lot_text']:
            region['lot_text'] = text
        time_match = re.search(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', text)
        if time_match and not region['time_text']:
            region['time_text'] = time_match[0]
        if region['role'] is None:
            if hint:
                region['role'] = hint
                region['role_basis'] = 'visible_header'
                region['role_evidence'] = '미검수 초안: 원문 표제 단서 ' + text
            elif source_class in ('due', 'prod', 'exp'):
                region['role'] = 'manufacture' if source_class == 'prod' else 'expiry'
                region['role_evidence'] = '미검수 초안: 외부 source_class=' + source_class
        region['draft'] = dict(method='literal_text_and_source_hints_v1', issues=issues,
                               human_verified=False)
    headers = [r for r in record['regions'] if r['kind'] == 'header' and r['role'] in ('expiry','manufacture')]
    for region in record['regions']:
        if region['status'] != 'pending' or region['kind'] not in ('date_line','date_block') or region['role']:
            continue
        ys = [p[1] for p in region['polygon']]
        nearby = [h for h in headers if abs(sum(p[1] for p in h['polygon'])/len(h['polygon']) - (min(ys)+max(ys))/2) <= max(ys)-min(ys)]
        if len(nearby) == 1:
            header = nearby[0]
            region['role'] = header['role']
            region['role_basis'] = 'visible_header'
            region['header_region_ids'] = [header['region_id']]
            region['role_evidence'] = '미검수 초안: 같은 높이의 표제 ' + header['region_id'] + ' / ' + header['transcription']
        else:
            issue = '역할 근거 부족: 소비기한/제조일/불명 확인'
            if issue not in region['draft']['issues']:
                region['draft']['issues'].append(issue)
    if not record.get('draft'):
        tags = record['legacy_metadata']['condition_tags']
        record['quality_tags'] = sorted(set(record['quality_tags']) | (set(tags) & set(ann.QUALITY_TAGS)))
        record['draft'] = dict(method='candidate_only_v1', human_verified=False,
            issues=['상품 그룹은 파일 동일성만 확인됨: 같은 상품·연속 촬영 확인 필요',
                    '반사·곡면·번짐 등 품질은 사진 대조 필요'],
            quality_basis='기존 진단 태그 재사용; 태그 없음은 결함 없음이 아님')
        if not record['group_evidence']:
            record['group_evidence'] = '초안: SHA-256 파일 동일성 기준. 동일 상품·연속 촬영 관계는 아직 미확정.'
    if not any(r['kind'] in ('date_line','date_block') for r in record['regions']):
        issue = '날짜 영역 후보 없음: 참고 OCR 및 원본에서 날짜 줄 탐색 필요'
        if issue not in record['draft']['issues']:
            record['draft']['issues'].append(issue)
    else:
        record['draft']['issues'] = [s for s in record['draft']['issues'] if not s.startswith('날짜 영역 후보 없음:')]
    for region in record['regions']:
        if region.get('draft'):
            region['draft']['issues'] = list(dict.fromkeys(region['draft']['issues']))
    return record


def run(ocr=False, limit=None, reverse=False, threads=4):
    backend = None
    processed = 0
    failures = []
    for path in sorted((ann.OUT/'records').glob('*.json'), reverse=reverse):
        record = ann.read(path)
        if record['review']['status'] != 'pending' or record['review']['reviewer']:
            continue
        if ocr and record['source_dataset'] == 'product' and not record.get('ocr_draft_pass'):
            if limit is not None and processed >= limit:
                break
            try:
                if backend is None:
                    import cv2
                    import numpy as np
                    from src.pipeline import PaddleOCRBackend, PipelineConfig
                    backend = PaddleOCRBackend(PipelineConfig(cpu_threads=threads))
                if not record['regions']:
                    with ann.Image.open(ann.source_path(record)) as image:
                        raster = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2BGR)
                    for i, line in enumerate(backend.recognize(raster, detector='mobile', variant='stored-raster')):
                        if not line.geometry_valid or not line.polygon:
                            continue
                        polygon = [list(p) for p in line.polygon]
                        if ann.polygon_errors(polygon, record['width'], record['height']):
                            continue
                        kind = region_kind(line.text)
                        record['regions'].append(ann.new_region(f'ocr_{i:03d}', kind, polygon, line.text,
                            dict(type='automatic_ocr_candidate', score=float(line.score), model='PP-OCRv5_mobile', created_at=ann.now())))
                record['ocr_draft_pass'] = dict(status='completed', created_at=ann.now(), cpu_threads=threads)
                processed += 1
            except Exception as exc:
                failures.append(dict(image_id=record['image_id'], error=str(exc)))
                ann.write(ann.OUT/'draft_failures.json', failures)
                continue
        before = ann.read(path)
        enrich(record)
        if record != before:
            try:
                ann.save_review(record['image_id'], record, record['revision'], False)
            except ValueError as exc:
                failures.append(dict(image_id=record['image_id'], error=str(exc)))
        if ocr and processed and processed % 20 == 0:
            print(f'CPU draft images processed: {processed}', flush=True)
    ann.audit()
    report = dict(processed_this_run=processed, failures=failures, human_approvals_created=0)
    ann.write(ann.OUT/('ocr_draft_report_reverse.json' if reverse else 'ocr_draft_report.json' if ocr else 'metadata_draft_report.json'), report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    print(run(args.ocr, args.limit, args.reverse, args.threads), flush=True)
