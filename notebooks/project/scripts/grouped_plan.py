"""Original-only six-round policy and immutable migration of the first three rounds."""
import re
import shutil
from collections import Counter
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read, csv_write, digest

PREVIOUS_BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1')
POLICY = 'grouped-6-originals-v1'
GROUPS = ((1,), (2, 3), (4, 5), (6,))
ROUND_SIZES = {1: 216, 2: 500, 3: 500, 4: 394, 5: 500, 6: 500}
SECONDS_PER_IMAGE = 3.2
HARD_TIMEOUT_SECONDS = 2400
CPU_POLICY = 'mixed-p2e2-v1'

def round_for(image_id):
    match = re.fullmatch(r'([AB])MLC(\d{6})', image_id)
    if not match:
        raise ValueError('Invalid original ID: ' + image_id)
    serial = int(match[2])
    if match[1] == 'B' and 2247 <= serial <= 2610: return 2
    if match[1] != 'A' or not 1 <= serial <= 2246:
        raise ValueError('Invalid original ID: ' + image_id)
    if serial <= 216: return 1
    if serial <= 352: return 2
    if serial <= 852: return 3
    if serial <= 1246: return 4
    if serial <= 1746: return 5
    return 6

def time_target_seconds(images):
    if images <= 0: raise ValueError('Positive image count required')
    return round(SECONDS_PER_IMAGE * images, 1)

def time_target_met(runtime, images):
    return (runtime['status'] == 'completed' and not runtime.get('failures')
            and runtime.get('images', images) == images
            and runtime['total_elapsed_seconds'] <= time_target_seconds(images))

def members(number):
    for group in GROUPS:
        if number in group: return group
    raise ValueError('Round must be 1..6')

def group_name(number):
    return 'group_' + '_'.join(f'{n:02d}' for n in members(number))

def previous_group(number):
    index = GROUPS.index(members(number))
    return GROUPS[index - 1] if index else ()

def cpu_set(number, integration=False):
    group = members(number)
    if len(group) == 1 or integration:
        return [0, 1, 2, 3]
    return [0, 1, 4, 5] if number == group[0] else [2, 3, 6, 7]

def validate_product_reference(row):
    """An existing augmented copy is a reference, never a training original."""
    path = Path(row['product_reference_path']).resolve()
    if path.parent != (ROOT / '상품사진입니다').resolve() or path.stem != row['test_id'][4:]:
        raise ValueError('Wrong existing product reference path')
    if row['original_id'] or row['augmented'] != 'true' or row['product_reference_usage'] != 'reference_only':
        raise ValueError('Augmented product reference cannot be a training original')
    if row['product_reference_kind'] != 'augmented_existing_product':
        raise ValueError('Existing product reference must retain its augmented type')
    if digest(path) != row['product_reference_sha256'] or row['product_reference_sha256'] != row['test_sha256']:
        raise ValueError('Existing product reference does not match the test bytes')
    proof_path = Path(row['product_reference_proof_path'])
    if digest(proof_path) != row['product_reference_proof_sha256']:
        raise ValueError('Product reference proof changed')
    proof = read(proof_path)
    if proof['test_id'] != row['test_id'] or proof['reference_path'] != str(path) or proof['sha256'] != row['test_sha256']:
        raise ValueError('Product reference proof mismatch')
    if proof['training_authorized'] is not False: raise ValueError('Reference cannot grant training approval')


