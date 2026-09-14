"""Run an isolated paper candidate with the existing notebook/provenance checks.

Uses the candidate's 1600-second watchdog, never changes formal round state.
Labels stay outside the notebook sandbox and are loaded only by later scoring.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('C:/ITDA_OCR_CODE')
BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
DEV = BASE/'paper-ocr-20260914'
CODE = DEV/'code-monitor'
os.environ.update(ITDA_GROUPED_RELEASE='1', ITDA_ASSET_ROOT=str(ROOT))
sys.path.insert(0, str(CODE/'notebooks/project'))
from scripts.grouped_rounds import (run_notebook, source_lock, model_lock, evidence,
    exclusive, stop_process, child_environment, embedded_source_manifest)
from scripts.prepare_sequential_rounds import read, write, digest, csv_read, csv_write
from scripts.grouped_plan import cpu_set
from scripts.grouped_cpu import verify_topology

SAMPLES = {'AMLT000218','AMLT000226','BMLT003509','AMLT000402','AMLT000407',
           'AMLT000450','AMLT000643','AMLT000727'}


def worker(job_path, number):
    import psutil
    job = read(job_path)
    if job['parent_pid'] not in [p.pid for p in psutil.Process().parents()]:
        raise RuntimeError('Worker has no live owning coordinator')
    if source_lock(CODE) != job['code'] or model_lock(CODE/'weights/paddle') != job['model']:
        raise RuntimeError('Candidate changed since job creation')
    os.environ.update(ITDA_EXECUTION_POLICY='base-first-v2', ITDA_SHARE_RECOGNIZER='1',
                      ITDA_BUDGET_SECONDS=str(90 if job['smoke'] else 1570))
    item = job['manifests'][str(number)]
    if digest(item['path']) != item['sha256']:
        raise RuntimeError('Manifest changed')
    _, runtime = run_notebook(BASE, number, code_root=CODE, weights=CODE/'weights/paddle',
        output_dir=job_path.parent/f'round_{number:02}', manifest=Path(item['path']), network_mode='online')
    raise SystemExit(0 if runtime['status'] == 'completed' and not runtime['failures'] else 1)


def main():
    import psutil
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path)
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--job', type=Path)
    p.add_argument('--round', type=int, choices=[2,3])
    args = p.parse_args()
    if args.job:
        return worker(args.job, args.round)
    if args.output is None:
        p.error('--output required')
    with exclusive(BASE/'locks/execution.lock'):
        auth = read(DEV/'authorization.json')
        if not auth['instruction'] or auth['notebook_limit_seconds'] != 1600:
            raise ValueError('Missing current task authorization')
        for path, sha in auth['protected'].items():
            if digest(path) != sha:
                raise RuntimeError('Protected baseline changed: '+path)
        embedded_source_manifest(CODE)
        if psutil.virtual_memory().available < 4 * 1024**3:
            raise RuntimeError('Paired run requires at least 4 GiB available RAM')
        topology = verify_topology()
        args.output.mkdir(parents=True, exist_ok=False)
        manifests = {}
        for number in (2,3):
            manifest = BASE/f'test_round_{number:02}.csv'
            if args.smoke:
                rows = [r for r in csv_read(manifest) if r['image_id'] in SAMPLES]
                manifest = args.output/f'manifest_{number:02}.csv'
                csv_write(manifest, rows, ['image_id','image_path'])
            manifests[str(number)] = evidence(manifest)
        job = dict(parent_pid=os.getpid(), authorization=evidence(DEV/'authorization.json'),
            code=source_lock(CODE), model=model_lock(CODE/'weights/paddle'), manifests=manifests,
            smoke=args.smoke, topology=topology, controller=evidence(__file__),
            scope='exposed development only; no training or promotion', hard_limit_seconds=1600)
        write(args.output/'job.json', job)
        processes, logs, error = [], [], None
        minimum = psutil.virtual_memory().available
        started = time.perf_counter()
        try:
            for number in (2,3):
                log = (args.output/f'worker_{number:02}.log').open('x', encoding='utf-8')
                logs.append(log)
                processes.append(subprocess.Popen([sys.executable, __file__, '--job', str(args.output/'job.json'),
                    '--round', str(number)], cwd=ROOT, env=child_environment(cpu_set(number)),
                    stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW))
            while any(p.poll() is None for p in processes):
                minimum = min(minimum, psutil.virtual_memory().available)
                if minimum < 768 * 1024**2:
                    raise RuntimeError('Available RAM below 768 MiB')
                if time.perf_counter()-started > (240 if args.smoke else 1740):
                    raise RuntimeError('Coordinator watchdog: notebook has its own 1600s deadline')
                time.sleep(.2)
        except Exception as exc:
            error = repr(exc)
        finally:
            for process in processes:
                stop_process(process)
            for log in logs:
                log.close()
            changed = source_lock(CODE) != job['code'] or model_lock(CODE/'weights/paddle') != job['model']
            result = dict(status='passed' if not error and not changed and len(processes)==2
                and all(p.returncode==0 for p in processes) else 'failed', error=error,
                code_or_model_changed=changed, returncodes=[p.returncode for p in processes],
                minimum_available_bytes=minimum, job=evidence(args.output/'job.json'))
            write(args.output/'result.json', result)
        print(json.dumps(result), flush=True)
        raise SystemExit(0 if result['status']=='passed' else 1)


if __name__ == '__main__':
    main()
