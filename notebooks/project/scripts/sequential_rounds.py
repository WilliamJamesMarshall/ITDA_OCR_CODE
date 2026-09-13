"""Eight-round workflow. Evidence gates prevent accidental release, not malicious forgery.

Approval JSON must transcribe an actual user instruction; this module never creates it.
All detailed artifacts live outside the submission tree.
"""
import argparse
import hashlib
import json
import math
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path
from scripts.prepare_sequential_rounds import BASE, ROOT, csv_read, digest, read, write

SEED = 20260911

def checked_evidence(evidence):
    path = Path(evidence['path'])
    if not path.is_file() or digest(path) != evidence['sha256']:
        raise ValueError('Evidence missing or changed: ' + str(path))
    return path

def evidence(path):
    return {'path': str(Path(path).resolve()), 'sha256': digest(path)}

def code_lock():
    paths = [ROOT / 'predict.ipynb', ROOT / 'requirements.txt',
             *sorted((ROOT / 'notebooks/project').rglob('*.py')),
             *sorted((ROOT / 'notebooks/project/configs').rglob('*.yml'))]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}

def model_lock(path):
    files = {p.relative_to(path).as_posix(): digest(p) for p in sorted(path.rglob('*')) if p.is_file()}
    if not files: raise ValueError('No model files')
    return files

def check_manifests(base):
    for name, sha in read(base / 'manifest_lock.json').items():
        if digest(base / name) != sha: raise ValueError('Frozen manifest changed: ' + name)

def round_dir(base, number):
    if number not in range(1, 9): raise ValueError('Round must be 1..8')
    return base / 'rounds' / f'round_{number:02d}'

def approval(path, action, number, bindings):
    value = read(path)
    if value.get('actor') != 'user' or value.get('action') != action or value.get('round') != number:
        raise ValueError('Explicit user approval required for this action and round')
    from datetime import datetime
    if not value.get('instruction', '').strip() or not value.get('source_reference', '').strip():
        raise ValueError('Actual user instruction and source reference required')
    stamp = datetime.fromisoformat(value['approved_at'])
    if stamp.tzinfo is None: raise ValueError('Approval timestamp must include timezone')
    for key, expected in bindings.items():
        if value.get(key) != expected: raise ValueError('Approval binding changed: ' + key)
    return value

def cumulative_partition(rows, previous):
    """Assign only newly admitted groups; immutable train/validation roles."""
    result = dict(previous)
    groups = {r['group_id'] for r in rows}
    if any(not g for g in groups): raise ValueError('Missing group')
    if any(v not in ('optimizer_train', 'inner_validation') for v in result.values()):
        raise ValueError('Invalid permanent role')
    new = sorted(groups - result.keys(), key=lambda g: hashlib.sha256(f'{SEED}:{g}'.encode()).hexdigest())
    sizes = {g: len({r['original_id'] for r in rows if r['group_id'] == g}) for g in new}
    target = sum(sizes.values()) * .1
    count = 0
    for g in new:
        use_validation = abs(count + sizes[g] - target) < abs(count - target)
        result[g] = 'inner_validation' if use_validation else 'optimizer_train'
        if use_validation: count += sizes[g]
    return result

def build_admission(mapping, number, previous, groups):
    current = [r for r in mapping if int(r['round']) == number]
    if not current or any(not r['original_id'] for r in current):
        raise ValueError('Round has unresolved original mappings')
    admitted = dict(previous)
    for row in current:
        image_id = row['original_id']
        group = groups.get(image_id)
        if not group or group.get('verified') is not True or not group.get('evidence'):
            raise ValueError('Product group review incomplete: ' + image_id)
        original = Path(row['original_path']).resolve()
        if original.parent != (ROOT / '학습대상데이터').resolve():
            raise ValueError('Only original training directory is allowed')
        if digest(original) != row['original_sha256']:
            raise ValueError('Original changed')
        annotation = checked_evidence({'path': row['annotation_path'], 'sha256': row['annotation_sha256']})
        record = read(annotation)
        if record['review']['status'] != 'approved' or record['image_sha256'] != row['original_sha256']:
            raise ValueError('Annotation not approved for original')
        if image_id in admitted:
            if admitted[image_id]['group_id'] != group['group_id']: raise ValueError('Group changed after admission')
            continue
        admitted[image_id] = {**row, 'group_id': group['group_id'], 'first_admitted_round': number}
    # Same bytes cannot cross independently assigned groups, even under different IDs.
    hashes = {}
    for row in admitted.values():
        sha = row['original_sha256']
        if sha in hashes and hashes[sha] != row['original_id']: raise ValueError('Duplicate original bytes')
        hashes[sha] = row['original_id']
    return admitted

