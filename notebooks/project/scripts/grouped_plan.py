"""Versioned metadata preparation for the approved 1 / 2+3 / 4+5 / 6+7 / 8 plan."""
import re
import shutil
from collections import Counter
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, BASE as LEGACY_BASE, read, write, csv_read, csv_write, digest

BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
POLICY = 'grouped-8-v2'
GROUPS = ((1,), (2, 3), (4, 5), (6, 7), (8,))

def round_for(image_id):
    match = re.fullmatch(r'[AB]MLT(\d{6})', image_id)
    if not match or not 1 <= int(match[1]) <= 3716:
        raise ValueError('Invalid test ID: ' + image_id)
    serial = int(match[1])
    if serial <= 216: return 1
    if serial <= 352 or serial >= 3353: return 2
    return 3 + (serial - 353) // 500

def members(number):
    for group in GROUPS:
        if number in group: return group
    raise ValueError('Round must be 1..8')

def group_name(number):
    return 'group_' + '_'.join(f'{n:02d}' for n in members(number))

def previous_group(number):
    index = GROUPS.index(members(number))
    return GROUPS[index - 1] if index else ()

def cpu_set(number):
    return [0, 1, 2, 3] if number == members(number)[0] else [4, 5, 6, 7]

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


def verify(base):
    base = Path(base)
    for name, sha in read(base / 'manifest_lock.json').items():
        if digest(base / name) != sha: raise ValueError('Frozen plan input changed: ' + name)
    plan = read(base / 'plan.json')
    if plan['policy'] != POLICY or plan['groups'] != [list(g) for g in GROUPS]:
        raise ValueError('Unexpected grouped policy')
    mapping = csv_read(base / 'test_to_original_mapping.csv')
    index = {r['test_id']: r for r in mapping}
    if len(mapping) != 3716 or len(index) != 3716:
        raise ValueError('Missing or duplicate mapping IDs')
    seen, summary = set(), []
    for n in range(1, 9):
        rows = csv_read(base / f'test_round_{n:02d}.csv')
        ids = [r['image_id'] for r in rows]
        if len(ids) != (216 if n == 1 else 500) or len(set(ids)) != len(ids) or seen.intersection(ids):
            raise ValueError('Round size or duplicate IDs')
        for row in rows:
            i = row['image_id']
            if i not in index or round_for(i) != n or int(index[i]['round']) != n:
                raise ValueError('Wrong round assignment')
            path = Path(row['image_path'])
            if path.parent.resolve() != (ROOT / '테스트용데이터').resolve() or path.stem != i or not path.is_file():
                raise ValueError('Missing or invalid test image path')
            if index[i].get('product_reference_path'): validate_product_reference(index[i])
        exposed = sum(index[i]['seen_in_development'] == 'true' for i in ids)
        if exposed != ({1: 206, 2: 499}.get(n, 0)):
            raise ValueError('Initial development exposure mismatch')
        seen.update(ids)
        summary.append(dict(round=n, group=group_name(n), cpus=cpu_set(n), images=len(ids),
                            initial_development=exposed, initial_unused=len(ids)-exposed,
                            existing_product_references=sum(bool(index[i].get('product_reference_path')) for i in ids),
                            identified_source_missing_file=sum(index[i].get('mapping_status')=='source_identified_file_missing' for i in ids),
                            unresolved_originals=sum(not index[i]['original_id'] for i in ids)))
    if seen != index.keys(): raise ValueError('Manifest coverage mismatch')
    return dict(policy=POLICY, images=len(seen), rounds=summary, duplicates=0, missing=0)

def prepare(base=BASE, source=LEGACY_BASE):
    base, source = Path(base), Path(source)
    if base.resolve() == source.resolve() or base.exists():
        raise ValueError('Use a new output directory; existing history is immutable')
    old_lock = read(source / 'manifest_lock.json')
    for name, sha in old_lock.items():
        if digest(source / name) != sha: raise ValueError('Legacy input changed: ' + name)
    mapping = csv_read(source / 'test_to_original_mapping.csv')
    manifests = {r['image_id']: r for n in range(1, 9) for r in csv_read(source / f'test_round_{n:02d}.csv')}
    legacy = read(ROOT / 'artifacts/date-recognition-repair-20260910/manifest.json')
    hashes = {r['sha256'] for r in legacy['included']}
    if len(hashes) != 705 or len(manifests) != 3716: raise ValueError('Legacy inventory mismatch')
    for row in mapping:
        if (row['seen_in_development'] == 'true') != (row['test_sha256'] in hashes):
            raise ValueError('Exposure history mismatch')
        row['legacy_round'] = row['round']
        row['round'] = str(round_for(row['test_id']))
    base.mkdir(parents=True)
    write(base / 'plan.json', dict(policy=POLICY, groups=GROUPS, initial_unused_round2='AMLT000263',
          accuracy_target=.95, seconds_per_image_target=3, hard_timeout_seconds=2400,
          legacy_workspace=str(source.resolve()), execution_started=False,
          scope='Implementation approval only; no future report review or training approval implied'))
    for n in range(1, 9):
        rows = [manifests[r['test_id']] for r in sorted(mapping, key=lambda r: int(r['test_id'][4:])) if int(r['round']) == n]
        csv_write(base / f'test_round_{n:02d}.csv', rows, ['image_id', 'image_path'])
    csv_write(base / 'test_to_original_mapping.csv', mapping, list(mapping[0]))
    queue = [dict(test_id=r['test_id'], round=r['round'], reason='Derivative provenance requires review')
             for r in mapping if not r['original_id']]
    csv_write(base / 'mapping_review_queue.csv', queue, ['test_id', 'round', 'reason'])
    names = ['plan.json', 'test_to_original_mapping.csv', 'mapping_review_queue.csv',
             *[f'test_round_{n:02d}.csv' for n in range(1, 9)]]
    write(base / 'manifest_lock.json', {name: digest(base / name) for name in names})
    history = [source / 'rounds/round_01' / name for name in ('state.json', 'report.json', 'runtime.json', 'submission.csv')]
    write(base / 'legacy_history.json', dict(source_lock=old_lock,
          round1={p.name: dict(path=str(p), sha256=digest(p)) for p in history if p.exists()},
          round1_completion_imported=False,
          note='Original artifacts are references, not a claim that round 1 training is complete.'))
    summary = verify(base)
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
