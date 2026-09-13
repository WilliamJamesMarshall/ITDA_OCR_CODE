"""Entry point for the five-stage, eight-round workflow. Status is read-only."""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, read, write, digest
from scripts.grouped_plan import BASE, GROUPS, members, group_name, cpu_set, prepare, verify, revise_mapping
from scripts.grouped_rounds import (group_dir, round_dir, exclusive, execution_release, prior_completion,
    freeze, qualification, check_qualification, infer, score, approval, evidence, checked_evidence,
    model_lock, source_lock, child_environment, stop_process, now, require_pair_scored)


def status(base=BASE):
    """Never derive completion from stale booleans or from the presence of a checkpoint."""
    base = Path(base)
    if not (base / 'plan.json').exists():
        return dict(total_stages=5, current_stage=1, current_rounds=[1], prepared=False,
                    next_action='Prepare the approved grouped plan; preserve prior history')
    summary = verify(base)
    stages, first_pending, preceding_complete = [], None, True
    active_jobs = []
    for path in sorted((base / 'jobs').glob('*/job.json')):
        if (path.parent / 'result.json').exists(): continue
        job = read(path)
        try:
            import psutil
        except ImportError:
            active_jobs.append(dict(path=str(path),rounds=job['rounds'],action='unknown; install controller dependencies',pid=job['parent_pid']))
            continue
        try:
            process = psutil.Process(job['parent_pid'])
            if 'scripts.run_round_groups' in process.cmdline():
                active_jobs.append(dict(path=str(path), rounds=job['rounds'], action=job['action'], pid=process.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    for index, group in enumerate(GROUPS, 1):
        dest = group_dir(base, group[0])
        completion = dest / 'completion.json'
        valid, errors = False, []
        if completion.exists():
            try:
                value = read(completion)
                if value['status'] != 'complete' or value['rounds'] != list(group) or not preceding_complete:
                    raise ValueError('Invalid completion order')
                for name in ('approval', 'training_release', 'evaluation'): checked_evidence(value[name])
                if model_lock(Path(value['weights'])) != value['model'] or source_lock(value['code_root']) != value['code']:
                    raise ValueError('Completed model/code changed')
                if value.get('completion_kind') == 'legacy_user_closure':
                    from scripts.prepare_grouped_stage2 import validate_legacy_completion
                    validate_legacy_completion(base, value)
                valid = True
            except (ValueError, KeyError, OSError) as error: errors.append(str(error))
        rows = []
        for n in group:
            path = round_dir(base, n) / 'state.json'
            state = read(path) if path.exists() else dict(status='interrupted_preparation' if path.parent.exists() else 'not_started')
            row = dict(round=n, status=state['status'], cpus=cpu_set(n), report=str(round_dir(base, n) / 'report.md'),
                       imported_history=state.get('imported_history', False))
            if state.get('completion_kind'): row['completion_kind'] = state['completion_kind']
            for field in ('report', 'release', 'candidate', 'completion'):
                if field in state:
                    try: checked_evidence(state[field])
                    except (ValueError, OSError) as error: errors.append(str(error))
            rows.append(row)
        if valid and any(r['status'] != 'complete' for r in rows):
            valid = False
            errors.append('Group completion and per-round completion disagree')
        stage = dict(stage=index, rounds=list(group), completed=valid, preceding_complete=preceding_complete,
                     errors=errors, round_statuses=rows,
                     integration_required=len(group)==2,
                     integration_release=(dest / 'integration/training_release.json').exists(),
                     integration_candidate=(dest / 'integration/candidate_complete.json').exists())
        if not valid and first_pending is None: first_pending = stage
        preceding_complete &= valid
        stages.append(stage)
    legacy = read(base / 'legacy_history.json')
    legacy_base = Path(read(base / 'plan.json')['legacy_workspace'])
    training_record = legacy_base / 'remediation_13/final_summary.json'
    result = dict(policy=summary['policy'], total_stages=5, prepared=True,
        current_stage=first_pending['stage'] if first_pending else None,
        current_rounds=first_pending['rounds'] if first_pending else [], completed_stages=sum(s['completed'] for s in stages),
        stages=stages, workflow_complete=first_pending is None, inventory=summary,
        prior_round1_test=legacy['round1'], legacy_training_summary=str(training_record) if training_record.exists() else None,
        active_jobs=active_jobs,
        note='Legacy training attempts are not group completion; inspect linked results and approvals. No new execution is authorized by status.')
    unresolved = sum(r['unresolved_originals'] for r in summary['rounds'])
    missing_sources = sum(r.get('identified_source_missing_file',0) for r in summary['rounds'])
    product_references = sum(r.get('existing_product_references',0) for r in summary['rounds'])
    result['mapping_readiness'] = dict(unresolved_original_files=unresolved,
        existing_product_references=product_references,unlinked_missing_file_references=unresolved-product_references,
        identified_source_missing_file=missing_sources,unknown_source=unresolved-missing_sources,
        reports=[str(p) for p in sorted(base.glob('derivative-resolution-*/summary.json'))],
        note='Existing product references are augmented copies, not training originals. Reference linkage does not authorize training or restoration of deleted originals.')
    history_path = base / 'development_history.json'
    if history_path.exists():
        history = read(history_path)
        for name in ('source','predictions','training_attempts'): checked_evidence(history[name])
        result['historical_protected_correct'] = len(history['protected_expected'])
        result['historical_training_attempts'] = history['training_attempts']
        result['case_106_extra_work_held'] = history['case_106_extra_work_held']
    if first_pending:
        states = [r['status'] for r in first_pending['round_statuses']]
        result['next_action'] = ('Resolve evidence errors' if first_pending['errors'] else
            'Confirm explicit model, freeze release, qualify both CPU slots, then obtain/start approved tests' if 'not_started' in states else
            'Finish scoring each completed test' if 'inference_complete' in states else
            'Review each report and feedback; resolve originals/groups; obtain round-specific training approval' if 'awaiting_user_review' in states else
            'Execute only the approved pending training release' if 'originals_admitted' in states else
            'Review and approve integration, train, evaluate cumulative rounds, and explicitly select/retain the model')
    else: result['next_action'] = 'All five stages complete; no ninth test. Report final model without an independent post-training score.'
    if active_jobs: result['next_action'] = 'An existing coordinator is running; inspect its jobs/logs and do not launch duplicate work'
    return result


def precheck(base, number, action, approvals, integration=False):
    from scripts.grouped_training import validate_training
    verify(base)
    execution_release(base, number)
    prior_completion(base, number)
    if action == 'test':
        check_qualification(base, number)
        release = execution_release(base, number)
        if round_dir(base, number).exists(): raise ValueError('Round already has results; do not overwrite')
        approval(Path(approvals) / f'round_{number:02d}.json', 'start_test', number,
                 dict(manifest_sha256=digest(Path(base) / f'test_round_{number:02d}.csv'), code=release['code'], model=release['model']))
    elif action in ('train', 'evaluate'):
        require_pair_scored(base, number)
        target = group_dir(base, number) / 'integration' if integration else round_dir(base, number)
        value = validate_training(target / 'training_release.json')
        if action == 'train' and Path(value['output_dir']).exists():
            raise ValueError('Training output already exists; preserve it and review the interrupted attempt')
        if action == 'evaluate':
            value = read(target / 'candidate_complete.json')
            if model_lock(Path(value['weights'])) != value['model']: raise ValueError('Candidate model changed')


def already_finished(base, number, action, integration=False, retain=False):
    """Skip evidenced work, never interpret an interrupted output directory as success."""
    target = group_dir(base, number) / 'integration' if integration else round_dir(base, number)
    if action == 'test':
        path = target / 'state.json'
        if not path.exists(): return False
        value = read(path)
        if value['status'] not in ('inference_complete', 'awaiting_user_review', 'originals_admitted', 'candidate_complete', 'complete'):
            return False
        checked_evidence(value['manifest'])
        checked_evidence(value['runtime'])
        if value.get('predictions'): checked_evidence(value['predictions'])
        if value.get('report'): checked_evidence(value['report'])
        return True
    if action == 'qualify':
        path = group_dir(base, number) / f'qualification_{number:02d}/qualification.json'
        if not path.exists(): return False
        check_qualification(base, number)
        return True
    if action == 'train':
        path = target / 'candidate_complete.json'
        if not path.exists(): return False
        from scripts.grouped_training import validate_training
        value = read(path)
        validate_training(checked_evidence(value['training_release']))
        for name in ('selection', 'checkpoint', 'export_loading'): checked_evidence(value[name])
        if value['status'] != 'candidate_complete' or model_lock(Path(value['weights'])) != value['model']:
            raise ValueError('Completed candidate evidence changed')
        if source_lock(value['code_root']) != value['code']: raise ValueError('Completed candidate code changed')
        return True
    # Evaluations are not silently reused with different labels or retention choices.
    return False


def run_workers(base, number, action, approvals=None, labels=None, integration=False, retain=False):
    """One coordinator owns both workers and their lifetime; no approvals are synthesized."""
    import psutil
    base = Path(base)
    group = members(number)
    numbers = (group[0],) if integration else group
    if action == 'test' and not approvals: raise ValueError('Per-round start approvals required')
    if action == 'evaluate' and not labels: raise ValueError('Scorer labels required')
    with exclusive(base / 'locks/execution.lock'):
        if (base / 'locks/metadata.lock').exists(): raise ValueError('Metadata revision in progress')
        verify(base)
        skipped = [n for n in numbers if already_finished(base, n, action, integration, retain)]
        numbers = tuple(n for n in numbers if n not in skipped)
        if not numbers: return dict(action=action, already_finished=skipped, launched=[])
        for n in numbers:
            precheck(base, n, action, approvals, integration)
            if action == 'evaluate':
                target = group_dir(base,n) / 'integration' if integration else round_dir(base,n)
                if (target / ('retain_evaluation' if retain else 'evaluation')).exists():
                    raise ValueError('Evaluation output already exists; preserve and review it before a new attempt')
        for n in numbers:
            if any(c >= psutil.cpu_count() for c in cpu_set(n)): raise ValueError('CPU allocation unavailable')
        job_id = uuid.uuid4().hex
        dest = base / 'jobs' / job_id
        dest.mkdir(parents=True)
        job = dict(created_at=now(), parent_pid=os.getpid(), base=str(base.resolve()), rounds=list(numbers), action=action,
                   already_finished=skipped, approvals=str(Path(approvals).resolve()) if approvals else None,
                   labels=str(Path(labels).resolve()) if labels else None, integration=integration, retain=retain)
        job['controller_code'] = controller_lock()
        write(dest / 'job.json', job)
        processes, logs = [], []
        try:
            for n in numbers:
                executable = ROOT / ('.training_env/Scripts/python.exe' if action=='train' else '.labeling_paddle_env/Scripts/python.exe')
                log = (dest / f'round_{n:02d}.log').open('w', encoding='utf-8')
                logs.append(log)
                process = subprocess.Popen([str(executable), str(ROOT / 'notebooks/project/run.py'),
                    'scripts.run_round_groups', '_worker', '--workspace', str(base.resolve()), '--round', str(n),
                    '--job', str(dest / 'job.json')], env=child_environment(cpu_set(n)), cwd=ROOT,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name!='nt',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                processes.append((n, process))
            minimum_available = psutil.virtual_memory().available
            while any(p.poll() is None for _, p in processes):
                minimum_available = min(minimum_available, psutil.virtual_memory().available)
                time.sleep(.2)
            result = dict(job=evidence(dest / 'job.json'), finished_at=now(),
                          workers=[dict(round=n, returncode=p.returncode) for n,p in processes],
                          minimum_available_memory_bytes=minimum_available,
                          all_passed=all(p.returncode==0 for _,p in processes))
            if controller_lock() != job['controller_code']:
                result.update(all_passed=False, controller_error='Controller code changed during execution')
            write(dest / 'result.json', result)
            if not result['all_passed']: raise RuntimeError('Worker failed; results retained at ' + str(dest))
            return result
        finally:
            for _, process in processes: stop_process(process)
            for log in logs: log.close()


def controller_lock():
    names = ['run_round_groups.py', 'grouped_rounds.py', 'grouped_plan.py', 'grouped_review.py',
             'grouped_training.py', 'prepare_grouped_stage2.py', 'prepare_sequential_rounds.py',
             'operating_environment.py']
    paths = [ROOT / 'notebooks/project/scripts' / name for name in names]
    paths.append(ROOT / 'notebooks/project/run.py')
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}


def is_coordinator_child(job, job_path, number):
    """Windows venv redirectors add exactly one validated launcher between worker and coordinator."""
    import psutil
    if os.getppid() == job['parent_pid']: return True
    if os.name != 'nt': return False
    try:
        launcher = psutil.Process(os.getppid())
        if launcher.ppid() != job['parent_pid']: return False
        expected = [str(ROOT / 'notebooks/project/run.py'), 'scripts.run_round_groups', '_worker',
                    '--workspace', str(Path(job['base']).resolve()), '--round', str(number),
                    '--job', str(Path(job_path))]
        return (Path(launcher.exe()).resolve() == Path(sys.executable).resolve()
                and launcher.cmdline()[1:] == expected)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def worker(job_path, number):
    from scripts.operating_environment import limit_cpu
    job = read(job_path)
    if number not in job['rounds'] or not is_coordinator_child(job, job_path, number):
        raise ValueError('Worker must be launched by the active coordinator')
    if job.get('controller_code') != controller_lock():
        raise ValueError('Worker controller code differs from coordinator')
    base = Path(job['base'])
    limit_cpu(cpu_set(number))
    with exclusive(base / 'locks' / ('cpu_A.lock' if cpu_set(number)[0]==0 else 'cpu_B.lock')):
        precheck(base, number, job['action'], job['approvals'], job['integration'])
        if job['action']=='qualify': qualification(base, number)
        elif job['action']=='test': infer(base, number, Path(job['approvals']) / f'round_{number:02d}.json')
        elif job['action']=='train':
            from scripts.grouped_training import train
            target = group_dir(base, number) / 'integration' if job['integration'] else round_dir(base, number)
            train(target / 'training_release.json', ROOT / '.labeling_paddle_env/Scripts/python.exe')
        elif job['action']=='evaluate':
            from scripts.grouped_review import evaluate_candidate
            evaluate_candidate(base, number, Path(job['labels']), job['integration'], job['retain'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','verify','status','import-round1','link-history','revise-mapping','freeze','qualify','test','score',
        'bindings','release','integration-review','release-integration','train','evaluate','finish','refresh-report','_worker'])
    parser.add_argument('--workspace', type=Path, default=BASE)
    parser.add_argument('--round', type=int, choices=range(1,9))
    parser.add_argument('--weights', type=Path)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--approvals-dir', type=Path)
    parser.add_argument('--labels', type=Path)
    parser.add_argument('--groups', type=Path)
    parser.add_argument('--pool', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--code-root', type=Path)
    parser.add_argument('--job', type=Path)
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--integration', action='store_true')
    parser.add_argument('--retain', action='store_true')
    args = parser.parse_args()
    base, n, action = args.workspace, args.round, args.action
    if action not in ('prepare','verify','status','import-round1','link-history','revise-mapping') and n is None: parser.error('--round required')
    result = None
    if action=='prepare': result=prepare(base)
    elif action=='verify': result=verify(base)
    elif action=='status': result=status(base)
    elif action=='revise-mapping':
        if not args.mapping: parser.error('--mapping required')
        result=revise_mapping(base,args.mapping)
    elif action=='import-round1':
        from scripts.grouped_review import import_round1
        result=import_round1(base)
    elif action=='link-history':
        from scripts.grouped_review import link_development_history
        result=link_development_history(base)
    elif action=='freeze': result=freeze(base,n,args.weights)
    elif action=='refresh-report':
        from scripts.grouped_rounds import render_report
        render_report(base,n)
    elif action in ('qualify','test','train','evaluate'):
        result=run_workers(base,n,action,args.approvals_dir,args.labels,args.integration,args.retain)
    elif action=='score':
        if not args.labels: parser.error('--labels required')
        score(base,n,args.labels)
    elif action in ('bindings','release','release-integration','integration-review'):
        from scripts.grouped_training import training_bindings, create_training_release, integration_review
        if action=='integration-review': result=integration_review(base,n)
        else:
            if not args.config: parser.error('--config required')
            if action=='bindings': result=training_bindings(base,n,args.config,args.groups,args.pool,args.code_root)
            else:
                if not args.approval: parser.error('--approval required')
                result=create_training_release(base,n,args.approval,args.config,args.groups,args.pool,action=='release-integration',args.code_root)
    elif action=='finish':
        from scripts.grouped_review import finish
        if not args.approval: parser.error('--approval required')
        result=finish(base,n,args.approval,args.retain)
    elif action=='_worker':
        if not args.job: parser.error('--job required')
        worker(args.job,n)
    if result is not None: print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
