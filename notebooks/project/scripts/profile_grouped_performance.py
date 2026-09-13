"""Bounded development profiling on exposed samples, never a formal round or training."""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from scripts.grouped_plan import BASE, cpu_set
from scripts.grouped_cpu import verify_topology
from scripts.grouped_rounds import (source_lock, model_lock, run_notebook, exclusive, child_environment, embedded_source_manifest,
                                  stop_process, evidence, now)
from scripts.prepare_sequential_rounds import ROOT, read, write, digest, csv_read, csv_write
from scripts.operating_environment import limit_cpu

SAMPLES = ('AMLT000218','AMLT000226','AMLT000263','BMLT003522','AMLT000353',
           'AMLT000355','AMLT000368','AMLT000375','AMLT000378','AMLT000515','AMLT000643')
MINIMUM_START_BYTES = 4 * 1024**3
MINIMUM_RUNNING_BYTES = 768 * 1024**2


def preflight(development, slot=None):
    import psutil
    development = Path(development).resolve()
    record = read(development/'development.json')
    if record['training_authorized'] is not False or not record['instruction']:
        raise ValueError('Development instruction binding required')
    for path, sha in record['protected_before'].items():
        if digest(path) != sha: raise ValueError('Protected initial evidence changed: '+path)
    copies = {}
    for n in (2,3):
        code = development/f'round_{n:02d}/code'
        if str(code) != str(Path(record['copies'][str(n)]['code_root']).resolve()):
            raise ValueError('Development copy identity mismatch')
        if model_lock(code/'weights/paddle') != record['model']:
            raise ValueError('Development model changed')
        embedded_source_manifest(code)
        if digest(code/'predict.ipynb') != record['baseline_code']['predict.ipynb']:
            if 'plan' not in record or 'previous' not in record:
                raise ValueError('Protected notebook changed')
            previous = read(record['previous']['path'])
            old_notebook = Path(previous['copies'][str(n)]['code_root'])/'predict.ipynb'
            if (digest(old_notebook) != record['baseline_code']['predict.ipynb'] or
                    read(old_notebook)['cells'][0] != read(code/'predict.ipynb')['cells'][0]):
                raise ValueError('Protected notebook CONFIG changed')
        copies[str(n)] = dict(code_root=str(code), code=source_lock(code), cpus=cpu_set(n))
    if copies['2']['code'] != copies['3']['code']:
        raise ValueError('Profile comparison requires identical inference copies')
    available = psutil.virtual_memory().available
    minimum_start = MINIMUM_START_BYTES if slot is None else int(2.5 * 1024**3)
    return dict(cpu=verify_topology(), available_memory_bytes=available,
                minimum_start_bytes=minimum_start, memory_ready=available >= minimum_start,
                copies=copies, development=evidence(development/'development.json'))


