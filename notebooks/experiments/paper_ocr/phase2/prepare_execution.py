"""Create immutable, non-executing stage-2/3 handoff artifacts. No approval generation."""
import argparse
import ast
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1')
SOURCE = BASE / 'paper-plan-implementation-20260914/code'
REVIEW = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/paper-ocr-20260914/training-review')
CONTROLLERS = ('grouped_plan.py', 'grouped_rounds.py', 'grouped_training.py', 'grouped_review.py',
               'run_round_groups.py', 'grouped_cpu.py', 'run_offline_verification.ps1',
               'prepare_grouped_stage2.py')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256') if hasattr(hashlib, 'file_digest') else None
        if value is None:
            value = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b''): value.update(block)
    return value.hexdigest()


def lock_tree(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream: return list(csv.DictReader(stream))


def prepare(destination):
    import yaml
    from materialize_training_config import materialize
    # Only metadata, source and already reviewed-development drafts are read.
    # No image decoder, model, notebook, optimizer, test runner or calibration fitting.
    source_before = lock_tree(SOURCE)
    locks = read(BASE / 'manifest_lock.json')
    for name, expected in locks.items():
        if sha(BASE / name) != expected: raise ValueError('Frozen manifest changed: ' + name)
    protected = {str(BASE / name): sha(BASE / name) for name in (
        'migration.json', 'group_roles.json', 'development_history.json',
        'rounds/round_02/state.json', 'rounds/round_03/state.json',
        'rounds/round_02/initial_report.json', 'rounds/round_03/initial_report.json')}
    release = read(BASE / 'groups/group_02_03/release/release.json')
    for name, expected in release['model'].items():
        if sha(SOURCE / 'weights/paddle' / name) != expected:
            raise ValueError('Candidate model differs from retained bundle: ' + name)
    notebook = read(SOURCE / 'predict.ipynb')
    embedded = notebook['metadata']['itda_embedded']['sources']
    for name, expected in embedded.items():
        if sha(SOURCE / 'notebooks/project/src' / (name + '.py')) != expected:
            raise ValueError('Notebook packaging is stale: ' + name)
    destination.mkdir(parents=True, exist_ok=False)
    groups, crops = read(REVIEW / 'groups.draft.json'), read(REVIEW / 'crops.draft.json')
    mapping = rows(BASE / 'test_to_original_mapping.csv')
    recipes = read(Path(__file__).with_name('training_recipes.json'))
    config_path = ROOT / 'notebooks/project/configs/training/korean_PP-OCRv5_mobile_rec_cpu.yml'
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    artifacts = {}
    for number in (2, 3):
        dest = destination / f'round_{number:02d}'
        code = dest / 'code'
        shutil.copytree(SOURCE, code, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in CONTROLLERS:
            shutil.copy2(ROOT / 'notebooks/project/scripts' / name, code / 'notebooks/project/scripts' / name)
        for name in ('test_grouped_original_policy.py', 'test_grouped_preparation_policy.py'):
            shutil.copy2(ROOT / 'notebooks/project/tests' / name, code / 'notebooks/project/tests' / name)
        current = {r['original_id'] for r in mapping if int(r['round']) == number}
        write(dest / 'review/groups.draft.json', {i: groups[i] for i in sorted(current)})
        write(dest / 'review/crops.draft.json', [{**c, 'review_status': 'pending'}
            for c in crops if c['image_id'] in current])
        for name, recipe in recipes['candidates'].items():
            path = dest / 'review/configs' / (name + '.draft.yml')
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as stream:
                yaml.safe_dump(materialize(config, recipe), stream, allow_unicode=True, sort_keys=False)
        # Parse syntax only. These are not executed tests or an inference validation.
        for name in CONTROLLERS:
            path = code / 'notebooks/project/scripts' / name
            if path.suffix == '.py': ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        artifacts[str(number)] = dict(code_root=str(code), files=lock_tree(code),
            model=release['model'], manifest=dict(path=str(BASE / f'test_round_{number:02d}.csv'),
            sha256=locks[f'test_round_{number:02d}.csv']), images=500,
            cpu_set=[0, 1, 4, 5] if number == 2 else [2, 3, 6, 7],
            initial_development_images=499 if number == 2 else 0,
            review_files=lock_tree(dest / 'review'), tests_executed=False, optimizer_started=False)
    write(destination / 'historical-crops.draft.json', [{**c, 'review_status': 'pending'} for c in crops
        if c['image_id'] not in {r['original_id'] for r in mapping if int(r['round']) in (2, 3)}])
    write(destination / 'stage3-deferred.json', dict(stage=3, rounds=[4, 5], images=[394, 500],
        cumulative_images=2110, time_targets_seconds=[1260.8, 1600.0],
        manifests={str(n): dict(path=str(BASE / f'test_round_{n:02d}.csv'),
            sha256=locks[f'test_round_{n:02d}.csv']) for n in (4, 5)},
        prerequisites=['valid stage-2 completion, selected code/model and integration evidence',
                       'both first tests, reports and user feedback before training',
                       'reviewed originals/crops, permanent groups and exact config approval'],
        code_root=None, weights=None, future_images_or_labels_read=False, admission_created=False))
    if source_before != lock_tree(SOURCE): raise ValueError('Original candidate changed during preparation')
    if any(sha(p) != expected for p, expected in protected.items()): raise ValueError('Historical evidence changed')
    result = dict(schema=1, policy='grouped-6-originals-v1', created_at=datetime.now(timezone.utc).isoformat(),
        status='prepared_not_tested_not_approved', workspace=str(BASE), source=str(SOURCE),
        tests_authorized=False, training_authorized=False, tests_executed=False, optimizer_started=False,
        shared_weights_changed=False, source_unchanged=True, historical_evidence_unchanged=True,
        source_files=source_before, protected=protected, manifest_lock=locks, rounds=artifacts,
        preparation_tool_sha256=sha(Path(__file__)), config_base=dict(path=str(config_path), sha256=sha(config_path)),
        runner_sha256=sha(Path(__file__).with_name('run_prepared.py')),
        recipes_sha256=sha(Path(__file__).with_name('training_recipes.json')),
        review_source=dict(path=str(REVIEW), files=lock_tree(REVIEW)),
        policy_values=dict(groups=[[1], [2, 3], [4, 5], [6]], seconds_per_image=3.2,
            hard_timeout_seconds=2400, accuracy_metric='date-fields-v1', accuracy_target=.95,
            threads_per_worker=4, standalone_integration_cpus=[0, 1, 2, 3],
            network_default='offline', online_exception='rounds 2/3 only, exact instruction and hashes required'),
        gates=['separately authorized new-code tests and embedded-source parity',
               'review product groups, crop transcriptions/fields and configs',
               'actual report-linked per-round training approval',
               'cumulative regression and separately approved integration/selection before stage 3'])
    write(destination / 'preparation.json', result)
    print(json.dumps(dict(destination=str(destination), status=result['status'],
                         tests_executed=False, optimizer_started=False), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output.resolve())
