"""Grouped workflow control. No command creates a user approval or overwrites a model."""
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, read, write, digest, csv_read, csv_write
from scripts.sequential_rounds import evidence, checked_evidence, code_lock, model_lock, approval
from scripts.grouped_plan import BASE, POLICY, GROUPS, members, previous_group, group_name, cpu_set, verify

def now():
    return datetime.now(timezone.utc).isoformat()

def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None: raise ValueError('Timezone is required')
    return result

@contextmanager
def exclusive(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(pid=os.getpid(), started_at=now())))
    try:
        yield
    finally:
        path.unlink()

def group_dir(base, number):
    return Path(base) / 'groups' / group_name(number)

def round_dir(base, number):
    members(number)
    return Path(base) / 'rounds' / f'round_{number:02d}'

def source_lock(root):
    root = Path(root)
    files = [root / n for n in ('predict.ipynb', 'requirements.txt', 'download_weights.sh')]
    files += [p for p in (root / 'notebooks/project').rglob('*') if p.is_file() and p.suffix in ('.py', '.yml', '.ps1')]
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(files)}

def prior_completion(base, number):
    previous = previous_group(number)
    if not previous: return None
    path = group_dir(base, previous[0]) / 'completion.json'
    value = read(path)
    if value['status'] != 'complete' or value['rounds'] != list(previous):
        raise ValueError('Previous group is not complete')
    if model_lock(Path(value['weights'])) != value['model']:
        raise ValueError('Previous group model changed')
    checked_evidence(value['training_release'])
    checked_evidence(value['approval'])
    checked_evidence(value['evaluation'])
    if source_lock(value['code_root']) != value['code']:
        raise ValueError('Previous group code changed')
    if value.get('completion_kind') == 'legacy_user_closure':
        from scripts.prepare_grouped_stage2 import validate_legacy_completion
        validate_legacy_completion(base, value)
    return value

def freeze(base, number, weights=None):
    verify(base)
    previous = prior_completion(base, number)
    if weights is None:
        if not previous: raise ValueError('Round 1 requires an explicit model bundle')
        weights = Path(previous['weights'])
    weights = Path(weights).resolve()
    if previous and model_lock(weights) != previous['model']:
        raise ValueError('Both rounds must start with the previous group selected model')
    dest = group_dir(base, number) / 'release'
    dest.mkdir(parents=True, exist_ok=False)
    snapshot = dest / 'code'
    origin = Path(previous['code_root']) if previous else ROOT
    before = source_lock(origin)
    for name in before:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin / name, target)
    model_before = model_lock(weights)
    shutil.copytree(weights, snapshot / 'weights/paddle')
    if source_lock(origin) != before or source_lock(snapshot) != before or model_lock(snapshot / 'weights/paddle') != model_before:
        raise ValueError('Code or model changed during snapshot preparation')
    value = dict(policy=POLICY, rounds=list(members(number)), created_at=now(),
                 code_root=str(snapshot), asset_root=str(ROOT), code=before, model=model_before,
                 weights=str(snapshot / 'weights/paddle'), previous_completion=evidence(
                     group_dir(base, previous_group(number)[0]) / 'completion.json') if previous else None)
    write(dest / 'release.json', value)
    return value

def execution_release(base, number):
    path = group_dir(base, number) / 'release/release.json'
    value = read(path)
    if value['rounds'] != list(members(number)): raise ValueError('Wrong group release')
    if source_lock(value['code_root']) != value['code'] or model_lock(Path(value['weights'])) != value['model']:
        raise ValueError('Immutable execution release changed')
    if value['previous_completion']: checked_evidence(value['previous_completion'])
    return value

def report_approval(path, action, number, report_path, bindings):
    report = read(report_path)
    value = approval(path, action, number, dict(report_sha256=digest(report_path), **bindings))
    if not isinstance(value.get('feedback'), str) or not value['feedback'].strip():
        raise ValueError('Actual feedback or an explicit user statement of no further comments is required')
    if stamp(value['approved_at']) < stamp(report['created_at']):
        raise ValueError('Approval predates the reviewed report')
    return value