def run(development, mode, smoke=False, slot=None, network_mode='offline'):
    import psutil
    development = Path(development).resolve()
    if network_mode=='online' and read(development/'development.json').get('network_mode')!='online':
        raise ValueError('Online execution requires an explicit development instruction binding')
    with exclusive(BASE/'locks/execution.lock'):
        proof = preflight(development, slot)
        dest = development/'profiles'/(("cpu-smoke-" if smoke else mode+'-')+uuid.uuid4().hex)
        dest.mkdir(parents=True, exist_ok=False)
        write(dest/'preflight.json',proof)
        if not smoke and not proof['memory_ready']:
            write(dest/'result.json',dict(status='blocked_before_inference',reason='Insufficient available RAM',
                  available_memory_bytes=proof['available_memory_bytes'],minimum_start_bytes=proof['minimum_start_bytes']))
            raise RuntimeError('Insufficient available RAM for this profile concurrency: '+str(dest))
        rows = []
        if not smoke:
            # Every selected sample must have completed the previous initial OCR.
            completed = set()
            for n in (2,3):
                with (BASE/f'rounds/round_{n:02d}/submission.csv.trace.jsonl').open(encoding='utf-8') as stream:
                    for line in stream:
                        if not line.endswith('\n'): break
                        event = json.loads(line)
                        if event['kind']=='image_end': completed.add(event['image_id'])
            if not set(SAMPLES) <= completed: raise ValueError('Profile samples must already be exposed')
            mapping = {r['test_id']:r for r in csv_read(BASE/'test_to_original_mapping.csv')}
            for image_id in SAMPLES:
                image = ROOT/'테스트용데이터'/(image_id+'.jpg')
                if digest(image) != mapping[image_id]['test_sha256']: raise ValueError('Sample changed')
                rows.append(dict(image_id=image_id,image_path=str(image)))
            csv_write(dest/'manifest.csv',rows,['image_id','image_path'])
        numbers = (slot,) if slot else (2,3)
        job = dict(created_at=now(), parent_pid=os.getpid(), mode=mode, smoke=smoke, preflight=proof, slots=numbers, network_mode=network_mode,
                   samples=SAMPLES if not smoke else [], model=read(development/'development.json')['model'],
                   controller=controller_lock(), training_authorized=False,
                   manifest=evidence(dest/'manifest.csv') if rows else None)
        write(dest/'job.json',job)
        processes, logs, minimum = [], [], psutil.virtual_memory().available
        started = time.perf_counter()
        error = None
        try:
            for n in numbers:
                log = (dest/f'worker_{n:02d}.log').open('w',encoding='utf-8')
                logs.append(log)
                command = [sys.executable,str(ROOT/'notebooks/project/run.py'),
                           'scripts.profile_grouped_performance','_worker','--job',str(dest/'job.json'),'--round',str(n)]
                processes.append(subprocess.Popen(command,env=child_environment(cpu_set(n)),cwd=ROOT,
                    stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
            while any(p.poll() is None for p in processes):
                minimum = min(minimum,psutil.virtual_memory().available)
                if time.perf_counter()-started > (60 if smoke else 600):
                    error = 'Development profile watchdog exceeded'
                    break
                if not smoke and minimum < MINIMUM_RUNNING_BYTES:
                    error = 'Available RAM dropped below 768 MiB; owned workers stopped'
                    break
                time.sleep(.2)
        finally:
            for p in processes: stop_process(p)
            for log in logs: log.close()
            changed = controller_lock() != job['controller']
            for item in proof['copies'].values():
                changed |= source_lock(item['code_root']) != item['code']
            result = dict(status='passed' if not error and not changed and len(processes)==len(numbers) and all(p.returncode==0 for p in processes) else 'failed',
                          error=error, code_changed=changed, returncodes=[p.returncode for p in processes],
                          minimum_available_bytes=minimum, elapsed_seconds=time.perf_counter()-started,
                          concurrent_workers=len(numbers), slots=numbers,
                          kind='CPU affinity smoke only' if smoke else f'{len(SAMPLES)} exposed samples per slot; not 500-image qualification',
                          job=evidence(dest/'job.json'))
            write(dest/'result.json',result)
        print(json.dumps(dict(path=str(dest),**result),ensure_ascii=False,indent=2))
        if result['status']!='passed': raise RuntimeError('Profile failure preserved: '+str(dest))


def controller_lock():
    from scripts.run_round_groups import controller_lock as grouped_lock
    return {**grouped_lock(), 'notebooks/project/scripts/profile_grouped_performance.py':digest(__file__)}


def worker(job_path, number):
    import psutil
    job_path = Path(job_path).resolve()
    job = read(job_path)
    if number not in job['slots']: raise ValueError('Unexpected profile slot')
    if job['controller'] != controller_lock(): raise ValueError('Profile controller changed')
    if job['parent_pid'] not in [p.pid for p in psutil.Process().parents()]:
        raise ValueError('Profile worker must belong to live coordinator')
    item = job['preflight']['copies'][str(number)]
    cpus = limit_cpu(item['cpus'])
    if job['smoke']:
        command = [sys.executable,'-c','import json,psutil; print(json.dumps(psutil.Process().cpu_affinity()))']
        child = json.loads(subprocess.check_output(command,text=True))
        if sorted(child) != cpus: raise ValueError('Child affinity mismatch')
        write(job_path.parent/f'cpu_{number:02d}.json',dict(parent=cpus,child=child,topology=verify_topology()))
        return
    code = Path(item['code_root'])
    if source_lock(code) != item['code'] or model_lock(code/'weights/paddle') != job['model']:
        raise ValueError('Profile source or model changed')
    out = job_path.parent/f'round_{number:02d}'
    os.environ['ITDA_PROFILE_PATH'] = str(out/'predictor_profile.jsonl')
    os.environ['ITDA_EXECUTION_POLICY'] = 'base-first-v1' if job['mode']=='base-first' else 'legacy'
    os.environ['ITDA_SHARE_RECOGNIZER'] = '0' if job['mode']=='legacy' else '1'
    os.environ['ITDA_BUDGET_SECONDS'] = str(job.get('budget_seconds', 1470))
    manifest = job['manifest']
    if digest(manifest['path']) != manifest['sha256']: raise ValueError('Profile manifest changed')
    _, runtime = run_notebook(BASE,number,code_root=code,weights=code/'weights/paddle',
                              output_dir=out,manifest=Path(manifest['path']), network_mode=job.get('network_mode','offline'))
    if runtime['status']!='completed' or runtime['failures']:
        raise RuntimeError('Development notebook failed; runtime retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','smoke','run','_worker'])
    parser.add_argument('--development-root',type=Path)
    parser.add_argument('--network-mode',choices=['offline','online'],default='offline')
    parser.add_argument('--mode',choices=['legacy','shared','base-first'],default='legacy')
    parser.add_argument('--job',type=Path)
    parser.add_argument('--round',type=int,choices=[2,3])
    parser.add_argument('--slot',type=int,choices=[2,3],help='Diagnostic single-slot run, not paired performance evidence')
    args = parser.parse_args()
    if args.action=='_worker':
        if not args.job or not args.round: parser.error('--job and --round required')
        worker(args.job,args.round)
    else:
        if not args.development_root: parser.error('--development-root required')
        if args.action=='check':
            result = preflight(args.development_root,args.slot)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            if not result['memory_ready']: raise RuntimeError('Insufficient available RAM for requested concurrency')
        else: run(args.development_root,args.mode,smoke=args.action=='smoke',slot=args.slot,network_mode=args.network_mode)


if __name__=='__main__': main()
