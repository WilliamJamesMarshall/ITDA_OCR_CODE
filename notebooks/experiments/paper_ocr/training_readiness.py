"""Create review-only inputs; never infer field truth or approve product groups."""
import csv
import hashlib
import json
from pathlib import Path

BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
DEST = BASE/'paper-ocr-20260914/training-review'
POOL = Path('C:/ITDA_OCR_WORKSPACE/workspace/02_annotations/exports/20260911T193432620539Z/recognition_pool.jsonl')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, data):
    with (DEST/name).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def main():
    DEST.mkdir(exist_ok=False)
    with (BASE/'test_to_original_mapping.csv').open(encoding='utf-8-sig', newline='') as stream:
        mapping = [r for r in csv.DictReader(stream) if r['round'] in ('2','3')]
    carry = read(BASE/'groups/group_01/historical_carryover.json')
    ids = {r['original_id'] for r in mapping}
    samples = [json.loads(line) for line in POOL.read_text(encoding='utf-8-sig').splitlines()]
    samples = [s for s in samples if s['image_id'] in ids]
    groups = {}
    issues = []
    for row in mapping:
        image_id = row['original_id']
        if image_id in groups:
            continue
        old = carry['admitted'].get(image_id)
        groups[image_id] = dict(group_id=old['group_id'] if old else row['group_id'],
            verified=bool(old), evidence='Historical approved carryover' if old else '',
            review_status='historical' if old else 'pending', original_path=row['original_path'],
            annotation_path=row['annotation_path'], annotation_sha256=row['annotation_sha256'])
        original, annotation = Path(row['original_path']), Path(row['annotation_path'])
        if not original.exists() or sha(original) != row['original_sha256']:
            issues.append(dict(image_id=image_id, issue='original_missing_or_changed'))
        if not annotation.exists() or sha(annotation) != row['annotation_sha256']:
            issues.append(dict(image_id=image_id, issue='annotation_missing_or_changed'))
        elif read(annotation)['review']['status'] != 'approved':
            issues.append(dict(image_id=image_id, issue='annotation_not_approved'))
    crops = []
    for sample in [*carry['samples'], *samples]:
        path = Path(sample['crop_path'])
        valid = path.exists() and sha(path) == sample['crop_sha256']
        crops.append(dict(**sample, crop_hash_valid=valid,
            date_fields=sample.get('date_fields',dict(year=None,month=None,day=None)),
            field_review_status='existing' if 'date_fields' in sample else 'pending'))
    write('groups.draft.json', groups)
    write('crops.draft.json', crops)
    summary = dict(status='review_required_not_trainable', current_rounds=[2,3],
        source_pool=dict(path=str(POOL),sha256=sha(POOL)), originals=len(ids),
        unreviewed_groups=sum(not g['verified'] for g in groups.values()),
        current_crops=len(samples), historical_crops=len(carry['samples']),
        missing_field_labels=sum(c['field_review_status']=='pending' for c in crops),
        invalid_crop_hashes=sum(not c['crop_hash_valid'] for c in crops), linkage_issues=issues,
        future_rounds_read=False, optimizer_started=False,
        note='Drafts are not training inputs or approvals. Preserve permanent group roles. '
             'Only inner-validation crops require date_fields; their final membership follows group review.')
    write('readiness.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k != 'linkage_issues'},ensure_ascii=False))


if __name__ == '__main__':
    main()
