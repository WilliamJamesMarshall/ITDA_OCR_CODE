"""Explicitly authorized 2/3 development retest; preserve all first-test evidence."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.grouped_plan import BASE, PREVIOUS_BASE, cpu_set, time_target_seconds
from scripts.grouped_rounds import evidence, checked_evidence, exclusive, now, child_environment, stop_process, validate_output
from scripts.prepare_sequential_rounds import ROOT, read, write, digest, csv_read
from scripts.profile_grouped_performance import preflight, controller_lock, MINIMUM_RUNNING_BYTES

DEVELOPMENT = BASE/'performance-development-20260913'


def check_fresh_resolution(record, proof, gate):
    """Historical missing OCR stays a replay failure; bind fresh exact-bundle evidence separately."""
    resolution = read(checked_evidence(record['submission_resolution']))
    if (checked_evidence(resolution['replay']) != checked_evidence(record['submission_gate'])
            or resolution['replay']['sha256'] != record['submission_gate']['sha256']):
        raise ValueError('Fresh evidence is for a different replay')
    result_path = checked_evidence(resolution['profile_result'])
    result = read(result_path)
    job = read(checked_evidence(result['job']))
    if (result.get('status')!='passed' or result.get('code_changed') or job.get('slots')!=[2,3]
            or job['preflight']['copies'] != proof['copies'] or job['model'] != record['model']
            or job.get('network_mode','offline') != record.get('network_mode','offline')):
        raise ValueError('Fresh recovery bundle/environment mismatch')
    changes = [c for r in gate['results'] for c in r.get('regressions',[])]
    if any(not isinstance(c,dict) or not c.get('image_id') for c in changes):
        raise ValueError('Malformed replay regression evidence')
    ids = {c['image_id'] for c in changes}
    if not ids or not ids <= set(job['samples']):
        raise ValueError('All historical replay regressions require fresh samples')
    manifest = checked_evidence(job['manifest'])
    mapping = {r['test_id']:r for r in csv_read(BASE/'test_to_original_mapping.csv')}
    for row in csv_read(manifest):
        if digest(row['image_path']) != mapping[row['image_id']]['test_sha256']:
            raise ValueError('Fresh recovery image changed')
    labels = {}
    for n in (2,3):
        labels.update({r['image_id']:r['정답 날짜'].strip().replace('NONE-NONE-NONE','NONE')
                       for r in csv_read(PREVIOUS_BASE/f'stage2_initial_20260913/approved_labels_round_{n:02d}.csv')})
    for n in (2,3):
        runtime = read(checked_evidence(resolution['slots'][str(n)]['runtime']))
        output = checked_evidence(resolution['slots'][str(n)]['submission'])
        if (output != result_path.parent/f'round_{n:02d}/submission.csv'
                or runtime['status']!='completed' or runtime['failures']
                or runtime['environment']['cpu_affinity']!=cpu_set(n)
                or runtime['environment'].get('network_mode','offline')!=record.get('network_mode','offline')):
            raise ValueError('Fresh recovery execution evidence invalid')
        validate_output(output,job['samples'])
        actual = {r['image_id']:r['final_date'] for r in csv_read(output)}
        if any(actual[i]!=labels[i] for i in ids):
            raise ValueError('Fresh exact-bundle recovery still regresses')
    return ids


def check_submission_gate(development, proof):
    record = read(Path(development)/'development.json')
    if not record.get('submission_validation_required'):
        return  # Historical attempts retain their original qualification contract.
    if not record.get('submission_gate'):
        raise ValueError('Actual submission-path regression evidence required')
    gate = read(checked_evidence(record['submission_gate']))
    if record.get('accuracy_policy') == 'date-fields-v1' and gate.get('accuracy_policy') != 'date-fields-v1':
        raise ValueError('Submission replay must declare the current field policy')
    expected = {(run, n) for run in ('retest-stage2-20260913', 'retest-stage2-corrected-20260914-v6') for n in (2,3)}
    results = gate.get('results', [])
    if (len(results) != 4 or {(r['run'],r['round']) for r in results} != expected
            or not gate.get('input_evidence')):
        raise ValueError('Complete successful submission replay required')
    for item in gate['input_evidence']:
        checked_evidence(item)
    for n in ('2','3'):
        if proof['copies'][n]['code'] != gate['code']:
            raise ValueError('Submission replay source differs from proposed notebook bundle')
    resolved = set()
    if not gate.get('gate_passed'):
        if not record.get('submission_resolution'):
            raise ValueError('Complete successful submission replay or bound fresh recovery required')
        resolved = check_fresh_resolution(record, proof, gate)
    if record.get('embedded_validation_required'):
        comparison = gate.get('embedded_equivalence', {})
        if (comparison.get('comparisons') != 2000 or comparison.get('mismatches') != []
                or comparison.get('project_imports_blocked') is not True
                or comparison.get('notebook', {}).get('sha256') != gate['code'].get('predict.ipynb')):
            raise ValueError('Exact generated-notebook equivalence evidence required')
        checked_evidence(comparison['notebook'])
    for result in results:
        predictions = result.get('predictions', [])
        if (result.get('images') != 500 or len(result.get('predictions',[])) != 500
                or len({r.get('image_id') for r in predictions}) != 500
                or any(not r.get('image_id') or not r.get('final_date') for r in predictions)
                or any(not isinstance(c,dict) or c.get('image_id') not in resolved for c in result.get('regressions',[]))
                or result.get('report_output_mismatches')):
            raise ValueError('Submission-path regression or incomplete replay blocks retest')


def prepare(dest, instruction, source_reference, development=DEVELOPMENT):
    development = Path(development).resolve()
    proof = preflight(development)
    dest.mkdir(parents=True,exist_ok=False)
    value = dict(actor='user',action='restart_tests',rounds=[2,3],instruction=instruction,
                 network_mode=read(development/'development.json').get('network_mode','offline'),
                 source_reference=source_reference,recorded_at=now(),copies=proof['copies'],
                 model=read(development/'development.json')['model'],mode='base-first',
                 budget_seconds=read(development/'development.json').get('budget_seconds',1470),
                 accuracy_policy=read(development/'development.json').get('accuracy_policy','historical-exact'),
                 evaluation_code=evidence(ROOT/'notebooks/project/scripts/evaluate_pipeline.py'),
                 notebook_target_seconds=time_target_seconds(500),
                 development=str(development),development_evidence=evidence(development/'development.json'),
                 sample_gate=evidence(ROOT/'notebooks/project/scripts/correction_sample_gate.py'),
                 cpu_policy=proof['cpu'],training_authorized=False,
                 manifests={str(n):evidence(BASE/f'test_round_{n:02d}.csv') for n in (2,3)},
                 original_reports={str(n):evidence(BASE/f'rounds/round_{n:02d}/initial_report.json') for n in (2,3)})
    write(dest/'authorization.json',value)
    write(dest/'preparation.json',proof)
    print(dest/'authorization.json')


def check(dest):
    value = read(dest/'authorization.json')
    if value.get('actor')!='user' or value.get('action')!='restart_tests' or value.get('rounds')!=[2,3]:
        raise ValueError('Actual paired restart authorization required')
    if not value.get('instruction') or not value.get('source_reference') or value.get('training_authorized') is not False:
        raise ValueError('Incomplete or wrong authorization scope')
    development = Path(value.get('development', DEVELOPMENT))
    if 'development_evidence' in value:
        if checked_evidence(value['development_evidence']) != development/'development.json':
            raise ValueError('Development identity changed')
    if 'sample_gate' in value:
        checked_evidence(value['sample_gate'])
    if 'evaluation_code' in value:
        checked_evidence(value['evaluation_code'])
    if value.get('accuracy_policy','historical-exact') != read(development/'development.json').get('accuracy_policy','historical-exact'):
        raise ValueError('Authorized accuracy policy changed')
    proof = preflight(development)
    if value['copies']!=proof['copies'] or value['model']!=read(development/'development.json')['model']:
        raise ValueError('Authorized source, model, or CPU assignment changed')
    if value.get('network_mode','offline') != read(development/'development.json').get('network_mode','offline'):
        raise ValueError('Authorized network mode changed')
    check_submission_gate(development, proof)
    dev_record = read(development/'development.json')
    if (value['mode']!='base-first' or value['budget_seconds']!=dev_record.get('budget_seconds',1470)
            or value.get('notebook_target_seconds') != time_target_seconds(500)
            or value['budget_seconds'] not in (1470,1570)):
        raise ValueError('Authorized runtime policy changed')
    for n in (2,3):
        manifest = checked_evidence(value['manifests'][str(n)])
        if manifest!=BASE/f'test_round_{n:02d}.csv' or len(csv_read(manifest))!=500:
            raise ValueError('Expected exact original 500-image manifest')
        checked_evidence(value['original_reports'][str(n)])
    if not proof['memory_ready']: raise RuntimeError('Need 4 GiB available RAM before paired retest')
    candidates = []
    for path in (development/'profiles').glob('base-first-*/result.json'):
        result = read(path)
        if result['status']!='passed' or result.get('slots')!=[2,3]: continue
        job = read(checked_evidence(result['job']))
        if job.get('network_mode','offline') != value.get('network_mode','offline'): continue
        if job['preflight']['copies']!=value['copies'] or job['model']!=value['model']: continue
        if job['controller']!=controller_lock(): continue
        for n in (2,3):
            folder=path.parent/f'round_{n:02d}'
            runtime=read(folder/'runtime.json')
            if runtime['status']!='completed' or runtime['failures'] or runtime['environment']['cpu_affinity']!=cpu_set(n):
                raise ValueError('Offline sample runtime invalid')
            if runtime['environment'].get('network_mode','offline') != value.get('network_mode','offline'):
                raise ValueError('Sample network mode differs from authorized mode')
            validate_output(folder/'submission.csv',job['samples'])
        if 'plan' in read(development/'development.json'):
            from scripts.correction_sample_gate import check_samples
            if not check_samples(path.parent, job['samples'])['passed']:
                continue
        candidates.append(path)
    if not candidates: raise ValueError('Both mixed slots need matching successful sample notebooks in the authorized network mode first')
    qualification=max(candidates,key=lambda p:p.stat().st_mtime)
    return value,proof,qualification


def run(dest):
    import psutil
    with exclusive(BASE/'locks/execution.lock'):
        value,proof,qualification=check(dest)
        attempt=dest/'execution'
        attempt.mkdir(exist_ok=False)
        # One immutable attempt for this authorization. A failed attempt is never overwritten.
        control=controller_lock()
        own_sha=digest(__file__)
        write(attempt/'binding.json',dict(authorization=evidence(dest/'authorization.json'),
             qualification=evidence(qualification),preflight=proof,controller=control,runner_sha256=own_sha))
        processes,logs=[],[]
        minimum=psutil.virtual_memory().available
        started=time.perf_counter()
        error=None
        try:
            for n in (2,3):
                job=dict(parent_pid=os.getpid(),slots=[2,3],smoke=False,mode=value['mode'],
                         network_mode=value.get('network_mode','offline'),
                         budget_seconds=value['budget_seconds'],preflight=proof,model=value['model'],
                         controller=control,manifest=value['manifests'][str(n)],
                         authorization=evidence(dest/'authorization.json'),created_at=now())
                job_path=attempt/f'job_{n:02d}.json'
                write(job_path,job)
                log=(attempt/f'worker_{n:02d}.log').open('w',encoding='utf-8')
                logs.append(log)
                command=[sys.executable,str(ROOT/'notebooks/project/run.py'),'scripts.profile_grouped_performance',
                         '_worker','--job',str(job_path),'--round',str(n)]
                processes.append(subprocess.Popen(command,cwd=ROOT,env=child_environment(cpu_set(n)),
                    stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
            while any(p.poll() is None for p in processes):
                minimum=min(minimum,psutil.virtual_memory().available)
                if minimum<MINIMUM_RUNNING_BYTES:
                    error='Available RAM below 768 MiB; owned test workers stopped'
                    break
                if time.perf_counter()-started>2520:
                    error='Coordinator watchdog; notebook watchdog remains 2400 seconds each'
                    break
                time.sleep(.2)
        finally:
            for p in processes: stop_process(p)
            for log in logs: log.close()
            code_changed=control!=controller_lock() or own_sha!=digest(__file__)
            result=dict(status='passed' if not error and not code_changed and len(processes)==2 and all(p.returncode==0 for p in processes) else 'failed',
                        created_at=now(),error=error,code_changed=code_changed,returncodes=[p.returncode for p in processes],
                        minimum_available_bytes=minimum,total_coordinator_seconds=time.perf_counter()-started,
                        kind='development retest; original first scores retained',training_executed=False)
            write(attempt/'result.json',result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result['status']!='passed': raise RuntimeError('Retest failed; partial records retained at '+str(attempt))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','check','run'])
    parser.add_argument('--restart-directory',type=Path,required=True)
    parser.add_argument('--instruction')
    parser.add_argument('--source-reference')
    parser.add_argument('--development-root',type=Path,default=DEVELOPMENT)
    args=parser.parse_args()
    if args.action=='prepare':
        if not args.instruction or not args.source_reference: parser.error('Actual instruction and source required')
        prepare(args.restart_directory,args.instruction,args.source_reference,args.development_root)
    elif args.action=='check':
        _,proof,q=check(args.restart_directory)
        print(json.dumps(dict(available_memory_bytes=proof['available_memory_bytes'],qualification=str(q))))
    else: run(args.restart_directory)


if __name__=='__main__': main()
