"""Approved original-only candidate and group integration training; never promote in-place."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, read, write, digest, csv_read
from scripts.grouped_plan import POLICY, members, group_name, cpu_set, verify
from scripts.grouped_rounds import (now, exclusive, group_dir, round_dir, execution_release,
    prior_completion, require_pair_scored, report_approval, evidence, checked_evidence,
    source_lock, model_lock, child_environment, render_report)
from scripts.sequential_rounds import build_admission, cumulative_partition


def training_bindings(base, number, config, groups=None, pool=None, code_root=None):
    from scripts.train_recognition_cpu import CHECKPOINT, CHECKPOINT_SHA256
    if digest(CHECKPOINT) != CHECKPOINT_SHA256: raise ValueError('Initial checkpoint changed')
    execution = execution_release(base, number)
    bindings = dict(manifest_sha256=digest(Path(base) / f'test_round_{number:02d}.csv'),
                    mapping_sha256=digest(Path(base) / 'test_to_original_mapping.csv'),
                    code=execution['code'], model=execution['model'],
                    training_code=source_lock(code_root or ROOT), config_sha256=digest(config),
                    initial_checkpoint_sha256=CHECKPOINT_SHA256)
    if groups: bindings['groups_sha256'] = digest(groups)
    if pool: bindings['pool_sha256'] = digest(pool)
    return bindings


def validate_samples(base, admitted, samples):
    """The approved pool binds every crop to its admitted original annotation."""
    test_root = (ROOT / '테스트용데이터').resolve()
    augmented_hashes = {r['test_sha256'] for r in csv_read(Path(base) / 'test_to_original_mapping.csv')
                        if r['augmented'] == 'true'}
    result = {}
    for sample in samples:
        row = admitted.get(sample['image_id'])
        if row is None: continue
        crop = Path(sample['crop_path']).resolve()
        if crop == test_root or test_root in crop.parents:
            raise ValueError('Test directory cannot supply training crops')
        actual = digest(crop)
        if actual in augmented_hashes: raise ValueError('Pre-existing augmented test bytes cannot train')
        if sample['record_sha256'] != row['annotation_sha256'] or actual != sample['crop_sha256']:
            raise ValueError('Approved original/crop linkage changed')
        if not sample['transcription'] or len(sample['transcription']) > 25:
            raise ValueError('Invalid recognition transcription')
        key = str(crop).casefold()
        if key in result and result[key] != sample: raise ValueError('Conflicting crop records')
        result[key] = sample
    return list(result.values())


def create_training_release(base, number, approval_path, config_path, group_path=None, pool_path=None, integration=False, code_root=None):
    """Prepare frozen training inputs only after report review; does not optimize."""
    import yaml
    from scripts.train_recognition_cpu import CHECKPOINT, DICTIONARY, SEED
    base = Path(base)
    if integration: number = members(number)[0]
    verify(base)
    require_pair_scored(base, number)
    target = group_dir(base, number) / 'integration' if integration else round_dir(base, number)
    if (target / 'training_release.json').exists(): raise ValueError('Training release exists; retain its history')
    previous = prior_completion(base, number)
    previous_release = read(checked_evidence(previous['training_release'])) if previous else {}
    admitted = dict(previous_release.get('admitted', {}))
    old_roles = dict(previous_release.get('group_roles', {}))
    sources = []
    origin = Path(code_root or ROOT).resolve()
    bindings = training_bindings(base, number, config_path, group_path, pool_path, origin)
    if integration:
        number = members(number)[0]
        overview = target / 'review.json'
        if not overview.exists(): raise ValueError('Run integration-review and obtain approval first')
        reports, samples, input_releases = {}, [], []
        for n in members(number):
            dest = round_dir(base, n)
            state = read(dest / 'state.json')
            if state['status'] != 'candidate_complete': raise ValueError('Both candidates must finish before integration')
            candidate = read(checked_evidence(state['candidate']))
            checked_evidence(candidate['selection'])
            value = validate_training(checked_evidence(state['release']))
            input_releases.append(evidence(dest / 'training_release.json'))
            checked_evidence(read(target / 'review.json')['candidate_evaluations'][str(n)])
            for i, row in value['admitted'].items():
                if i in admitted and admitted[i]['original_sha256'] != row['original_sha256']:
                    raise ValueError('Original conflict between rounds')
                admitted[i] = row
            samples.extend(value['samples'])
            reports[str(n)] = state['report']
        overview = target / 'review.json'
        # This review must exist before the user can bind an integration approval.
        if not overview.exists(): raise ValueError('Run integration-review and obtain approval first')
        review = read(overview)
        if review['round_reports'] != reports or review['input_releases'] != input_releases:
            raise ValueError('Integration review inputs changed')
        bindings.update(round_reports=reports, input_releases=input_releases, rounds=list(members(number)))
        report_approval(approval_path, 'train_integration', number, overview, bindings)
        report_path = overview
        sources = input_releases
    else:
        if group_path is None or pool_path is None: raise ValueError('Reviewed groups and recognition pool required')
        state = read(round_dir(base, number) / 'state.json')
        if state['status'] != 'awaiting_user_review': raise ValueError('Round not awaiting reviewed training')
        report_path = checked_evidence(state['report'])
        report_approval(approval_path, 'train', number, report_path, bindings)
        admitted = build_admission(csv_read(base / 'test_to_original_mapping.csv'), number, admitted, read(group_path))
        samples = [json.loads(line) for line in Path(pool_path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        # Earlier admitted originals use their earlier approved crops too.
        samples = list(previous_release.get('samples', [])) + samples
        sources = [evidence(group_path), evidence(pool_path)]
    samples = validate_samples(base, admitted, samples)
    with exclusive(base / 'locks/group_roles.lock'):
        registry_path = base / 'group_roles.json'
        registry = read(registry_path) if registry_path.exists() else old_roles
        if any(registry.get(g) != role for g, role in old_roles.items()): raise ValueError('Permanent group role changed')
        registry = cumulative_partition(list(admitted.values()), registry)
        roles = {r['group_id']: registry[r['group_id']] for r in admitted.values()}
        lists = {role: [] for role in ('optimizer_train', 'inner_validation')}
        for sample in samples:
            role = roles[admitted[sample['image_id']]['group_id']]
            lists[role].append(str(Path(sample['crop_path']).resolve()) + '\t' + sample['transcription'])
        if any(not rows for rows in lists.values()): raise ValueError('Both partitions require usable crops')
        config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
        epochs = config['Global']['epoch_num']
        if type(epochs) is not int or not 1 <= epochs <= 75: raise ValueError('Approved epoch count must be 1..75')
        target.mkdir(parents=True, exist_ok=True)
        for role, lines in lists.items():
            (target / (role + '.txt')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        snapshot = target / 'training_code'
        if snapshot.exists(): raise ValueError('Training code snapshot already exists')
        for name in bindings['training_code']:
            path = snapshot / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin / name, path)
        if source_lock(snapshot) != bindings['training_code'] or source_lock(origin) != bindings['training_code']:
            raise ValueError('Training source changed during snapshot')
        output = target / 'model'
        global_config = config['Global']
        global_config.update(use_gpu=False, distributed=False, seed=SEED, pretrained_model=str(CHECKPOINT),
            checkpoints=None, character_dict_path=str(DICTIONARY), save_model_dir=str(output),
            save_res_path=str(output / 'predicts.txt'), save_epoch_step=1)
        for section, role in [('Train', 'optimizer_train'), ('Eval', 'inner_validation')]:
            config[section]['dataset']['label_file_list'] = [str((target / (role + '.txt')).resolve())]
            config[section]['dataset']['data_dir'] = str(ROOT)
            config[section]['loader'].update(num_workers=0, drop_last=False)
        effective = target / 'effective_config.yml'
        effective.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
        value = dict(policy=POLICY, base=str(base.resolve()), round=number, integration=integration,
            created_at=now(), admitted=admitted, group_roles=roles, samples=samples,
            approval=evidence(approval_path), report=evidence(report_path), bindings=bindings,
            sources=sources, code_root=str(snapshot), training_code=bindings['training_code'],
            approved_config=evidence(config_path), effective_config=evidence(effective),
            initial_checkpoint=evidence(CHECKPOINT), dictionary=evidence(DICTIONARY), output_dir=str(output),
            partitions={r: evidence(target / (r + '.txt')) for r in lists})
        write(target / 'training_release.json', value)
        write(registry_path, registry)
    if not integration:
        state.update(status='originals_admitted', release=evidence(target / 'training_release.json'))
        write(round_dir(base, number) / 'state.json', state)
        render_report(base, number)
    return value


def integration_review(base, number):
    dest = group_dir(base, number) / 'integration'
    reports, inputs, candidates, evaluations = {}, [], [], {}
    for n in members(number):
        state = read(round_dir(base, n) / 'state.json')
        if state['status'] != 'candidate_complete': raise ValueError('Both candidates must finish')
        checked_evidence(state['report'])
        checked_evidence(state['candidate'])
        reports[str(n)] = state['report']
        inputs.append(evidence(checked_evidence(state['release'])))
        candidates.append(state['candidate'])
        evaluation = round_dir(base, n) / 'evaluation/review.json'
        if not evaluation.exists(): raise ValueError('Review cumulative candidate evaluation before integration')
        evaluations[str(n)] = evidence(evaluation)
    path = dest / 'review.json'
    if path.exists(): raise ValueError('Integration review exists; preserve reviewed version')
    write(path, dict(created_at=now(), rounds=list(members(number)), round_reports=reports,
                     input_releases=inputs, candidates=candidates, candidate_evaluations=evaluations,
                     purpose='Separate approval of cumulative original-only integration training'))
    return read(path)


def validate_training(path):
    value = read(path)
    if value['policy'] != POLICY: raise ValueError('Wrong training policy')
    base, number = Path(value['base']), value['round']
    verify(base)
    require_pair_scored(base, number)
    report_approval(checked_evidence(value['approval']), 'train_integration' if value['integration'] else 'train',
                    number, checked_evidence(value['report']), value['bindings'])
    for item in [value['approved_config'], value['effective_config'], value['initial_checkpoint'], value['dictionary'],
                 *value['sources'], *value['partitions'].values()]: checked_evidence(item)
    if source_lock(value['code_root']) != value['training_code']: raise ValueError('Approved training code changed')
    registry = read(base / 'group_roles.json')
    if any(registry.get(g) != role for g, role in value['group_roles'].items()): raise ValueError('Group role changed')
    for row in value['admitted'].values():
        original = Path(row['original_path']).resolve()
        if original.parent != (ROOT / '학습대상데이터').resolve() or digest(original) != row['original_sha256']:
            raise ValueError('Admitted original changed or outside original directory')
        checked_evidence(dict(path=row['annotation_path'], sha256=row['annotation_sha256']))
    validate_samples(base, value['admitted'], value['samples'])
    expected = {r: [] for r in ('optimizer_train', 'inner_validation')}
    for sample in value['samples']:
        role = value['group_roles'][value['admitted'][sample['image_id']]['group_id']]
        expected[role].append(str(Path(sample['crop_path']).resolve()) + '\t' + sample['transcription'])
    for role, lines in expected.items():
        if Path(value['partitions'][role]['path']).read_text(encoding='utf-8').splitlines() != lines:
            raise ValueError('Training list not derived from approved originals')
    return value


def train(path, inference_python):
    """Runs in a worker process assigned a CPU slot by the group runner."""
    from scripts.operating_environment import limit_cpu
    from scripts.train_recognition_cpu import run_preflight, RUNTIME, DICTIONARY
    value = validate_training(path)
    cpus = cpu_set(value['round']) if not value['integration'] else [0, 1, 2, 3]
    limit_cpu(cpus)
    output = Path(value['output_dir'])
    if output.exists(): raise ValueError('Training output exists; use a reviewed new attempt')
    output.mkdir(parents=True)
    write(output / 'preflight.json', run_preflight())
    env = {**child_environment(cpus), 'ITDA_GROUPED_RELEASE': str(Path(path).resolve()), 'ITDA_ASSET_ROOT': str(ROOT)}
    snapshot = Path(value['code_root'])
    command = [sys.executable, str(snapshot / 'notebooks/project/run.py'), 'scripts.train_sequential_cpu',
               '-c', str(checked_evidence(value['effective_config']))]
    with (output / 'train.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    validate_training(path)
    selection_path = output / 'selected_checkpoint.json'
    selection = read(selection_path)
    from scripts.recognition_metrics import select_checkpoint
    candidates = [read(p)['metrics'] for p in sorted(output.glob('validation_epoch_*.json'))]
    if select_checkpoint(candidates, patience=5)['checkpoint'] != selection['checkpoint']:
        raise ValueError('Checkpoint selection disagrees with internal validation')
    checkpoint = Path(selection['checkpoint'] + '.pdparams')
    if not checkpoint.is_file(): raise ValueError('Selected checkpoint missing')
    export = output / 'export'
    with (output / 'export.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, str(RUNTIME / 'tools/export_model.py'), '-c', value['effective_config']['path'],
            '-o', f'Global.pretrained_model={selection["checkpoint"]}', 'Global.checkpoints=null',
            f'Global.character_dict_path={DICTIONARY}', f'Global.save_inference_dir={export}',
            'Global.use_gpu=False'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    bundle = output / 'bundle'
    shutil.copytree(execution_release(value['base'], value['round'])['weights'], bundle)
    for name in ('inference.json', 'inference.yml', 'inference.pdiparams'):
        shutil.copy2(export / name, bundle / 'korean_PP-OCRv5_mobile_rec' / name)
    image = next(iter(value['admitted'].values()))['original_path']
    subprocess.run([str(inference_python), str(snapshot / 'notebooks/project/run.py'), 'scripts.check_sequential_export',
                    '--weights', str(bundle), '--image', image, '--report', str(output / 'export_loading.json')],
                   env=env, cwd=ROOT, check=True)
    result = dict(status='candidate_complete', created_at=now(), training_release=evidence(path),
                  selection=evidence(selection_path), checkpoint=evidence(checkpoint),
                  export_loading=evidence(output / 'export_loading.json'), weights=str(bundle), model=model_lock(bundle),
                  code_root=value['code_root'], code=value['training_code'], operational_weights_changed=False)
    dest = Path(path).parent
    write(dest / 'candidate_complete.json', result)
    if not value['integration']:
        state = read(dest / 'state.json')
        state.update(status='candidate_complete', candidate=evidence(dest / 'candidate_complete.json'))
        write(dest / 'state.json', state)
        render_report(value['base'], value['round'])
    return result
