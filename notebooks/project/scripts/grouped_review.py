"""History import, cumulative candidate evaluation, and evidence-backed group completion."""
from datetime import datetime, timezone
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read, digest
from scripts.grouped_plan import members, GROUPS, verify
from scripts.grouped_rounds import (group_dir, round_dir, now, evidence, checked_evidence, model_lock,
    source_lock, execution_release, prior_completion, run_notebook, report_approval, render_report, exclusive)


def import_round1(base):
    """Reference the existing test, never invent historical training completion."""
    verify(base)
    history = read(Path(base) / 'legacy_history.json')
    previous = history['round1']
    old = read(checked_evidence(previous['report.json']))
    runtime = read(checked_evidence(previous['runtime.json']))
    state = read(checked_evidence(previous['state.json']))
    manifest = Path(base) / 'test_round_01.csv'
    if csv_read(manifest) != csv_read(checked_evidence(state['manifest'])):
        raise ValueError('Round 1 membership changed; cannot import its evaluation')
    dest = round_dir(base, 1)
    dest.mkdir(parents=True, exist_ok=False)
    report = dict(old, images=216, created_at=datetime.fromtimestamp(
        Path(previous['report.json']['path']).stat().st_mtime, timezone.utc).isoformat(),
        history_source=previous['report.json'], timing_scope='Preserved historical notebook run; not a new execution')
    write(dest / 'initial_report.json', report)
    state.update(status='awaiting_user_review', round=1, report=evidence(dest / 'initial_report.json'),
                 manifest=evidence(manifest), imported_history=True)
    write(dest / 'state.json', state)
    render_report(base, 1)
    return dict(round=1, test_imported=True, training_completion_imported=False)


def link_development_history(base):
    """Keep the demonstrated 204 correct cases protected without promoting that bundle."""
    legacy = Path(read(Path(base) / 'plan.json')['legacy_workspace'])
    comparison_path = legacy / 'remediation_12/comparison.json'
    csv_path = legacy / 'remediation_12/candidate_01/submission.csv'
    comparison = read(comparison_path)
    predictions = {r['image_id']: r['final_date'] for r in csv_read(csv_path)}
    details = comparison['detail']
    if len(details)!=216 or len(predictions)!=216 or len({r['image_id'] for r in details})!=216:
        raise ValueError('Historical development coverage mismatch')
    if any(predictions.get(r['image_id'])!=r['after'] or r['after_correct']!=(r['expected']==r['after']) for r in details):
        raise ValueError('Historical development predictions disagree with comparison')
    protected = {r['image_id']:r['expected'] for r in details if r['after_correct']}
    if len(protected)!=comparison['correct'] or len(protected)!=204:
        raise ValueError('Historical protected set mismatch')
    value = dict(source=evidence(comparison_path), predictions=evidence(csv_path), protected_expected=protected,
                 training_attempts=evidence(legacy / 'remediation_13/final_summary.json'),
                 model_promoted=False, group_completed=False, case_106_extra_work_held=True,
                 scope='Historical development protection and rejected training attempts, not an independent test')
    path = Path(base) / 'development_history.json'
    if path.exists():
        if read(path)!=value: raise ValueError('Development history changed; preserve prior version and review')
    else: write(path,value)
    render_report(base,1)
    return dict(protected_correct=204,training_history_linked=True,group_completed=False)


def correct_ids(report, ids):
    return set(ids) - {row['image_id'] for row in report['metrics']['errors']}


def evaluation_gate(reports, protected):
    correct, runtime_ok, format_ok = set(), True, True
    for report in reports:
        correct.update(correct_ids(report, report['ids']))
        runtime = report['runtime']
        runtime_ok &= runtime['status'] == 'completed' and not runtime['failures']
        format_ok &= report['metrics']['submission_format']['all_rows_compliant']
    regressions = sorted(set(protected) - correct)
    return dict(correct_ids=sorted(correct), regressions=regressions,
                correctness_protected=not regressions, runtime_valid=bool(runtime_ok), format_valid=bool(format_ok),
                eligible=not regressions and bool(runtime_ok) and bool(format_ok))