def release(base, number, approval_path, group_path):
    check_manifests(base)
    dest = round_dir(base, number)
    state = read(dest / 'state.json')
    if state['status'] != 'awaiting_user_review': raise ValueError('Scored report required')
    report = checked_evidence(state['report'])
    approval(approval_path, 'train', number, {'report_sha256': digest(report),
             'manifest_sha256': state['manifest']['sha256'], 'code': state['code'], 'model': state['model']})
    if state['code'] != code_lock(): raise ValueError('Code changed after evaluation; reevaluation required')
    previous, roles = {}, {}
    if number > 1:
        prev = read(round_dir(base, number - 1) / 'training_release.json')
        previous, roles = prev['admitted'], prev['group_roles']
    groups = read(group_path)
    admitted = build_admission(csv_read(base / 'test_to_original_mapping.csv'), number, previous, groups)
    roles = cumulative_partition(list(admitted.values()), roles)
    input_version = base / 'active_training_inputs.json'
    if input_version.exists():
        inputs = read(input_version)
        if inputs.get('round') != number:
            raise ValueError('Training input version belongs to another round')
        pool = checked_evidence(inputs['recognition_pool'])
        checked_evidence(inputs['review_evidence'])
    else:
        pool = ROOT / '학습 및 테스트 결과/02_annotations/exports/20260911T193432620539Z/recognition_pool.jsonl'
    samples = [json.loads(line) for line in pool.read_text(encoding='utf-8').splitlines() if line.strip()]
    files = {}
    for role in ('optimizer_train', 'inner_validation'):
        lines = []
        for item in samples:
            row = admitted.get(item['image_id'])
            if not row or roles[row['group_id']] != role: continue
            if item['record_sha256'] != row['annotation_sha256'] or digest(item['crop_path']) != item['crop_sha256']:
                raise ValueError('Approved recognition crop changed')
            lines.append(str(Path(item['crop_path']).resolve()) + '\t' + item['transcription'])
        if not lines: raise ValueError('Both recognition partitions need usable crops')
        files[role] = lines
    if (dest / 'training_release.json').exists(): raise ValueError('Release already exists')
    for role, lines in files.items():
        (dest / (role + '.txt')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    value = dict(policy='sequential-8-v1', round=number, admitted=admitted, group_roles=roles,
                 approval=evidence(approval_path), report=evidence(report), groups=evidence(group_path),
                 pool=evidence(pool), manifest=state['manifest'], code=state['code'], model=state['model'],
                 partitions={role: evidence(dest / (role + '.txt')) for role in files})
    write(dest / 'training_release.json', value)
    state.update(status='originals_admitted', release=evidence(dest / 'training_release.json'))
    write(dest / 'state.json', state)

def require_training_release(base, number, train_list, validation_list):
    check_manifests(base)
    dest = round_dir(base, number)
    state = read(dest / 'state.json')
    if state['status'] != 'originals_admitted': raise ValueError('No pending approved training release')
    value = read(checked_evidence(state['release']))
    report = checked_evidence(value['report'])
    approval(checked_evidence(value['approval']), 'train', number,
             {'report_sha256': digest(report), 'manifest_sha256': value['manifest']['sha256'],
              'code': value['code'], 'model': value['model']})
    if value['code'] != code_lock(): raise ValueError('Training code changed after approval')
    checked_evidence(value['manifest'])
    checked_evidence(value['groups'])
    pool = checked_evidence(value['pool'])
    sample_index = {str(Path(r['crop_path']).resolve()).casefold(): r
                    for r in map(json.loads, pool.read_text(encoding='utf-8').splitlines())}
    for role, supplied in [('optimizer_train', train_list), ('inner_validation', validation_list)]:
        path = checked_evidence(value['partitions'][role])
        if Path(supplied).resolve() != path.resolve(): raise ValueError('Wrong training list')
        for line in path.read_text(encoding='utf-8').splitlines():
            crop, label = line.split('\t', 1)
            sample = sample_index[str(Path(crop).resolve()).casefold()]
            row = value['admitted'][sample['image_id']]
            if (value['group_roles'][row['group_id']] != role or label != sample['transcription']
                    or digest(crop) != sample['crop_sha256']): raise ValueError('Crop/partition mismatch')
    for row in value['admitted'].values():
        if digest(row['original_path']) != row['original_sha256'] or digest(row['annotation_path']) != row['annotation_sha256']:
            raise ValueError('Admitted source changed')
    if number > 1:
        prior = read(round_dir(base, number - 1) / 'training_release.json')
        if any(value['group_roles'].get(g) != role for g, role in prior['group_roles'].items()):
            raise ValueError('Permanent group role changed')
        if not prior['admitted'].keys() <= value['admitted'].keys(): raise ValueError('Cumulative originals lost')
    return value

def infer(base, number, approval_path):
    """Execute unchanged notebook in an external, labels-free submission copy."""
    check_manifests(base)
    dest = round_dir(base, number)
    if (dest / 'state.json').exists(): raise ValueError('Round already exists; preserve initial evaluation')
    readiness = read(base / 'execution_readiness.json')
    if not readiness.get('formal_environment_verified'): raise ValueError('Formal environment not verified')
    qualification = read(checked_evidence(readiness['environment_evidence']))
    manifest = base / f'test_round_{number:02d}.csv'
    weights = ROOT / 'weights/paddle'
    locks = {'code': code_lock(), 'model': model_lock(weights), 'manifest_sha256': digest(manifest)}
    if qualification['code'] != locks['code'] or qualification['model'] != locks['model']:
        raise ValueError('Code/model changed after environment qualification')
    approval(approval_path, 'start_test', number, locks)
    from scripts.operating_environment import enforce
    execution_environment = enforce()
    if number > 1:
        previous = read(round_dir(base, number - 1) / 'state.json')
        if previous['status'] != 'training_complete': raise ValueError('Previous training/export incomplete')
        completion = read(checked_evidence(previous['completion']))
        if completion['model'] != locks['model']: raise ValueError('Next test must use selected exported model')
    sandbox = dest / 'submission'
    sandbox.mkdir(parents=True)
    for name in ('predict.ipynb', 'requirements.txt', 'download_weights.sh'):
        shutil.copy2(ROOT / name, sandbox / name)
    shutil.copytree(ROOT / 'notebooks/project/src', sandbox / 'notebooks/project/src', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(weights, sandbox / 'weights/paddle')
    images = dest / 'input'
    images.mkdir()
    mapping = {r['test_id']: r for r in csv_read(base / 'test_to_original_mapping.csv')}
    for row in csv_read(manifest):
        source = Path(row['image_path'])
        if digest(source) != mapping[row['image_id']]['test_sha256']: raise ValueError('Input changed')
        shutil.copy2(source, images / source.name)
    state = dict(status='inference_running', round=number, manifest=evidence(manifest),
                 code=locks['code'], model=locks['model'], start_approval=evidence(approval_path))
    write(dest / 'state.json', state)
    output = dest / 'submission.csv'
    env = {**os.environ, 'ITDA_INPUT_DIR': str(images), 'ITDA_OUTPUT_PATH': str(output),
           'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '4'}
    kernel_root = dest / 'jupyter'
    write(kernel_root / 'kernels/python3/kernel.json',
          {'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
           'display_name': 'ITDA frozen Python', 'language': 'python'})
    env['JUPYTER_PATH'] = str(kernel_root)
    started = time.perf_counter()
    try:
        with (dest / 'inference.log').open('w', encoding='utf-8') as log:
            run = subprocess.Popen([sys.executable, '-m', 'nbconvert', '--execute', '--to', 'notebook',
                  '--ExecutePreprocessor.timeout=2400', '--output', 'executed.ipynb', 'predict.ipynb'],
                  cwd=sandbox, env=env, stdout=log, stderr=subprocess.STDOUT,
                  start_new_session=os.name != 'nt')
            try:
                run.wait(timeout=2400)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(run.pid), '/T', '/F'], capture_output=True)
                else:
                    os.killpg(run.pid, signal.SIGKILL)
                run.wait()
                raise
        status = 'completed' if run.returncode == 0 and output.exists() else 'failed'
    except subprocess.TimeoutExpired:
        status = 'timeout'
    runtime = dict(status=status, total_elapsed_seconds=time.perf_counter() - started,
                   images=len(csv_read(manifest)), failures=[],
                   timing_scope='nbconvert process startup and complete notebook execution; setup copies and scorer excluded',
                   p50=None, p95=None, per_image_timing_status='not instrumented in submission notebook')
    runtime['environment'] = readiness['environment_evidence']
    runtime['actual_execution_environment'] = execution_environment
    executed = sandbox / 'executed.ipynb'
    if executed.exists():
        for cell in read(executed)['cells']:
            text = ''.join(''.join(item.get('text', [])) for item in cell.get('outputs', []) if item.get('output_type') == 'stream')
            for index, character in enumerate(text):
                if character != '{': continue
                try: summary, _ = json.JSONDecoder().raw_decode(text[index:])
                except ValueError: continue
                if isinstance(summary, dict) and 'p50_image_seconds' in summary:
                    runtime.update(p50=summary['p50_image_seconds'], p95=summary['p95_image_seconds'],
                                   failures=summary['failures'], pipeline_summary=summary,
                                   per_image_timing_status='pipeline prediction elapsed times; initialization excluded')
    write(dest / 'runtime.json', runtime)
    state.update(status='inference_complete', runtime=evidence(dest / 'runtime.json'),
                 predictions=evidence(output) if output.exists() else None)
    write(dest / 'state.json', state)

def score(base, number, labels_path):
    from scripts.evaluate_pipeline import read_labels, score_predictions
    dest = round_dir(base, number)
    state = read(dest / 'state.json')
    if state['status'] != 'inference_complete': raise ValueError('Finish inference before opening labels')
    runtime = read(checked_evidence(state['runtime']))
    rows = csv_read(checked_evidence(state['manifest']))
    predictions = csv_read(checked_evidence(state['predictions'])) if state['predictions'] else []
    ids = [r['image_id'] for r in rows]
    if any(r['image_id'] not in ids for r in predictions): raise ValueError('Out-of-round prediction')
    labels = read_labels(labels_path)
    # Accept existing numeric IDs only via the exact frozen manifest serial mapping.
    labels = {i: labels.get(i, labels.get(i[4:])) for i in ids}
    if any(v is None for v in labels.values()): raise ValueError('Missing round labels')
    if any(v.get('라벨 상태') not in ('approved', 'manual') for v in labels.values()):
        raise ValueError('Every round label must be approved')
    metrics = score_predictions(labels, predictions, runtime['failures'], expected_ids=ids)
    mapping = {r['test_id']: r for r in csv_read(base / 'test_to_original_mapping.csv')}
    previous = read(round_dir(base, number - 1) / 'training_release.json')['admitted'] if number > 1 else {}
    previous_groups = {r['group_id'] for r in previous.values()}
    strata = {}
    subsets = {'original': [i for i in ids if mapping[i]['augmented'] == 'false'],
               'augmented': [i for i in ids if mapping[i]['augmented'] == 'true'],
               'previous_original': [i for i in ids if mapping[i]['original_id'] in previous],
               'previous_development': [i for i in ids if mapping[i]['seen_in_development'] == 'true'],
               'unexposed_verified': [i for i in ids if mapping[i]['original_id']
                    and mapping[i]['original_id'] not in previous and mapping[i]['group_verified'] == 'true'
                    and mapping[i]['group_id'] not in previous_groups and mapping[i]['seen_in_development'] == 'false'],
               'exposure_unknown': [i for i in ids if not mapping[i]['original_id'] or mapping[i]['group_verified'] != 'true']}
    for name, subset in subsets.items():
        strata[name] = score_predictions(labels, [p for p in predictions if p['image_id'] in subset], runtime['failures'], expected_ids=subset) if subset else None
    elapsed = runtime['total_elapsed_seconds']
    if not math.isfinite(elapsed) or elapsed <= 0: raise ValueError('Invalid elapsed time')
    current = [mapping[i] for i in ids]
    originals = {r['original_id'] for r in current if r['original_id']}
    report = dict(round=number, runtime=runtime, metrics=metrics, strata=strata,
                  mean_seconds=elapsed / len(ids), time_target_seconds=3 * len(ids),
                  time_target_met=runtime['status'] == 'completed' and elapsed <= 3 * len(ids),
                  new_originals=len(originals - previous.keys()), existing_originals=len(originals & previous.keys()),
                  repeated_test_originals=sum(bool(r['original_id']) for r in current) - len(originals),
                  unresolved=sum(not r['original_id'] for r in current),
                  code=state['code'], model=state['model'], manifest=state['manifest'],
                  ground_truth=evidence(labels_path), user_feedback=None, training_approved=False)
    write(dest / 'report.json', report)
    state.update(status='awaiting_user_review', report=evidence(dest / 'report.json'))
    write(dest / 'state.json', state)

def complete_training(base, number, model_directory, inference_python):
    """Export and smoke-load selected weights; promote only after verification."""
    from scripts.train_recognition_cpu import RUNTIME, DICTIONARY, CONFIG
    from scripts.recognition_metrics import select_checkpoint
    dest = round_dir(base, number)
    require_training_release(base, number, dest / 'optimizer_train.txt', dest / 'inner_validation.txt')
    selection = read(model_directory / 'selected_checkpoint.json')
    candidates = [read(p)['metrics'] for p in sorted(model_directory.glob('validation_epoch_*.json'))]
    expected = select_checkpoint(candidates, patience=5)
    if expected['checkpoint'] != selection['checkpoint']: raise ValueError('Checkpoint selection mismatch')
    checkpoint = Path(selection['checkpoint'] + '.pdparams')
    if not checkpoint.is_file(): raise ValueError('Selected checkpoint missing')
    export = model_directory / 'export'
    subprocess.run([sys.executable, str(RUNTIME / 'tools/export_model.py'), '-c', str(CONFIG), '-o',
                    f'Global.pretrained_model={selection["checkpoint"]}', 'Global.checkpoints=null',
                    f'Global.character_dict_path={DICTIONARY}', f'Global.save_inference_dir={export}',
                    'Global.use_gpu=False'], cwd=ROOT, check=True)
    for name in ('inference.json', 'inference.pdiparams', 'inference.yml'):
        if not (export / name).is_file(): raise ValueError('Incomplete export: ' + name)
    # Use only an already admitted original for the loading check.
    released = read(dest / 'training_release.json')
    original = next(iter(released['admitted'].values()))['original_path']
    bundle = model_directory / 'verified_bundle'
    shutil.copytree(ROOT / 'weights/paddle', bundle)
    rec = bundle / 'korean_PP-OCRv5_mobile_rec'
    for path in export.iterdir():
        if path.is_file(): shutil.copy2(path, rec / path.name)
    subprocess.run([str(inference_python), str(ROOT / 'notebooks/project/run.py'),
                    'scripts.check_sequential_export', '--weights', str(bundle), '--image', original,
                    '--report', str(model_directory / 'export_loading.json')], cwd=ROOT, check=True)
    # Keep a recoverable copy of the prior inference model before promotion.
    active = ROOT / 'weights/paddle/korean_PP-OCRv5_mobile_rec'
    shutil.copytree(active, model_directory / 'previous_inference_model')
    for path in rec.iterdir():
        if path.is_file(): shutil.copy2(path, active / path.name)
    completion = dict(round=number, checkpoint=evidence(checkpoint), selection=evidence(model_directory / 'selected_checkpoint.json'),
                      export_loading=evidence(model_directory / 'export_loading.json'), model=model_lock(ROOT / 'weights/paddle'),
                      independent_final_test=False if number == 8 else None)
    write(dest / 'training_complete.json', completion)
    state = read(dest / 'state.json')
    state.update(status='training_complete', completion=evidence(dest / 'training_complete.json'),
                 workflow_finished=number == 8)
    write(dest / 'state.json', state)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['infer', 'score', 'release'])
    parser.add_argument('--workspace', type=Path, default=BASE)
    parser.add_argument('--round', type=int, choices=range(1, 9), required=True)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--groups', type=Path)
    parser.add_argument('--labels', type=Path)
    args = parser.parse_args()
    if args.action == 'infer':
        if not args.approval: parser.error('--approval required')
        infer(args.workspace, args.round, args.approval)
    elif args.action == 'score':
        if not args.labels: parser.error('--labels required')
        score(args.workspace, args.round, args.labels)
    else:
        if not args.approval or not args.groups: parser.error('--approval and --groups required')
        release(args.workspace, args.round, args.approval, args.groups)

if __name__ == '__main__': main()
