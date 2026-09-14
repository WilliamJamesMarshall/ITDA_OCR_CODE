"""Explicitly authorized stage-2 development test only; never train, score or promote.

Not used by preparation. Each invocation needs real per-round approval files.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from prepare_execution import ROOT, BASE, CONTROLLERS, read, sha, lock_tree, write


def require_approval(path, preparation_path, preparation, number, mode):
    value = read(path)
    expected = dict(actor='user', action='start_development_test', round=number,
                    preparation_sha256=sha(preparation_path), runner_sha256=sha(Path(__file__)),
                    network_mode=mode, manifest_sha256=preparation['rounds'][str(number)]['manifest']['sha256'])
    if any(value.get(k) != v for k, v in expected.items()):
        raise ValueError('Approval does not bind this prepared candidate, runner, round and network scope')
    if not all(isinstance(value.get(k), str) and value[k].strip()
               for k in ('instruction', 'source_reference', 'approved_at')):
        raise ValueError('Actual instruction, source and timestamp required; no generated approval')
    approved = datetime.fromisoformat(value['approved_at'])
    if approved.tzinfo is None or approved < datetime.fromisoformat(preparation['created_at']):
        raise ValueError('Approval must follow the prepared candidate and include timezone')


def check_prepared(preparation, number):
    if preparation['policy'] != 'grouped-6-originals-v1' or number not in (2, 3):
        raise ValueError('Only the prepared stage-2 development scope is supported')
    item = preparation['rounds'][str(number)]
    code = Path(item['code_root'])
    if lock_tree(code) != item['files'] or sha(item['manifest']['path']) != item['manifest']['sha256']:
        raise ValueError('Prepared code/model/manifest changed; preserve old package and prepare a new version')
    return code


def worker(job_path, number):
    import psutil
    job = read(job_path)
    if number not in job['rounds'] or job['runner_sha256'] != sha(Path(__file__)):
        raise ValueError('Unexpected worker round or runner changed')
    parent = next((p for p in psutil.Process().parents() if p.pid == job['parent_pid']), None)
    if parent is None or abs(parent.create_time() - job['parent_create_time']) > .01:
        raise ValueError('Worker requires its live owning coordinator')
    path = Path(job['preparation']['path'])
    if sha(path) != job['preparation']['sha256']: raise ValueError('Preparation changed')
    preparation = read(path)
    code = check_prepared(preparation, number)
    item = job['approvals'][str(number)]
    if sha(item['path']) != item['sha256']: raise ValueError('Approval changed')
    require_approval(item['path'], path, preparation, number, job['network_mode'])
    os.environ.update(ITDA_GROUPED_RELEASE='1', ITDA_ASSET_ROOT=str(ROOT),
                      ITDA_EXPLICIT_TEST_INSTRUCTION='1', ITDA_EXECUTION_POLICY='base-first-v2',
                      ITDA_SHARE_RECOGNIZER='1')
    sys.path.insert(0, str(code / 'notebooks/project'))
    from scripts.operating_environment import limit_cpu
    from scripts.grouped_rounds import run_notebook
    limit_cpu(preparation['rounds'][str(number)]['cpu_set'])
    _, runtime = run_notebook(BASE, number, code_root=code, weights=code / 'weights/paddle',
        output_dir=job_path.parent / f'round_{number:02d}',
        manifest=Path(preparation['rounds'][str(number)]['manifest']['path']), network_mode=job['network_mode'])
    raise SystemExit(0 if runtime['status'] == 'completed' and not runtime['failures'] else 1)


def main(args):
    import psutil
    if not args.execute or not args.preparation or not args.approvals or not args.output:
        raise ValueError('--execute, --preparation, --approvals and a fresh --output are required')
    if args.output.exists(): raise ValueError('Output exists; never overwrite or repeat a completed result')
    preparation_path = args.preparation.resolve()
    preparation = read(preparation_path)
    if preparation.get('runner_sha256') != sha(Path(__file__)):
        raise ValueError('Runner changed since preparation; prepare a new version')
    numbers = list(dict.fromkeys(args.rounds))
    for n in numbers:
        code = check_prepared(preparation, n)
        require_approval(args.approvals / f'round_{n:02d}.json', preparation_path, preparation, n, args.network_mode)
        for name in CONTROLLERS:
            if sha(ROOT / 'notebooks/project/scripts' / name) != sha(code / 'notebooks/project/scripts' / name):
                raise ValueError('Current controller differs from prepared snapshot: ' + name)
    sys.path.insert(0, str(ROOT / 'notebooks/project'))
    from scripts.grouped_rounds import exclusive, child_environment, stop_process
    from scripts.grouped_plan import cpu_set, verify
    from scripts.grouped_cpu import verify_topology
    # Own the shared lock before starting any work; legacy nested locks are checked too.
    with exclusive(BASE / 'locks/execution.lock'):
        if (BASE / 'locks/metadata.lock').exists(): raise ValueError('Metadata update is in progress')
        verify(BASE, check_assets=True)
        topology = verify_topology()
        if psutil.virtual_memory().available < (4 if len(numbers) == 2 else 2) * 1024**3:
            raise ValueError('Insufficient available RAM for the selected workers')
        args.output.mkdir(parents=True, exist_ok=False)
        job = dict(parent_pid=os.getpid(), parent_create_time=psutil.Process().create_time(), rounds=numbers,
            preparation=dict(path=str(preparation_path), sha256=sha(preparation_path)),
            approvals={str(n): dict(path=str((args.approvals / f'round_{n:02d}.json').resolve()),
                sha256=sha(args.approvals / f'round_{n:02d}.json')) for n in numbers},
            runner_sha256=sha(Path(__file__)), network_mode=args.network_mode, topology=topology,
            hard_limit_seconds=2400, target_seconds_per_round=1600,
            scope='development retest only; no scoring/training/promotion/formal-state change')
        job_path = args.output / 'job.json'
        write(job_path, job)
        processes, logs, error = [], [], None
        started = time.perf_counter()
        minimum = psutil.virtual_memory().available
        try:
            for number in numbers:
                log = (args.output / f'worker_{number:02d}.log').open('x', encoding='utf-8')
                logs.append(log)
                processes.append(subprocess.Popen([sys.executable, __file__, '--job', str(job_path),
                    '--worker-round', str(number)], cwd=ROOT, env=child_environment(cpu_set(number)),
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            while any(p.poll() is None for p in processes):
                minimum = min(minimum, psutil.virtual_memory().available)
                if minimum < 768 * 1024**2: raise RuntimeError('Available memory below safety floor')
                if time.perf_counter() - started > 3000:
                    raise RuntimeError('Coordinator safety timeout, distinct from each notebook watchdog')
                time.sleep(.2)
        except Exception as exc:
            error = repr(exc)
        finally:
            for process in processes: stop_process(process)
            for log in logs: log.close()
            try:
                for number in numbers: check_prepared(preparation, number)
            except Exception as exc:
                error = repr(exc)
            completed = not error and len(processes) == len(numbers) and all(p.returncode == 0 for p in processes)
            write(args.output / 'result.json', dict(error=error, returncodes=[p.returncode for p in processes],
                minimum_available_bytes=minimum, performance_passed=None, scoring_required=True,
                execution_completed=completed,
                note='Completion is not accuracy/time acceptance; preserve per-round runtime and score all 500 images.'))
        raise SystemExit(0 if completed else 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--preparation', type=Path)
    parser.add_argument('--approvals', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--rounds', nargs='+', type=int, choices=(2, 3), default=[2, 3])
    parser.add_argument('--network-mode', choices=('offline', 'online'), default='offline')
    parser.add_argument('--job', type=Path)
    parser.add_argument('--worker-round', type=int, choices=(2, 3))
    arguments = parser.parse_args()
    if arguments.job: worker(arguments.job, arguments.worker_round)
    else: main(arguments)