def require_pair_scored(base, number):
    for n in members(number):
        state = read(round_dir(base, n) / 'state.json')
        checked_evidence(state['report'])
        if state['status'] not in ('awaiting_user_review', 'originals_admitted', 'candidate_complete', 'complete'):
            raise ValueError('Both first tests must finish and be scored before training')

def render_report(base, number):
    """One representative Markdown per round; immutable JSON evidence stays separate."""
    dest = round_dir(base, number)
    state = read(dest / 'state.json')
    report = read(checked_evidence(state['report']))
    metrics = report['metrics']
    lines = [f'# {number}회 결과보고서', '', f"상태: {state['status']}", '',
             f"최초 평가: {metrics['exact_match_rate']:.2%}, {report['images']}장.",
             f"노트북 전체: {report['runtime']['total_elapsed_seconds']:.3f}초.",
             f"평균: {report['mean_seconds']:.3f}초/장. 시간 목표: {report['time_target_seconds']}초.",
             f"최초 평가 근거: {state['report']['path']}", '',
             '## 오답의 구조적 원인과 해결', '',
             '오답별 검출·잘림·문자 인식·조각 결합·문맥·선택 원인은 analysis.json에 기록합니다.',
             '분석이 없으면 미분석이며 원인을 자동으로 확정하지 않습니다.', '']
    lines += ['최초 평가 진단:', '```json', json.dumps(dict(
        exact_matches=metrics.get('exact_matches'), field_metrics=metrics.get('field_metrics'),
        submission_format=metrics.get('submission_format'), error_types=metrics.get('error_type_counts'),
        errors=metrics.get('errors')), ensure_ascii=False, indent=2), '```', '']
    analysis = dest / 'analysis.json'
    if analysis.exists(): lines += ['```json', json.dumps(read(analysis), ensure_ascii=False, indent=2), '```', '']
    history_path = Path(base) / 'development_history.json'
    if number == 1 and history_path.exists():
        history = read(history_path)
        lines += ['## 기존 개발·학습 이력', '',
                  f"기존 개발 보호 정답: {len(history['protected_expected'])}/216. 최초 평가와 구분합니다.",
                  f"개발 결과 근거: {history['source']['path']}",
                  f"실제 후속 학습·후보 기각 근거: {history['training_attempts']['path']}",
                  '기존 학습 이력의 연결은 새 단계의 완료나 가중치 반영을 뜻하지 않습니다.', '']
    legacy_closed = state.get('completion_kind') == 'legacy_user_closure'
    if legacy_closed:
        completion = read(checked_evidence(state['completion']))
        lines += ['## 사용자 종료 승계', '',
                  'remediation_12의 204/216 및 미해결 12건을 유지한 사용자 종료를 승계했습니다.',
                  '새 정식 평가·학습 완료나 95% 목표 달성으로 기록한 것이 아닙니다.',
                  '2단계 준비 지시를 연결했으며 2·3회 정식 테스트 시작 승인은 별도입니다.',
                  f"종료 검증 근거: {completion['evaluation']['path']}",
                  f"기존 승인 원본·crop·고정 그룹: {completion['training_release']['path']}", '']
    for heading, filename in [('사용자 피드백과 학습 승인', 'training_release.json'),
                               ('학습 후보 결과', 'candidate_complete.json'),
                               ('최종 판정', 'completion.json')]:
        lines += [f'## {heading}', '']
        path = dest / filename
        lines += [f'근거: {path}' if path.exists() else
                  ('기존 실행·승인 이력은 위 사용자 종료 승계 근거에 보존됨; 추가 실행 없음' if legacy_closed else '대기 / 미실행'), '']
        if filename == 'training_release.json' and path.exists():
            value = read(path)
            approved = read(checked_evidence(value['approval']))
            lines += [approved['feedback'], '']
    for name in ('evaluation', 'retain_evaluation'):
        path = dest / name / 'review.json'
        if path.exists():
            review = read(path)
            lines += ['## 학습 후 누적 개발 재평가', '', f'근거: {path}',
                      '```json', json.dumps(dict(gate=review['gate'], targets_met=review['targets_met']),ensure_ascii=False,indent=2), '```', '']
    if len(members(number)) == 2:
        integration = group_dir(base, number) / 'integration'
        lines += ['## 묶음 통합 학습·검증', '']
        for name in ('review.json', 'training_release.json', 'candidate_complete.json',
                     'evaluation/review.json', 'retain_evaluation/review.json'):
            if (integration / name).exists(): lines += [f'근거: {integration / name}', '']
    lines += ['최초 평가와 학습 후 개발 재평가는 구분합니다. 병행 실행 시간은 공유 RAM·I/O 환경의 로컬 측정입니다.',
              '초기 개발 미사용과 원본·상품 그룹 단위 독립성은 별개입니다.', '']
    (dest / 'report.md').write_text('\n'.join(lines), encoding='utf-8')

