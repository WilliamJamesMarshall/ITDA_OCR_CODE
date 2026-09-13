"""Carry the user-closed first round into grouped execution without rerunning it."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read, csv_write, digest
from scripts.grouped_plan import BASE, verify
from scripts.grouped_rounds import (now, exclusive, evidence, checked_evidence, source_lock,
    model_lock, round_dir, group_dir, approval, freeze, render_report)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def validate_legacy_completion(base, value):
    """An explicit administrative transition, never a new grouped performance result."""
    if value.get('completion_kind') != 'legacy_user_closure' or value['rounds'] != [1]:
        raise ValueError('Legacy closure is only valid for round 1')
    history = read(checked_evidence(value['evaluation']))
    required = {'closure', 'development_runtime', 'comparison', 'predictions', 'trace', 'initial_report',
                'legacy_training_release', 'legacy_approval', 'legacy_review', 'legacy_pool', 'legacy_groups',
                'training_summary', 'selected_checkpoint', 'selected_parameters', 'optimizer_train', 'inner_validation'}
    required.update(f'{arm}_{name}' for arm in ('A', 'B') for name in (
        'runtime.json', 'selected_checkpoint.json', 'epoch_001.pdparams', 'effective_config.yml',
        'validation_001.json', 'export_equivalence.json', 'train.log'))
    if not required <= history['evidence'].keys():
        raise ValueError('Historical closure evidence is incomplete')
    for item in history['evidence'].values(): checked_evidence(item)
    closure = read(checked_evidence(history['evidence']['closure']))
    if (closure['status'] != 'closed_by_user' or closure['selected_baseline'] != 'remediation_12'
            or not closure['round1_testing_ended'] or not closure['round1_machine_learning_ended']):
        raise ValueError('The historical round has not been closed by its user')
    if canonical(value['model']) != closure['model_manifest_sha256']:
        raise ValueError('Retained model differs from the user-closed model')
    runtime = read(checked_evidence(history['evidence']['development_runtime']))
    expected = {k: v for k, v in runtime['code'].items()
                if k.startswith('notebooks/project/src/') or k == 'predict.ipynb'}
    if any(value['code'].get(k) != v for k, v in expected.items()):
        raise ValueError('Retained inference differs from the closed development run')
    if value['protected_correct'] != history['protected_correct'] or len(value['protected_correct']) != 204:
        raise ValueError('Historical protection set changed')
    approved = approval(checked_evidence(value['approval']), 'adopt_round1_closure', 1,
        dict(closure_sha256=digest(history['evidence']['closure']['path']),
             code=value['code'], model=value['model'], reviewed_status_sha256=history['reviewed_status_sha256']))
    if approved.get('scope') != 'close_legacy_round1_and_prepare_stage2_only':
        raise ValueError('Wrong administrative transition scope')
    carry = read(checked_evidence(value['training_release']))
    legacy_release = read(checked_evidence(history['evidence']['legacy_training_release']))
    if carry['group_roles'] != legacy_release['group_roles'] or carry['admitted'] != legacy_release['admitted']:
        raise ValueError('Legacy admitted originals or permanent roles changed')
    if carry.get('optimizer_execution_authorized') is not False:
        raise ValueError('Carryover must not authorize a new training run')
    registry = read(Path(base) / 'group_roles.json')
    if any(registry.get(g) != role for g, role in carry['group_roles'].items()):
        raise ValueError('Permanent group role changed after legacy adoption')
    return history


def reconcile_approved_190(base, legacy):
    """Version only the stale annotation reference; preserve IDs, pixels and exposure."""
    mapping_path = base / 'test_to_original_mapping.csv'
    rows = csv_read(mapping_path)
    row = next(r for r in rows if r['test_id'] == 'AMLT000190')
    current = digest(row['annotation_path'])
    if current == row['annotation_sha256']: return None
    proof_path = legacy / 'rounds/round_01/revisions/ground_truth_190/corrections.json'
    proof, record = read(proof_path), read(row['annotation_path'])
    expected = dict(test_id='AMLT000190', original_id='AMLC000190', after='2026-11-22')
    change = next(c for c in proof['changes'] if c['test_id'] == expected['test_id'])
    if (proof['actor'] != 'user' or any(change[k] != v for k, v in expected.items())
            or record['final_date'] != change['after']
            or record['final_date_review']['source']['instruction'] != proof['instruction']
            or record['image_sha256'] != row['original_sha256']):
        raise ValueError('190 annotation requires the existing explicit correction evidence')
    revision = base / 'mapping_revisions' / ('annotation_190_' + now().replace(':', '-'))
    revision.mkdir(parents=True, exist_ok=False)
    for name in ('test_to_original_mapping.csv', 'manifest_lock.json'):
        shutil.copy2(base / name, revision / name)
    before = row['annotation_sha256']
    row['annotation_sha256'] = current
    csv_write(mapping_path, rows, list(rows[0]))
    lock = read(base / 'manifest_lock.json')
    lock['test_to_original_mapping.csv'] = digest(mapping_path)
    write(base / 'manifest_lock.json', lock)
    write(revision / 'change.json', dict(kind='approved_annotation_reference', test_id=row['test_id'],
        old_sha256=before, new_sha256=current, approval=evidence(proof_path),
        changed_fields=['annotation_sha256'], pixels_and_membership_changed=False))
    verify(base)
    return evidence(revision / 'change.json')


def approved_carryover(base, release):
    from scripts.grouped_training import validate_samples
    pool = [json.loads(line) for line in checked_evidence(release['pool']).read_text(
        encoding='utf-8-sig').splitlines() if line.strip()]
    index = {str(Path(s['crop_path']).resolve()).casefold(): s for s in pool}
    samples = []
    for role, item in release['partitions'].items():
        for line in checked_evidence(item).read_text(encoding='utf-8-sig').splitlines():
            path, text = line.split('\t', 1)
            sample = index[str(Path(path).resolve()).casefold()]
            row = release['admitted'][sample['image_id']]
            if sample['transcription'] != text or release['group_roles'][row['group_id']] != role:
                raise ValueError('Historical crop/partition mismatch')
            samples.append(sample)
    for row in release['admitted'].values():
        if digest(row['original_path']) != row['original_sha256']:
            raise ValueError('Historical original changed')
        checked_evidence(dict(path=row['annotation_path'], sha256=row['annotation_sha256']))
    return validate_samples(base, release['admitted'], samples)


def prepare(base, instruction, source_reference):
    base = Path(base)
    verify(base)
    legacy = Path(read(base / 'plan.json')['legacy_workspace'])
    dest = group_dir(base, 1)
    if (dest / 'completion.json').exists(): raise ValueError('Already adopted; use status, do not overwrite')
    from scripts.run_round_groups import status
    before = status(base)
    if before['current_stage'] != 1 or before['active_jobs']:
        raise ValueError('Adoption requires an idle first stage')
    closure_path = legacy / 'round_01_closure_20260913/closure.json'
    closure = read(closure_path)
    runtime_path = legacy / 'remediation_12/candidate_01/runtime.json'
    runtime = read(runtime_path)
    snapshot = Path(closure['full_code_snapshot'])
    if {k: digest(snapshot / k) for k in runtime['code']} != runtime['code']:
        raise ValueError('Historical code snapshot changed')
    if canonical(runtime['code']) != closure['code_manifest_sha256']:
        raise ValueError('Historical code manifest differs from closure')
    current_code = source_lock(ROOT)
    inference = {k: v for k, v in runtime['code'].items()
                 if k.startswith('notebooks/project/src/') or k == 'predict.ipynb'}
    if any(current_code.get(k) != v for k, v in inference.items()):
        raise ValueError('Current inference differs from the selected legacy version')
    model = model_lock(Path(closure['selected_model']))
    if model != runtime['model'] or canonical(model) != closure['model_manifest_sha256']:
        raise ValueError('Selected historical model changed')
    comparison_path = legacy / 'remediation_12/comparison.json'
    comparison = read(comparison_path)
    predictions_path = legacy / 'remediation_12/candidate_01/submission.csv'
    predictions = {r['image_id']: r['final_date'] for r in csv_read(predictions_path)}
    if (len(predictions) != 216 or len(comparison['detail']) != 216 or comparison['correct'] != 204
            or comparison['regressions'] or comparison['stage_errors'] or runtime['summary']['failures']):
        raise ValueError('Historical development coverage/errors do not support closure')
    for row in comparison['detail']:
        if predictions.get(row['image_id']) != row['after'] or row['after_correct'] != (row['after'] == row['expected']):
            raise ValueError('Development comparison and saved predictions disagree')
    protected = sorted(r['image_id'] for r in comparison['detail'] if r['after_correct'])
    release_path = legacy / 'remediation_13/workflow/rounds/round_01/training_release.json'
    release = read(release_path)
    for key in ('approval', 'report', 'groups', 'pool', 'manifest'): checked_evidence(release[key])
    approval(checked_evidence(release['approval']), 'train', 1, dict(
        report_sha256=release['report']['sha256'], manifest_sha256=release['manifest']['sha256'],
        code=release['code'], model=release['model']))
    samples = approved_carryover(base, release)
    ev = dict(closure=evidence(closure_path), development_runtime=evidence(runtime_path),
        comparison=evidence(comparison_path), predictions=evidence(predictions_path),
        trace=evidence(legacy / 'remediation_12/candidate_01/submission.csv.trace.jsonl'),
        initial_report=evidence(round_dir(base, 1) / 'initial_report.json'),
        legacy_training_release=evidence(release_path), legacy_approval=release['approval'],
        legacy_review=release['report'], legacy_pool=release['pool'], legacy_groups=release['groups'],
        training_summary=evidence(legacy / 'remediation_13/final_summary.json'),
        selected_checkpoint=evidence(legacy / 'remediation_05/model/selected_checkpoint.json'),
        selected_parameters=evidence(legacy / 'remediation_05/model/whole_epoch_000.pdparams'))
    for role, item in release['partitions'].items(): ev[role] = item
    for arm in ('A', 'B'):
        train = legacy / f'remediation_13/training_{arm}'
        result = read(train / 'runtime.json')
        if result['status'] != 'completed' or result['epochs_completed'] != 1:
            raise ValueError('Historical A/B training not completed')
        for name in ('runtime.json', 'selected_checkpoint.json', 'epoch_001.pdparams',
                     'effective_config.yml', 'validation_001.json', 'export_equivalence.json', 'train.log'):
            ev[f'{arm}_{name}'] = evidence(train / name)
    with exclusive(base / 'locks/metadata.lock'):
        if (base / 'locks/execution.lock').exists(): raise ValueError('An execution is active')
        dest.mkdir(parents=True, exist_ok=False)
        for name in ('state.json', 'report.md'):
            shutil.copy2(round_dir(base, 1) / name, dest / ('before_' + name))
        write(dest / 'reviewed_status.json', before)
        revision = reconcile_approved_190(base, legacy)
        if revision: ev['annotation_revision'] = revision
        code_root = dest / 'retained_code'
        for name in current_code:
            target = code_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        if source_lock(code_root) != current_code or source_lock(ROOT) != current_code:
            raise ValueError('Code changed while snapshotting')
        carry = dict(kind='historical_approved_carryover', admitted=release['admitted'],
            group_roles=release['group_roles'], samples=samples, source=evidence(release_path),
            optimizer_execution_authorized=False)
        write(dest / 'historical_carryover.json', carry)
        roles_path = base / 'group_roles.json'
        if roles_path.exists() and read(roles_path) != release['group_roles']:
            raise ValueError('Existing group registry conflicts with historical roles')
        write(roles_path, release['group_roles'])
        history = dict(created_at=now(), evidence=ev, protected_correct=protected,
            reviewed_status_sha256=digest(dest / 'reviewed_status.json'),
            scope='User-closed historical development; not a new grouped qualification or performance test',
            accuracy=204/216, historical_pipeline_seconds=601.961, new_notebook_timing_verified=False,
            new_training_executed=False, unresolved_retained=12, candidates_adopted=False)
        write(dest / 'legacy_closure_review.json', history)
        write(dest / 'transition_instruction.json', dict(actor='user', action='adopt_round1_closure', round=1,
            instruction=instruction, source_reference=source_reference, approved_at=now(),
            timestamp_note='Capture time of the preparation instruction, not the historical closure message',
            scope='close_legacy_round1_and_prepare_stage2_only',
            closure_sha256=digest(closure_path), reviewed_status_sha256=history['reviewed_status_sha256'],
            code=current_code, model=model, formal_test_start_authorized=False))
        value = dict(status='complete', completion_kind='legacy_user_closure', created_at=now(), rounds=[1],
            weights=closure['selected_model'], model=model, code_root=str(code_root), code=current_code,
            training_release=evidence(dest / 'historical_carryover.json'),
            approval=evidence(dest / 'transition_instruction.json'), evaluation=evidence(dest / 'legacy_closure_review.json'),
            protected_correct=protected, candidate_accepted=False, targets_met=False, development_100=False,
            workflow_finished=False, independent_final_test=False,
            scope='Administrative legacy closure adopted for stage 2 preparation; historical shortfall retained')
        validate_legacy_completion(base, value)
        write(dest / 'completion.json', value)
        state = read(round_dir(base, 1) / 'state.json')
        state.update(status='complete', completion_kind='legacy_user_closure', completion=evidence(dest / 'completion.json'))
        write(round_dir(base, 1) / 'state.json', state)
        write(round_dir(base, 1) / 'completion.json', dict(group_completion=evidence(dest / 'completion.json')))
        render_report(base, 1)
    frozen = freeze(base, 2)
    return dict(current_stage=2, rounds=[2, 3], release=evidence(group_dir(base, 2) / 'release/release.json'),
                model_manifest=canonical(frozen['model']), code_manifest=canonical(frozen['code']),
                historical_originals=len(carry['admitted']), historical_crops=len(samples),
                formal_tests_started=False, offline_qualification_pending=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=BASE)
    parser.add_argument('--instruction', required=True)
    parser.add_argument('--source-reference', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.workspace, args.instruction, args.source_reference), ensure_ascii=False, indent=2))
