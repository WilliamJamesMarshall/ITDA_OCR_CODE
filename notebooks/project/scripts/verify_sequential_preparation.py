"""Build a data-free submission copy and verify preparation; never run a test round."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from scripts.prepare_sequential_rounds import BASE, ROOT, read, write, verify, digest, csv_read
from scripts.sequential_rounds import code_lock, model_lock, check_manifests

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=BASE)
    parser.add_argument('--skip-preservation', action='store_true')
    args = parser.parse_args()
    base = args.workspace
    check_manifests(base)
    if not args.skip_preservation: verify(base)
    indexed = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    roots = {p.split('/')[0] for p in indexed if p}
    allowed = {'predict.ipynb', 'requirements.txt', 'README.md', '.gitignore', 'download_weights.sh', 'notebooks', 'weights'}
    if roots != allowed: raise ValueError('Unexpected index roots')
    old = read(base / 'previous_policy/0/predict.ipynb')
    if read(ROOT / 'predict.ipynb')['cells'][0] != old['cells'][0]: raise ValueError('CONFIG changed')
    from scripts import ocr_annotations as ann
    records = [ann.read(p) for p in (ann.OUT / 'records').glob('*.json')]
    if len(records) != 2610 or any(ann.validate(r, True) or r['review']['status'] != 'approved' for r in records):
        raise ValueError('Approved annotation regression')
    clean = base / 'clean-submission'
    clean.mkdir(exist_ok=True)
    files = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode().split('\0')
    for name in files:
        if not name: continue
        source = ROOT / name
        if not source.resolve().is_relative_to(ROOT.resolve()): raise ValueError('Unexpected source')
        target = clean / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    with (base / 'clean-regression.log').open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, str(clean / 'notebooks/project/run.py'), 'unittest', 'discover',
                                 '-s', str(clean / 'notebooks/project/tests'), '-q'], cwd=clean, stdout=log, stderr=log)
    if result.returncode: raise ValueError('Clean submission regression failed; see log')
    record = next(r for r in records if r['image_id'] == 'BMLC002247')
    if not record['seen_in_development']: raise ValueError('Smoke sample not previously exposed')
    inputs = base / 'smoke-input'
    inputs.mkdir(exist_ok=True)
    image = ann.source_path(record)
    shutil.copy2(image, inputs / image.name)
    bundle = base / 'initial-export-bundle'
    if not bundle.exists(): shutil.copytree(ROOT / 'weights/paddle', bundle)
    for name in ('inference.json', 'inference.pdiparams', 'inference.yml'):
        shutil.copy2(base / 'initial-export-check' / name, bundle / 'korean_PP-OCRv5_mobile_rec' / name)
    with (base / 'initial-export-loading.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, str(clean / 'notebooks/project/run.py'), 'scripts.check_sequential_export',
                        '--weights', str(bundle), '--image', str(image), '--report', str(base / 'initial-export-loading.json')],
                        cwd=clean, stdout=log, stderr=log, check=True)
    shutil.copytree(ROOT / 'weights/paddle', clean / 'weights/paddle', dirs_exist_ok=True)
    kernel_root = base / 'smoke-jupyter'
    write(kernel_root / 'kernels/python3/kernel.json',
          {'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
           'display_name': 'ITDA smoke Python', 'language': 'python'})
    env = {**os.environ, 'JUPYTER_PATH': str(kernel_root), 'ITDA_INPUT_DIR': str(inputs),
           'ITDA_OUTPUT_PATH': str(base / 'smoke-submission.csv')}
    with (base / 'notebook-smoke.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, '-m', 'nbconvert', '--execute', '--to', 'notebook',
                        '--ExecutePreprocessor.timeout=300', '--output', 'smoke-executed.ipynb', 'predict.ipynb'],
                        cwd=clean, env=env, stdout=log, stderr=log, check=True, timeout=360)
    previous = ROOT.parent / 'ITDA_OCR_WORKSPACE/strict-layout-20260912/verified-submission.csv'
    if csv_read(base / 'smoke-submission.csv') != csv_read(previous): raise ValueError('Exposed sample output changed')
    # Freeze the actual current model, not the exported initial training checkpoint.
    write(base / 'round1_model_code_lock.json', {'code': code_lock(), 'model': model_lock(ROOT / 'weights/paddle'),
          'manifest_sha256': digest(base / 'test_round_01.csv')})
    write(base / 'preparation_verification.json', dict(submission_roots=sorted(roots), config_preserved=True,
          approved_annotations=len(records), clean_regression=True, initial_checkpoint_export_loading=True,
          current_model_notebook_run_all=True, exposed_sample_csv_unchanged=True,
          actual_training_performed=False, formal_rounds_executed=0))
    print('Preparation verification passed; formal environment remains unverified')

if __name__ == '__main__': main()