def evaluate_candidate(base, number, labels_path, integration=False, retain=False):
    from scripts.evaluate_pipeline import read_labels, score_predictions
    from scripts.grouped_training import validate_training
    from scripts.grouped_rounds import require_pair_scored
    verify(base)
    require_pair_scored(base, number)
    target = group_dir(base, number) / 'integration' if integration else round_dir(base, number)
    candidate = read(target / 'candidate_complete.json')
    value = validate_training(checked_evidence(candidate['training_release']))
    checked_evidence(candidate['selection'])
    checked_evidence(candidate['checkpoint'])
    checked_evidence(candidate['export_loading'])
    initial = execution_release(base, number)
    chosen = initial if retain else candidate
    if model_lock(Path(chosen['weights'])) != chosen['model']: raise ValueError('Selected model changed')
    if source_lock(chosen['code_root']) != chosen['code']: raise ValueError('Selected code changed')
    dest = target / ('retain_evaluation' if retain else 'evaluation')
    dest.mkdir(parents=True, exist_ok=False)
    previous = prior_completion(base, number)
    protected = set(previous['protected_correct']) if previous else set()
    history_path = Path(base) / 'development_history.json'
    history = read(history_path) if history_path.exists() else {}
    if history:
        checked_evidence(history['source']); checked_evidence(history['predictions'])
        protected.update(history['protected_expected'])
    for n in members(number):
        s = read(round_dir(base, n) / 'state.json')
        r = read(checked_evidence(s['report']))
        ids = [row['image_id'] for row in csv_read(Path(base) / f'test_round_{n:02d}.csv')]
        protected.update(correct_ids(r, ids))
    reports = []
    # Labels are read only after each inference subprocess has exited.
    for n in range(1, max(members(number)) + 1):
        manifest = Path(base) / f'test_round_{n:02d}.csv'
        out, runtime = run_notebook(base, number, weights=chosen['weights'], code_root=chosen['code_root'],
                                    output_dir=dest / f'round_{n:02d}', manifest=manifest)
        ids = [row['image_id'] for row in csv_read(manifest)]
        labels = read_labels(labels_path)
        labels = {i: labels.get(i, labels.get(i[4:])) for i in ids}
        if any(not r or r.get('라벨 상태') not in ('approved', 'manual') for r in labels.values()):
            raise ValueError('Unapproved cumulative evaluation label')
        if any(labels[i]['정답 날짜'].strip()!=expected for i,expected in history.get('protected_expected',{}).items() if i in labels):
            raise ValueError('Historical protected ground truth changed; review the protection history explicitly')
        predictions = csv_read(out / 'submission.csv') if (out / 'submission.csv').exists() else []
        if any(row['image_id'] not in ids for row in predictions): raise ValueError('Out of scope prediction')
        failures = runtime['failures'] if runtime['status']=='completed' else [dict(image_id=i) for i in ids]
        metrics = score_predictions(labels, predictions, failures, expected_ids=ids)
        report = dict(round=n, ids=ids, runtime=runtime, metrics=metrics,
                      time_target_met=runtime['status']=='completed' and runtime['total_elapsed_seconds']<=3*len(ids))
        write(out / 'report.json', report)
        reports.append(report)
    gate = evaluation_gate(reports, protected)
    result = dict(created_at=now(), round=number, rounds=list(members(number)),
                  training_release=evidence(target / 'training_release.json'), candidate=evidence(target / 'candidate_complete.json'),
                  model=chosen['model'], weights=chosen['weights'], code=chosen['code'], code_root=chosen['code_root'],
                  labels=evidence(labels_path), reports=reports, gate=gate, retained_previous=retain,
                  targets_met=all(r['time_target_met'] and r['metrics']['accuracy_target_met'] for r in reports),
                  development_100=all(r['metrics']['exact_match_rate']==1 for r in reports))
    write(dest / 'review.json', result)
    for n in members(number) if integration else (number,):
        render_report(base, n)
    return result


def finish(base, number, approval_path, retain=False):
    from scripts.grouped_training import validate_training
    number = members(number)[0]
    paired = len(members(number)) == 2
    target = group_dir(base, number) / 'integration' if paired else round_dir(base, number)
    path = target / ('retain_evaluation' if retain else 'evaluation') / 'review.json'
    review = read(path)
    release = validate_training(checked_evidence(review['training_release']))
    candidate = read(checked_evidence(review['candidate']))
    for item in ('selection', 'checkpoint', 'export_loading'): checked_evidence(candidate[item])
    expected_rounds = list(range(1, max(members(number)) + 1))
    if [r['round'] for r in review['reports']] != expected_rounds: raise ValueError('Missing cumulative evaluation rounds')
    gate = review['gate']
    if not gate['eligible']: raise ValueError('Regression, runtime, or output format gate failed')
    if model_lock(Path(review['weights'])) != review['model'] or source_lock(review['code_root']) != review['code']:
        raise ValueError('Reviewed model/code changed')
    bindings = dict(rounds=list(members(number)), model=review['model'], code=review['code'], retained_previous=retain,
                    training_release_sha256=digest(review['training_release']['path']))
    approved = report_approval(approval_path, 'complete_group', number, path, bindings)
    if not review['targets_met'] and approved.get('accept_target_shortfall') is not True:
        raise ValueError('Targets missed; explicit reviewed shortfall acceptance required')
    dest = group_dir(base, number)
    with exclusive(Path(base) / 'locks' / 'completion.lock'):
        if (dest / 'completion.json').exists(): raise ValueError('Group completion already exists')
        value = dict(status='complete', created_at=now(), rounds=list(members(number)), weights=review['weights'],
                     model=review['model'], code_root=review['code_root'], code=review['code'],
                     training_release=review['training_release'], approval=evidence(approval_path),
                     evaluation=evidence(path), protected_correct=gate['correct_ids'],
                     candidate_accepted=not retain, targets_met=review['targets_met'], development_100=review['development_100'],
                     workflow_finished=number==8, independent_final_test=False)
        write(dest / 'completion.json', value)
        for n in members(number):
            rd = round_dir(base, n)
            state = read(rd / 'state.json')
            state.update(status='complete', completion=evidence(dest / 'completion.json'))
            write(rd / 'state.json', state)
            write(rd / 'completion.json', dict(group_completion=evidence(dest / 'completion.json')))
            render_report(base, n)
    return value
