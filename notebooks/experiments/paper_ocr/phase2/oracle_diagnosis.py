"""Explicitly gated OCR interventions on reviewed current-round originals.

Compares baseline -> reviewed crop OCR -> printed-transcription substitution.
Diagnostic interventions are NEVER submitted predictions or optimizer samples.
"""
import argparse
import csv
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path('C:/ITDA_OCR_CODE')
BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1')
FIELDS = ('year', 'month', 'day')


def classify(baseline, crop, transcription, expected):
    # Non-exclusive intervention sensitivity, not proof of a unique cause.
    return {field: ('baseline_correct' if baseline[field] == expected[field] else
                    'region_or_crop_sensitive' if crop[field] == expected[field] else
                    'recognition_sensitive' if transcription[field] == expected[field] else
                    'parsing_role_or_annotation_unresolved') for field in FIELDS}


def overlap(a, b):
    area = max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area
    return area/union if union > 0 else 0.


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--code-root', type=Path, required=True)
    p.add_argument('--reviewed-regions', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute-tests', action='store_true')
    a = p.parse_args()
    if not a.execute_tests:
        p.error('OCR diagnosis is a test: separate user instruction and --execute-tests required')
    if a.output.exists():
        raise FileExistsError(a.output)
    reviewed = json.loads(a.reviewed_regions.read_text(encoding='utf-8'))
    if reviewed.get('approved') is not True or not reviewed.get('source_reference'):
        raise ValueError('Explicit reviewed-region evidence required')
    allowed = set()
    for n in (1,2,3):
        with (BASE/f'test_round_{n:02}.csv').open(encoding='utf-8-sig',newline='') as stream:
            allowed.update(Path(r['image_path']).resolve() for r in csv.DictReader(stream))
    # Check every record before any model load/inference.
    for row in reviewed['images']:
        image = Path(row['original_path']).resolve()
        if image not in allowed or image.parent != (ROOT/'학습대상데이터').resolve():
            raise ValueError('Only already exposed current-round originals may be diagnosed')
        if hashlib.sha256(image.read_bytes()).hexdigest() != row['original_sha256']:
            raise ValueError('Reviewed original changed')
        if row.get('regions_reviewed') is not True or not row['regions']:
            raise ValueError('Reviewed regions required')
        if set(row['expected_fields']) != set(FIELDS):
            raise ValueError('Explicit three-field labels required')
    sys.path.insert(0,str(a.code_root/'notebooks/project'))
    from src.pipeline import PaddleOCRBackend, PipelineConfig, _load_bgr
    from src.date_extraction import OCRLine, select_date, submission_fields
    from src.budget_pipeline import output_selection
    config = PipelineConfig(weights_dir=a.code_root/'weights/paddle')
    backend = PaddleOCRBackend(config)
    def predict(lines):
        return submission_fields(output_selection(select_date(lines, context=config.date_context,
                                        product_rules=config.product_date_rules)).final_date)
    with a.output.open('x',encoding='utf-8') as stream:
        for row in reviewed['images']:
            image = _load_bgr(Path(row['original_path']))
            backend.begin_image()
            observed = [replace(line, original_box=line.box) for line in
                        backend.recognize(image,detector='mobile',variant='original')]
            baseline = predict(observed)
            crops, boxes = [], []
            for region in row['regions']:
                x1,y1,x2,y2 = region['box']
                if (any(type(v) is not int for v in region['box']) or
                        not 0 <= x1 < x2 <= image.shape[1] or not 0 <= y1 < y2 <= image.shape[0]):
                    raise ValueError('Reviewed box must fit the EXIF-oriented original')
                if not region.get('transcription'):
                    raise ValueError('Reviewed printed transcription required')
                boxes.append((x1,y1,x2,y2))
                crops.append(image[y1:y2,x1:x2])
            recognized = backend.recognize_crops(crops)
            unchanged = [line for line in observed if not any(overlap(line.box,box) >= .5 for box in boxes)]
            crop_lines, oracle_lines = [], []
            for box,region,result in zip(boxes,row['regions'],recognized):
                crop_lines.append(OCRLine(result[0],result[1],box, original_box=box,
                                          character_scores=tuple(result[2]), variant='original'))
                oracle_lines.append(OCRLine(region['transcription'],1.,box,original_box=box,variant='original'))
            crop_result, text_result = predict(unchanged+crop_lines), predict(unchanged+oracle_lines)
            stream.write(json.dumps(dict(image_id=row['image_id'], baseline=baseline, oracle_crop=crop_result,
                oracle_text=text_result, expected=row['expected_fields'],
                field_diagnosis=classify(baseline,crop_result,text_result,row['expected_fields']),
                scope='Diagnostic intervention only; not final OCR performance'),ensure_ascii=False)+'\n')
            stream.flush()


if __name__ == '__main__':
    main()