def verify(base, check_assets=False):
    base = Path(base)
    for name, sha in read(base / 'manifest_lock.json').items():
        if digest(base / name) != sha: raise ValueError('Frozen plan input changed: ' + name)
    plan = read(base / 'plan.json')
    if plan['policy'] != POLICY or plan['groups'] != [list(g) for g in GROUPS]:
        raise ValueError('Unexpected grouped policy')
    if (plan['seconds_per_image_target'] != SECONDS_PER_IMAGE
            or plan['hard_timeout_seconds'] != HARD_TIMEOUT_SECONDS):
        raise ValueError('Unexpected timing policy')
    mapping = csv_read(base / 'test_to_original_mapping.csv')
    index = {r['test_id']: r for r in mapping}
    if (len(mapping) != 2610 or len(index) != 2610
            or len({r['original_id'] for r in mapping}) != 2610
            or len({r['original_sha256'] for r in mapping}) != 2610):
        raise ValueError('Missing or duplicate mapping IDs')
    original_root = (ROOT / '학습대상데이터').resolve()
    inventory = {p.resolve() for p in original_root.iterdir()
                 if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png')}
    if inventory != {Path(r['original_path']).resolve() for r in mapping}:
        raise ValueError('Original inventory coverage changed')
    seen, summary = set(), []
    for n in ROUND_SIZES:
        rows = csv_read(base / f'test_round_{n:02d}.csv')
        ids = [r['image_id'] for r in rows]
        if len(ids) != ROUND_SIZES[n] or len(set(ids)) != len(ids) or seen.intersection(ids):
            raise ValueError('Round size or duplicate IDs')
        for row in rows:
            i = row['image_id']
            if i not in index or round_for(index[i]['original_id']) != n or int(index[i]['round']) != n:
                raise ValueError('Wrong round assignment')
            original = index[i]
            path = Path(row['image_path'])
            if (path.parent.resolve() != original_root or path.stem != original['original_id']
                    or path.resolve() != Path(original['original_path']).resolve() or not path.is_file()
                    or original['augmented'] != 'false' or original['test_sha256'] != original['original_sha256']):
                raise ValueError('Missing or invalid test image path')
            if check_assets:
                if digest(path) != original['original_sha256']:
                    raise ValueError('Original image changed: ' + i)
                if digest(original['annotation_path']) != original['annotation_sha256']:
                    raise ValueError('Original annotation changed: ' + i)
        exposed = sum(index[i]['seen_in_development'] == 'true' for i in ids)
        if exposed != ({1: 206, 2: 499}.get(n, 0)):
            raise ValueError('Initial development exposure mismatch')
        seen.update(ids)
        summary.append(dict(round=n, group=group_name(n), cpus=cpu_set(n), images=len(ids),
                            time_target_seconds=time_target_seconds(len(ids)), seconds_per_image_target=SECONDS_PER_IMAGE,
                            initial_development=exposed, initial_unused=len(ids)-exposed,
                            existing_product_references=sum(bool(index[i].get('product_reference_path')) for i in ids),
                            identified_source_missing_file=sum(index[i].get('mapping_status')=='source_identified_file_missing' for i in ids),
                            unresolved_originals=sum(not index[i]['original_id'] for i in ids)))
    if seen != index.keys(): raise ValueError('Manifest coverage mismatch')
    return dict(policy=POLICY, images=len(seen), rounds=summary, duplicates=0, missing=0,
                used_originals=1216, remaining_originals=1394, usage_count_scope='original allocation after rounds 1-3',
                augmented=0, assets_verified=check_assets)

def prepare(base=BASE, source=PREVIOUS_BASE):
    base, source = Path(base), Path(source)
    if base.resolve() == source.resolve() or base.exists():
        raise ValueError('Use a new output directory; existing history is immutable')
    old_lock = read(source / 'manifest_lock.json')
    for name, sha in old_lock.items():
        if digest(source / name) != sha: raise ValueError('Legacy input changed: ' + name)
    old_mapping = csv_read(source / 'test_to_original_mapping.csv')
    mapping = [dict(r) for r in old_mapping if r['augmented'] == 'false']
    if len(old_mapping) != 3716 or len(mapping) != 2610:
        raise ValueError('Legacy inventory mismatch')
    labels = []
    for row in mapping:
        row['previous_grouped_round'] = row['round']
        row['round'] = str(round_for(row['original_id']))
        if int(row['previous_grouped_round']) <= 3 and row['round'] != row['previous_grouped_round']:
            raise ValueError('Used original moved to another round')
        if digest(row['original_path']) != row['original_sha256'] or row['test_sha256'] != row['original_sha256']:
            raise ValueError('Original differs from historical test bytes')
        record = read(row['annotation_path'])
        if (digest(row['annotation_path']) != row['annotation_sha256']
                or record['review']['status'] != 'approved' or record['image_sha256'] != row['original_sha256']):
            raise ValueError('Approved original annotation changed: ' + row['original_id'])
        labels.append(dict(image_id=row['test_id'], original_id=row['original_id'],
                           **{'정답 날짜': record['final_date'], '라벨 상태': 'approved'}))
    for n in (1, 2, 3):
        old_ids = [r['image_id'] for r in csv_read(source / f'test_round_{n:02d}.csv')]
        if old_ids != [r['test_id'] for r in mapping if int(r['round']) == n]:
            raise ValueError('Historical membership/order changed')
    # Snapshot only stable history, never an active experiment or its input/model copies.
    history_files = [source / name for name in ('legacy_history.json', 'group_roles.json', 'development_history.json')
                     if (source / name).exists()]
    for n in (1, 2, 3):
        history_files += [p for p in (source / f'rounds/round_{n:02d}').glob('*') if p.is_file()]
    for group in ('group_01', 'group_02_03'):
        history_files += [p for p in (source / 'groups' / group).glob('*.json') if p.is_file()]
        release = source / 'groups' / group / 'release/release.json'
        if release.exists(): history_files.append(release)
    history_hashes = {p.relative_to(source).as_posix(): digest(p) for p in history_files}
    base.mkdir(parents=True)
    write(base / 'plan.json', dict(policy=POLICY, groups=GROUPS, initial_unused_round2='AMLT000263',
          accuracy_target=.95, seconds_per_image_target=SECONDS_PER_IMAGE, hard_timeout_seconds=HARD_TIMEOUT_SECONDS,
          legacy_workspace=read(source / 'plan.json')['legacy_workspace'], previous_workspace=str(source.resolve()),
          original_root=str(ROOT / '학습대상데이터'), round_sizes=ROUND_SIZES, execution_started=False,
          identity_policy='Historical test IDs are output aliases; every input is copied from its bound original',
          scope='Implementation approval only; no future report review or training approval implied'))
    for n in ROUND_SIZES:
        rows = [dict(image_id=r['test_id'], image_path=r['original_path']) for r in mapping if int(r['round']) == n]
        csv_write(base / f'test_round_{n:02d}.csv', rows, ['image_id', 'image_path'])
    csv_write(base / 'test_to_original_mapping.csv', mapping, list(mapping[0]))
    csv_write(base / 'mapping_review_queue.csv', [], ['test_id', 'round', 'reason'])
    excluded = [dict(test_id=r['test_id'], test_sha256=r['test_sha256']) for r in old_mapping if r['augmented'] == 'true']
    csv_write(base / 'excluded_derivatives.csv', excluded, ['test_id', 'test_sha256'])
    csv_write(base / 'scorer_only/labels.csv', labels, ['image_id', 'original_id', '정답 날짜', '라벨 상태'])
    names = ['plan.json', 'test_to_original_mapping.csv', 'mapping_review_queue.csv',
             'excluded_derivatives.csv', 'scorer_only/labels.csv', *[f'test_round_{n:02d}.csv' for n in ROUND_SIZES]]
    write(base / 'manifest_lock.json', {name: digest(base / name) for name in names})
    for name, sha in history_hashes.items():
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
        if digest(target) != sha or digest(source / name) != sha:
            raise ValueError('Historical evidence changed during migration: ' + name)
    if any(digest(source / name) != sha for name, sha in old_lock.items()):
        raise ValueError('Source plan changed during migration')
    write(base / 'migration.json', dict(source=str(source.resolve()), source_lock=old_lock,
          copied_history=history_hashes, preserved_rounds=[1, 2, 3], excluded_derivatives=len(excluded),
          new_test_executed=False, new_training_executed=False,
          note='Historical state and evidence retain their original IDs, paths, approvals and timing judgments.'))
    summary = verify(base, check_assets=True)
    write(base / 'preparation_verification.json', summary)
    return summary


def revise_mapping(base, candidate):
    """Admit reviewed provenance metadata without changing test membership or past results."""
    from scripts.grouped_rounds import exclusive, now, checked_evidence, stamp
    base = Path(base)
    verify(base)
    old = csv_read(base / 'test_to_original_mapping.csv')
    incoming = csv_read(candidate)
    index = {r['test_id']: r for r in incoming}
    if len(incoming) != len(old) or len(index) != len(old): raise ValueError('Mapping coverage changed')
    changed = []
    protected = ('test_id','round','legacy_round','test_sha256','augmented','seen_in_development')
    for row in old:
        new = index.get(row['test_id'])
        if new is None or any(row.get(k) != new.get(k) for k in protected):
            raise ValueError('Test identity/exposure/round cannot change')
        if row['original_id']:
            if any(new.get(k) != v for k,v in row.items()): raise ValueError('Existing original link cannot change')
            continue
        if not new['original_id']: continue
        original = Path(new['original_path']).resolve()
        if original.parent != (ROOT / '학습대상데이터').resolve() or original.stem != new['original_id']:
            raise ValueError('Only corresponding originals can be admitted')
        if digest(original) != new['original_sha256']: raise ValueError('Original hash mismatch')
        record = read(checked_evidence(dict(path=new['annotation_path'],sha256=new['annotation_sha256'])))
        if record['review']['status'] != 'approved' or record['image_sha256'] != new['original_sha256']:
            raise ValueError('Approved original annotation required')
        proof = read(checked_evidence(dict(path=new['mapping_review_path'],sha256=new['mapping_review_sha256'])))
        for k in ('test_id','original_id','test_sha256','original_sha256'):
            if proof.get(k) != new[k]: raise ValueError('Provenance evidence mismatch')
        if proof.get('relationship') != 'derived_from' or not proof.get('reviewer') or not proof.get('source_reference'):
            raise ValueError('Reviewed derivation evidence required; serial/similarity alone is insufficient')
        stamp(proof['reviewed_at'])
        changed.append(new['test_id'])
    if not changed: raise ValueError('No newly verified original links')
    with exclusive(base / 'locks/metadata.lock'):
        if (base / 'locks/execution.lock').exists(): raise ValueError('Wait for running jobs before revising metadata')
        verify(base)
        revision = base / 'mapping_revisions' / now().replace(':','-')
        revision.mkdir(parents=True)
        for name in ('test_to_original_mapping.csv','mapping_review_queue.csv','manifest_lock.json'):
            shutil.copy2(base / name, revision / name)
        fields = list(dict.fromkeys(k for row in incoming for k in row))
        csv_write(base / 'test_to_original_mapping.csv', incoming, fields)
        queue = [dict(test_id=r['test_id'],round=r['round'],reason=r.get('mapping_issue') or 'Derivative provenance requires review') for r in incoming if not r['original_id']]
        csv_write(base / 'mapping_review_queue.csv',queue,['test_id','round','reason'])
        lock = read(base / 'manifest_lock.json')
        for name in ('test_to_original_mapping.csv','mapping_review_queue.csv'): lock[name]=digest(base/name)
        write(base / 'manifest_lock.json',lock)
        write(revision / 'change.json',dict(created_at=now(),source=str(Path(candidate).resolve()),source_sha256=digest(candidate),new_original_links=changed))
    return verify(base)