def child_environment(cpus):
    return {**os.environ, 'ITDA_CPU_SET': ','.join(map(str, cpus)), 'CUDA_VISIBLE_DEVICES': '',
            'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4',
            'FLAGS_num_threads': '4', 'FLAGS_paddle_num_threads': '4'}

def stop_process(process):
    if process.poll() is not None: return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
    else:
        import signal
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()

def run_notebook(base, number, qualification=False, weights=None, output_dir=None, manifest=None, code_root=None):
    """Only images and inference files enter this notebook's submission copy."""
    from scripts.operating_environment import enforce, network_probe
    import psutil
    release = execution_release(base, number)
    cpus = cpu_set(number)
    proof = enforce(cpus)
    dest = Path(output_dir) if output_dir else (group_dir(base, number) / f'qualification_{number:02d}' if qualification else round_dir(base, number))
    dest.mkdir(parents=True, exist_ok=False)
    sandbox = dest / 'submission'
    sandbox.mkdir()
    source = Path(code_root or release['code_root'])
    source_before = source_lock(source)
    for name in ('predict.ipynb', 'requirements.txt', 'download_weights.sh'):
        shutil.copy2(source / name, sandbox / name)
    shutil.copytree(source / 'notebooks/project/src', sandbox / 'notebooks/project/src', ignore=shutil.ignore_patterns('__pycache__'))
    bundle = Path(weights or release['weights'])
    bundle_hash = model_lock(bundle)
    shutil.copytree(bundle, sandbox / 'weights/paddle')
    input_dir = dest / 'input'
    input_dir.mkdir()
    if qualification:
        asset = Path(release['asset_root'])
        record = read(asset / '학습 및 테스트 결과/02_annotations/records/BMLC002247.json')
        if not record['seen_in_development']: raise ValueError('Qualification image must be historically exposed')
        original = asset / '학습대상데이터/BMLC002247.jpg'
        if digest(original) != record['image_sha256']: raise ValueError('Qualification image changed')
        rows = [dict(image_id=original.stem, image_path=str(original))]
    else:
        rows = csv_read(manifest or Path(base) / f'test_round_{number:02d}.csv')
        mapping = {r['test_id']: r for r in csv_read(Path(base) / 'test_to_original_mapping.csv')}
        if any(digest(r['image_path']) != mapping[r['image_id']]['test_sha256'] for r in rows):
            raise ValueError('Test image changed')
    for row in rows:
        image = Path(row['image_path'])
        shutil.copy2(image, input_dir / image.name)
    output = dest / 'submission.csv'
    kernel = dest / 'jupyter'
    write(kernel / 'kernels/python3/kernel.json', dict(argv=[sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
                                                     display_name='ITDA grouped frozen kernel', language='python'))
    env = {**child_environment(cpus), 'JUPYTER_PATH': str(kernel),
           'ITDA_INPUT_DIR': str(input_dir), 'ITDA_OUTPUT_PATH': str(output)}
    started = time.perf_counter()
    peak_rss, peak_commit, minimum_available, affinity_checks = 0, 0, psutil.virtual_memory().available, 0
    status, process = 'failed', None
    try:
        with (dest / 'inference.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'nbconvert', '--execute', '--to', 'notebook',
                      '--ExecutePreprocessor.timeout=2400', '--output', 'executed.ipynb', 'predict.ipynb'],
                      cwd=sandbox, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt')
            while process.poll() is None:
                if time.perf_counter() - started > 2400:
                    status = 'timeout'
                    stop_process(process)
                    break
                try:
                    parent = psutil.Process(process.pid)
                    rss, commit = 0, 0
                    for child in [parent, *parent.children(recursive=True)]:
                        try:
                            if set(child.cpu_affinity()) != set(cpus): raise RuntimeError('Notebook child escaped CPU allocation')
                            memory = child.memory_info()
                            rss += memory.rss
                            commit += getattr(memory, 'private', memory.vms)
                            affinity_checks += 1
                        except psutil.NoSuchProcess: pass
                    peak_rss, peak_commit = max(peak_rss, rss), max(peak_commit, commit)
                    minimum_available = min(minimum_available, psutil.virtual_memory().available)
                except psutil.NoSuchProcess: pass
                time.sleep(.2)
            else:
                status = 'completed' if process.returncode == 0 and output.is_file() else 'failed'
    except Exception as error:
        if process: stop_process(process)
        proof['error'] = repr(error)
    finally:
        runtime = dict(status=status, total_elapsed_seconds=time.perf_counter()-started, images=len(rows),
                       environment=proof, peak_tree_rss_bytes=peak_rss, peak_tree_commit_bytes=peak_commit,
                       minimum_available_memory_bytes=minimum_available, child_affinity_checks=affinity_checks,
                       timing_scope='nbconvert startup and complete notebook; copies and scoring excluded', failures=[])
        executed = sandbox / 'executed.ipynb'
        if executed.exists():
            for cell in read(executed)['cells']:
                for item in cell.get('outputs', []):
                    text = ''.join(item.get('text', []))
                    for index, char in enumerate(text):
                        if char != '{': continue
                        try: summary, _ = json.JSONDecoder().raw_decode(text[index:])
                        except ValueError: continue
                        if isinstance(summary, dict) and 'p50_image_seconds' in summary:
                            runtime.update(pipeline_summary=summary, failures=summary['failures'],
                                           p50=summary['p50_image_seconds'], p95=summary['p95_image_seconds'])
        try:
            runtime['network_after'] = network_probe()
            execution_release(base, number)
            if source_lock(source) != source_before: raise ValueError('Inference code changed during execution')
            if model_lock(bundle) != bundle_hash: raise ValueError('Candidate bundle changed during execution')
        except Exception as error:
            runtime.update(status='failed', verification_error=repr(error))
        write(dest / 'runtime.json', runtime)
    return dest, runtime

def qualification(base, number):
    dest, runtime = run_notebook(base, number, qualification=True)
    if runtime['status'] != 'completed' or runtime['failures'] or not runtime['child_affinity_checks']:
        raise ValueError('Offline qualification failed; retained runtime evidence')
    rows = csv_read(dest / 'submission.csv')
    if len(rows) != 1 or rows[0]['image_id'] != 'BMLC002247': raise ValueError('Qualification output mismatch')
    value = dict(status='passed', cpus=cpu_set(number), release=evidence(group_dir(base, number) / 'release/release.json'),
                 runtime=evidence(dest / 'runtime.json'), created_at=now())
    write(dest / 'qualification.json', value)

def check_qualification(base, number):
    q = read(group_dir(base, number) / f'qualification_{number:02d}/qualification.json')
    if q['status'] != 'passed' or q['cpus'] != cpu_set(number): raise ValueError('CPU qualification mismatch')
    if checked_evidence(q['release']) != group_dir(base, number) / 'release/release.json':
        raise ValueError('Wrong qualified release')
    checked_evidence(q['runtime'])

def infer(base, number, approval_path):
    release = execution_release(base, number)
    verify(base)
    check_qualification(base, number)
    prior_completion(base, number)
    manifest = Path(base) / f'test_round_{number:02d}.csv'
    approval(approval_path, 'start_test', number, dict(manifest_sha256=digest(manifest),
             code=release['code'], model=release['model']))
    with exclusive(Path(base) / 'locks' / f'round_{number:02d}.lock'):
        dest, runtime = run_notebook(base, number)
        state = dict(status='inference_complete', round=number, created_at=now(), manifest=evidence(manifest),
                     code=release['code'], model=release['model'], start_approval=evidence(approval_path),
                     runtime=evidence(dest / 'runtime.json'), predictions=evidence(dest / 'submission.csv')
                     if (dest / 'submission.csv').exists() else None)
        write(dest / 'state.json', state)

def score(base, number, labels_path):
    from scripts.evaluate_pipeline import read_labels, score_predictions
    dest = round_dir(base, number)
    state = read(dest / 'state.json')
    if state['status'] != 'inference_complete': raise ValueError('Inference must finish before scoring')
    runtime = read(checked_evidence(state['runtime']))
    ids = [r['image_id'] for r in csv_read(checked_evidence(state['manifest']))]
    all_labels = read_labels(labels_path)
    labels = {i: all_labels.get(i, all_labels.get(i[4:])) for i in ids}
    if any(not v or v.get('라벨 상태') not in ('approved', 'manual') for v in labels.values()):
        raise ValueError('Each label must be approved')
    predictions = csv_read(checked_evidence(state['predictions'])) if state['predictions'] else []
    if any(r['image_id'] not in ids for r in predictions): raise ValueError('Out-of-round prediction')
    failures = runtime['failures']
    if runtime['status'] != 'completed': failures = [dict(image_id=i, error='Incomplete run') for i in ids]
    metrics = score_predictions(labels, predictions, failures, expected_ids=ids)
    mapping = {r['test_id']: r for r in csv_read(Path(base) / 'test_to_original_mapping.csv')}
    previous = prior_completion(base, number)
    admitted = read(checked_evidence(previous['training_release']))['admitted'] if previous else {}
    strata = {}
    for name, subset in dict(original=[i for i in ids if mapping[i]['augmented']=='false'],
                             augmented=[i for i in ids if mapping[i]['augmented']=='true'],
                             initial_development=[i for i in ids if mapping[i]['seen_in_development']=='true'],
                             previous_original=[i for i in ids if mapping[i]['original_id'] in admitted],
                             unresolved_original=[i for i in ids if not mapping[i]['original_id']]).items():
        strata[name] = score_predictions(labels, [p for p in predictions if p['image_id'] in subset], failures,
                                        expected_ids=subset) if subset else None
    report = dict(round=number, created_at=now(), images=len(ids), runtime=runtime, metrics=metrics, strata=strata,
                  mean_seconds=runtime['total_elapsed_seconds']/len(ids), time_target_seconds=3*len(ids),
                  time_target_met=runtime['status']=='completed' and runtime['total_elapsed_seconds']<=3*len(ids),
                  ground_truth=evidence(labels_path), manifest=state['manifest'], code=state['code'], model=state['model'])
    write(dest / 'initial_report.json', report)
    state.update(status='awaiting_user_review', report=evidence(dest / 'initial_report.json'))
    write(dest / 'state.json', state)
    render_report(base, number)
