"""Freeze approved original crops and a test-disabled cumulative training release."""
import copy
import json
import math
import os
import random
import shutil
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image
from scripts import ocr_annotations as ann
from scripts.audit_cumulative_1_5 import read, rows, sha, write_new
from scripts.grouped_rounds import source_lock, model_lock


def main():
    root = ann.ROOT
    run = Path(os.environ['ITDA_CUMULATIVE_RUN']).resolve()
    base = run.parent
    audit_dir = run / 'input-audit-01'
    audit = read(audit_dir / 'audit.json')
    for path, digest in audit['files'].items():
        assert sha(path) == digest, path
    old = base / 'joint123-20260914-v1'
    targeted = old / 'targeted-retrain-code-20260914-v1'
    old_release = read(targeted / 'release-02/release.json')
    old_pool = read(old / 'release/pool.json')
    targeted_pool = read(targeted / 'release-02/pool.json')
    assert old_pool['admitted'] == targeted_pool['admitted']
    assert old_pool['group_roles'] == targeted_pool['group_roles']
    mapping = {r['original_id']: r for r in rows(base / 'test_to_original_mapping.csv') if r['round'] in ('1','2','3','4','5')}
    admitted = copy.deepcopy(mapping)
    admitted.update(copy.deepcopy(old_pool['admitted']))
    roles = dict(old_pool['group_roles'])
    group_audit = read(audit_dir / 'new-group-evidence.json')
    uncertain = {i for p in group_audit['validation_link_candidates'] for i in (p['a'], p['b']) if i not in old_pool['admitted']}
    excluded_ids = uncertain | {'AMLC000454', 'AMLC000467'}
    # Only identified conflicts are quarantined; these are not certified product identities.
    for i in set(admitted) - set(old_pool['admitted']):
        group = admitted[i]['group_id']
        assert group not in roles
        roles[group] = 'quarantine' if i in uncertain else 'optimizer_train'
    release_dir = run / 'release'
    release_dir.mkdir(exist_ok=False)
    crop_dir = release_dir / 'crops'
    crop_dir.mkdir()
    config = yaml.safe_load(Path(old_release['config']).read_text(encoding='utf-8'))
    dictionary = Path(config['Global']['character_dict_path'])
    charset = set(dictionary.read_text(encoding='utf-8').replace('\n', '')) | {' '}
    skipped = [dict(image_id=i, reason='unresolved_validation_product_candidate' if i in uncertain else 'inherited_role_conflict') for i in sorted(excluded_ids)]
    samples = [copy.deepcopy(s) for s in old_pool['samples'] if s['image_id'] not in excluded_ids]
    # Historical validation order/targets and corrected crop overlays remain unchanged.
    assert [s for s in samples if s['role'] == 'inner_validation'] == [s for s in targeted_pool['samples'] if s['role'] == 'inner_validation']
    for i in sorted(set(admitted) - set(old_pool['admitted'])):
        if i in excluded_ids:
            continue
        item = admitted[i]
        record = read(item['annotation_path'])
        assert record['review']['status'] == 'approved' and not ann.validate(record, approve=True)
        with Image.open(item['original_path']) as image:
            for region in record['regions']:
                text = region['transcription']
                reason = ('unsupported_region_kind' if region['kind'] not in ('date_line', 'header') else
                          'not_checked_readable' if region['status'] != 'checked' or region['legibility'] != 'readable' else
                          'empty_or_multiline' if not text.strip() or any(c in text for c in '\n\r\t') else
                          'over_length_25' if len(text) > 25 else
                          'unsupported_characters' if not set(text) <= charset else None)
                if reason:
                    skipped.append(dict(image_id=i, region_id=region['region_id'], reason=reason))
                    continue
                path = crop_dir / f'{i}_{region["region_id"]}.png'
                ann.crop(image, region['polygon']).save(path)
                samples.append(dict(image_id=i, crop_path=str(path), crop_sha256=sha(path),
                    transcription=text, region_id=region['region_id'], kind=region['kind'],
                    record_sha256=item['annotation_sha256'], group_id=item['group_id'],
                    role=roles[item['group_id']], seen_in_development=item['seen_in_development'],
                    review_status='approved', approval_source=item['annotation_path']))
    seen, unique = {}, []
    for sample in samples:
        assert sha(sample['crop_path']) == sample['crop_sha256']
        assert sample['record_sha256'] == admitted[sample['image_id']]['annotation_sha256']
        assert sample['role'] == roles[sample['group_id']]
        if sample['crop_sha256'] in seen:
            previous = seen[sample['crop_sha256']]
            assert (previous['transcription'], previous['role']) == (sample['transcription'], sample['role']), 'Conflicting duplicate crop'
            skipped.append(dict(image_id=sample['image_id'], reason='duplicate_crop_bytes'))
            continue
        seen[sample['crop_sha256']] = sample
        unique.append(sample)
    samples = unique
    excluded_hashes = {r['test_sha256'] for r in rows(base / 'excluded_derivatives.csv')}
    assert not excluded_hashes & set(seen)
    train = [s for s in samples if s['role'] == 'optimizer_train']
    valid = [s for s in samples if s['role'] == 'inner_validation']
    assert len(valid) == 25 and all(s['image_id'] not in excluded_ids for s in samples)
    assert {s['group_id'] for s in train}.isdisjoint(s['group_id'] for s in valid)
    assert {admitted[s['image_id']]['round'] for s in train} == {'1','2','3','4','5'}
    random.Random(20260911).shuffle(train)
    for name, items in [('optimizer_train', train), ('inner_validation', valid)]:
        with (release_dir / (name + '.txt')).open('x', encoding='utf-8') as stream:
            stream.write(''.join(s['crop_path'] + '\t' + s['transcription'] + '\n' for s in items))
    write_new(release_dir / 'pool.json', dict(admitted=admitted, group_roles=roles, samples=samples,
        policy='Approved crops; fixed prior validation roles; unresolved validation-neighbour originals quarantined; global product independence unverified'))
    write_new(release_dir / 'excluded.json', dict(originals=sorted(excluded_ids), entries=skipped))
    write_new(release_dir / 'group_roles.json', roles)
    authorization = dict(read(run / 'instruction.json'), online_local_training_allowed=True,
        external_upload_allowed=False, shared_weights_promotion_allowed=False,
        policy_interpretation='New approved crops admitted except unresolved validation-neighbour originals. No group identities certified by similarity or SHA.',
        prior_authorization=str(old / 'release/authorization.json'), full_product_independence_guaranteed=False)
    write_new(release_dir / 'authorization.json', authorization)
    checkpoint = targeted / 'training-run/joint123-attempt02/epoch_001.pdparams'
    output = run / 'training-run'
    config['Global'].update(pretrained_model=str(checkpoint.with_suffix('')), save_model_dir=str(output), save_res_path=str(output / 'predicts.txt'))
    for section, partition in [('Train','optimizer_train'), ('Eval','inner_validation')]:
        config[section]['dataset']['label_file_list'] = [str(release_dir / (partition + '.txt'))]
    with (release_dir / 'config.yml').open('x', encoding='utf-8') as stream:
        stream.write(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    snapshot = run / 'code'
    code = source_lock(root)
    for relative in code:
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
    assert source_lock(snapshot) == code == source_lock(root)
    bundle = run / 'starting_bundle'
    shutil.copytree(root / 'weights/paddle', bundle)
    assert model_lock(bundle) == model_lock(root / 'weights/paddle')
    reference = targeted / 'training-run/joint123-attempt02/validation_001.json'
    protected = dict(audit['files'])
    for p in [old / 'release/pool.json', reference, Path(old_release['fields']), dictionary, run / 'instruction.json',
              audit_dir / 'audit.json', audit_dir / 'new-group-evidence.json', audit_dir / 'latest-final-date-overlay.json',
              root / 'weights/adopted_model.json', *release_dir.glob('*.*')]:
        protected[str(p)] = sha(p)
    protected.update({str(snapshot / relative): digest for relative, digest in code.items()})
    protected.update({str(p): sha(p) for p in bundle.rglob('*') if p.is_file()})
    release = dict(kind='cumulative-1-5-single-epoch-v1', authorization=dict(path=str(release_dir / 'authorization.json'), sha256=sha(release_dir / 'authorization.json')),
        pool=str(release_dir / 'pool.json'), config=str(release_dir / 'config.yml'), fields=old_release['fields'],
        runtime=old_release['runtime'], runtime_commit=old_release['runtime_commit'],
        bundle=str(bundle), epoch_zero_reference=str(reference), round1_validation_count=25,
        protected_files=protected, scope=dict(originals=2110, optimizer_crops=len(train), validation_crops=len(valid),
            optimizer_steps=math.ceil(len(train)/8), cpus=[0,1,2,3], threads=4),
        whole_image_test_allowed=False, shared_weight_promotion=False, formal_round_state_mutation=False)
    write_new(release_dir / 'release.json', release)
    from scripts.train_cumulative_1_5 import validate_release
    validate_release()
    summary = dict(status='release_ready', optimizer_started=False, optimizer_crops=len(train), validation_crops=len(valid),
        optimizer_originals=len({s['image_id'] for s in train}),
        optimizer_round_crops=dict(Counter(admitted[s['image_id']]['round'] for s in train)),
        new_crop_kinds=dict(Counter(s.get('kind', 'historical_date_line') for s in train)),
        exclusions=dict(Counter(s['reason'] for s in skipped)), quarantine_originals=len(uncertain),
        release_sha256=sha(release_dir / 'release.json'), full_image_tests='held_until_separate_user_instruction')
    write_new(release_dir / 'preflight.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
