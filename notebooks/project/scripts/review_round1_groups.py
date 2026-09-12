"""Generate original-image contact sheets for round-one product grouping; no OCR."""
from PIL import Image, ImageOps, ImageDraw
import argparse
import json
import shutil
from scripts.prepare_sequential_rounds import BASE, ROOT, csv_read, csv_write, read, write, digest

def apply_review():
    from scripts.sequential_rounds import cumulative_partition
    if (BASE / 'rounds').exists(): raise ValueError('Do not change review manifests after execution starts')
    out = BASE / 'round1-group-review'
    decision_path = out / 'visual_decisions.json'
    decisions = read(decision_path)
    sources = read(out / 'sources.json')
    assignments = {i: f'round1-product-{i:06d}' for i in range(1, 217)}
    reasons = {i: decisions['remaining_images'] for i in assignments}
    used = set()
    for group in decisions['merged_groups']:
        for i in group['ids']:
            if i in used or i not in assignments: raise ValueError('Duplicate/invalid group member')
            used.add(i)
            assignments[i] = f'round1-family-{min(group["ids"]):06d}'
            reasons[i] = group['reason']
    groups = {}
    for i in range(1, 217):
        key = f'AMLC{i:06d}'
        if digest(sources[key]['path']) != sources[key]['sha256']: raise ValueError('Reviewed image changed')
        groups[key] = dict(group_id=assignments[i], verified=True, evidence=reasons[i],
            reviewer='assistant', review_scope='round1 conservative visual split groups',
            image_sha256=sources[key]['sha256'], decisions_sha256=digest(decision_path))
    write(out / 'verified_groups.json', groups)
    path = BASE / 'test_to_original_mapping.csv'
    backup = out / 'mapping_before_review.csv'
    if not backup.exists(): shutil.copy2(path, backup)
    mapping = csv_read(path)
    for row in mapping:
        if row['original_id'] in groups:
            row.update(group_id=groups[row['original_id']]['group_id'], group_verified='true')
    csv_write(path, mapping, list(mapping[0]))
    lock = read(BASE / 'manifest_lock.json')
    lock[path.name] = digest(path)
    write(BASE / 'manifest_lock.json', lock)
    rows = [r for r in mapping if r['round'] == '1']
    roles = cumulative_partition(rows, {})
    counts = {role: sum(roles[r['group_id']] == role for r in rows) for role in ('optimizer_train', 'inner_validation')}
    write(out / 'partition_preview.json', dict(status='preview_not_admitted_or_approved', images=len(rows),
          groups=len(roles), image_counts=counts, group_roles=roles, training_started=False))
    pool = ROOT / '학습 및 테스트 결과/02_annotations/exports/20260911T193432620539Z/recognition_pool.jsonl'
    by_id = {r['original_id']: r for r in rows}
    crop_counts = {role: 0 for role in counts}
    ids_with_crops = set()
    for item in map(json.loads, pool.read_text(encoding='utf-8').splitlines()):
        row = by_id.get(item['image_id'])
        if not row: continue
        if item['record_sha256'] != row['annotation_sha256'] or digest(item['crop_path']) != item['crop_sha256']:
            raise ValueError('Approved round-one crop/record mismatch')
        crop_counts[roles[row['group_id']]] += 1
        ids_with_crops.add(item['image_id'])
    if not all(crop_counts.values()): raise ValueError('Empty recognition partition')
    write(out / 'learning_preflight.json', dict(status='passed', original_images=216,
          image_counts=counts, recognition_crop_counts=crop_counts,
          originals_without_recognition_crops=sorted(by_id.keys()-ids_with_crops),
          group_overlap=0, approval_created=False, originals_admitted=False,
          scope='Preview of actual approved original crop pool; not authorization to train'))
    print(counts)

def main():
    rows = [r for r in csv_read(BASE / 'test_to_original_mapping.csv') if r['round'] == '1']
    out = BASE / 'round1-group-review'
    out.mkdir(exist_ok=True)
    for offset in range(0, len(rows), 24):
        sheet = Image.new('RGB', (1600, 1200), 'white')
        draw = ImageDraw.Draw(sheet)
        for k, row in enumerate(rows[offset:offset + 24]):
            with Image.open(row['original_path']) as im:
                thumb = ImageOps.contain(ImageOps.exif_transpose(im).convert('RGB'), (260, 265))
            x, y = (k % 6) * 266, (k // 6) * 300
            sheet.paste(thumb, (x + (260-thumb.width)//2, y))
            draw.text((x+8, y+270), row['original_id'], fill='black')
        sheet.save(out / f'sheet_{offset//24+1:02d}.jpg', quality=92)
    write(out / 'sources.json', {r['original_id']: {'path': r['original_path'], 'sha256': digest(r['original_path'])} for r in rows})
    print(out)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply-review', action='store_true')
    args = parser.parse_args()
    apply_review() if args.apply_review else main()
