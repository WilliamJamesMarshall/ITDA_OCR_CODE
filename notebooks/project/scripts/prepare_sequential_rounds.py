"""Prepare eight label-free rounds without inference, training or approval."""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path('C:/ITDA_OCR_WORKSPACE/sequential-8-rounds')
PROTECTED = ('상품사진_정답지', '상품사진입니다', '추가수집_정답지', '추가수집데이터',
             '테스트용_정답지', '테스트용데이터', '학습대상_정답지', '학습대상데이터')

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def csv_write(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def csv_read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def round_for(image_id):
    match = re.fullmatch(r'[AB]MLT(\d{6})', image_id)
    if not match or not 1 <= int(match[1]) <= 3716:
        raise ValueError('Invalid test ID: ' + image_id)
    number = int(match[1])
    return 1 if number <= 216 else 2 + (number - 217) // 500

def inventory():
    return {p.relative_to(ROOT).as_posix(): {'bytes': p.stat().st_size, 'sha256': digest(p)}
            for folder in PROTECTED for p in sorted((ROOT / folder).rglob('*')) if p.is_file()}

def baseline(base):
    target = base / 'baseline.json'
    if target.exists():
        verify(base)
        return
    write(target, inventory())
    paths = [ROOT / 'predict.ipynb', ROOT / 'notebooks/docs/protocol',
             ROOT / '학습 및 테스트 결과/학습_및_평가_실행계획.md',
             ROOT / '학습 및 테스트 결과/00_protocol/execution_policy.md',
             ROOT / '학습 및 테스트 결과/stage345_progress.json']
    for index, source in enumerate(paths):
        destination = base / 'previous_policy' / str(index) / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir(): shutil.copytree(source, destination)
        elif source.exists(): shutil.copy2(source, destination)
    write(base / 'git_before.json', {key: subprocess.check_output(command, cwd=ROOT).decode('utf-8').strip()
          for key, command in {'head': ['git', 'rev-parse', 'HEAD'],
                               'status': ['git', 'status', '--short'],
                               'remote': ['git', 'remote', '-v']}.items()})

def verify(base):
    before, after = read(base / 'baseline.json'), inventory()
    changes = [p for p in before.keys() | after.keys() if before.get(p) != after.get(p)]
    write(base / 'preservation.json', {'files': len(after), 'changes': changes})
    if changes: raise ValueError('Protected data changed')
    return len(after)

def prepare(base):
    if (base / 'rounds').exists(): raise ValueError('Execution already initialized; manifests are frozen')
    baseline(base)
    originals = sorted(p for p in (ROOT / '학습대상데이터').iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    tests = sorted((p for p in (ROOT / '테스트용데이터').iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png')),
                   key=lambda p: int(p.stem[4:]))
    if len(tests) != 3716 or len(originals) != 2610: raise ValueError('Unexpected image counts')
    if {int(p.stem[4:]) for p in tests} != set(range(1, 3717)): raise ValueError('Missing/duplicate serial')
    hashes = defaultdict(list)
    for path in originals: hashes[digest(path)].append(path)
    old = read(ROOT / '학습 및 테스트 결과/00_protocol/dataset_inventory.json')['images']
    historical = {r['test_image_id']: r for r in old}
    mapping, queue = [], []
    for path in tests:
        sha = digest(path)
        legacy = historical[path.stem]
        test_copy = next(c for c in legacy['copies'] if c['kind'] == 'test')
        if sha != test_copy['sha256']: raise ValueError('Test inventory changed: ' + path.stem)
        matches = hashes[sha]
        original = matches[0] if len(matches) == 1 else None
        augmented = legacy.get('exclusion_reason') == 'preexisting_640x640_augmented_derivative'
        record = ROOT / '학습 및 테스트 결과/02_annotations/records' / f'{original.stem}.json' if original else None
        annotation = read(record) if record and record.exists() else None
        if original and (not annotation or annotation['review']['status'] != 'approved' or annotation['image_sha256'] != sha):
            raise ValueError('Missing approved annotation: ' + original.stem)
        row = dict(test_id=path.stem, round=round_for(path.stem), original_id=original.stem if original else '',
                   augmented=str(augmented).lower(), evidence='sha256_exact' if original else 'unresolved_derivative',
                   test_sha256=sha, original_sha256=sha if original else '',
                   original_path=str(original) if original else '', group_id=annotation['group_id'] if annotation else '',
                   group_verified='false', annotation_path=str(record) if annotation else '',
                   annotation_sha256=digest(record) if annotation else '',
                   seen_in_development=str(legacy['seen_in_development']).lower(), first_admitted_round='')
        if original and augmented: raise ValueError('Augmented file cannot be an original')
        if not original: queue.append(dict(test_id=path.stem, reason='No exact original; derivative provenance requires review'))
        mapping.append(row)
    for row in mapping[:216]:
        if row['test_id'] != 'AMLT' + row['test_id'][4:] or row['original_id'] != 'AMLC' + row['test_id'][4:]:
            raise ValueError('Round 1 identity mismatch')
    for number in range(1, 9):
        rows = [{'image_id': p.stem, 'image_path': str(p)} for p in tests if round_for(p.stem) == number]
        if len(rows) != (216 if number == 1 else 500): raise ValueError('Round size mismatch')
        csv_write(base / f'test_round_{number:02d}.csv', rows, ['image_id', 'image_path'])
    csv_write(base / 'test_to_original_mapping.csv', mapping, list(mapping[0]))
    csv_write(base / 'mapping_review_queue.csv', queue, ['test_id', 'reason'])
    summary = dict(policy='sequential-8-v1', images=len(tests), originals=len(originals),
                   round_sizes=dict(Counter(r['round'] for r in mapping)),
                   exact_original_matches=sum(bool(r['original_id']) for r in mapping),
                   unresolved=len(queue), augmented=sum(r['augmented'] == 'true' for r in mapping),
                   round1_sha256_verified=True, product_groups_verified=False,
                   annotations_approval='Existing bulk user approval; not per-image visual review',
                   training_started=False, formal_test_started=False)
    write(base / 'round_summary.json', summary)
    write(base / 'manifest_lock.json', {p.name: digest(p) for p in [*base.glob('test_round_*.csv'),
          base / 'test_to_original_mapping.csv', base / 'mapping_review_queue.csv']})
    print(json.dumps(summary, ensure_ascii=False))

def prepare_scorer(base):
    """Copy previously approved dates to a scorer-only artifact, never a manifest."""
    records = read(ROOT / '학습 및 테스트 결과/00_protocol/dataset_inventory.json')['images']
    ids = {r['image_id'] for n in range(1, 9) for r in csv_read(base / f'test_round_{n:02d}.csv')}
    if len(records) != 3716 or {r['test_image_id'] for r in records} != ids:
        raise ValueError('Scorer label coverage differs from manifests')
    if any(r['final_date_status'] != 'approved' for r in records): raise ValueError('Unapproved dates')
    rows = [{'image_id': r['test_image_id'], '정답 날짜': r['final_date'], '라벨 상태': 'approved'} for r in records]
    target = base / 'scorer_only/labels.csv'
    csv_write(target, rows, ['image_id', '정답 날짜', '라벨 상태'])
    write(base / 'scorer_only/source.json', {'source': 'Existing approved dataset inventory, no new approval',
          'source_sha256': digest(ROOT / '학습 및 테스트 결과/00_protocol/dataset_inventory.json'),
          'labels_sha256': digest(target), 'rows': len(rows)})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['baseline', 'prepare', 'verify', 'scorer-labels'])
    parser.add_argument('--workspace', type=Path, default=BASE)
    args = parser.parse_args()
    print({'result': {'baseline': baseline, 'prepare': prepare, 'verify': verify,
                     'scorer-labels': prepare_scorer}[args.mode](args.workspace)})

if __name__ == '__main__': main()
