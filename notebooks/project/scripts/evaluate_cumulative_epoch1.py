"""User-authorized epoch-1 evaluation: 1, then (2,3), then (4,5); no training/promotion."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path('C:/ITDA_OCR_CODE')
BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1')
TRAIN = BASE / 'cumulative-1-5-20260915-v2'
RUN = BASE / 'cumulative-1-5-epoch1-eval-20260915-v1'
REPORTS = ROOT / 'notebooks/docs/training/cumulative_1_5_20260915/epoch1_evaluation'
COUNTS = {1:216, 2:500, 3:500, 4:394, 5:500}
INSTRUCTION = '직전 누적 학습의 1 epoch checkpoint에 따라 1회~5회 전체 이미지 테스트를 실행한다. 1회는 단독으로 실행한다. 2회와 3회, 4회와 5회를 동시에 묶어서 실행한다.'
LABELS_SOURCE = TRAIN/'saved-output-rescore/labels.latest.csv'
WORKER_SCRIPT = 'evaluate_cumulative_epoch1.py'
os.environ.update(ITDA_ASSET_ROOT=str(ROOT), ITDA_GROUPED_RELEASE='1', ITDA_EXPLICIT_TEST_INSTRUCTION='1',
    ITDA_EXECUTION_POLICY='base-first-v2', ITDA_SHARE_RECOGNIZER='1', PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',
    OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', MKL_NUM_THREADS='4', FLAGS_num_threads='4', FLAGS_paddle_num_threads='4')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_sequential_rounds import read, write, digest, csv_read
from scripts.grouped_rounds import (exclusive, source_lock, model_lock, original_inputs, embedded_source_manifest,
    labels_for, run_notebook, now, cpu_set)


def reject_active():
    import psutil
    own = {os.getpid(), *[p.pid for p in psutil.Process().parents()]}
    tokens = ('nbconvert', 'train_cumulative', 'train_joint', 'train_sequential', 'run_prepared', 'evaluate_cumulative_epoch1', 'evaluate_weighted_epoch1')
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid not in own and 'python' in (p.info['name'] or '').lower() and any(t in ' '.join(p.info['cmdline'] or []) for t in tokens):
            raise RuntimeError('Existing OCR worker: '+str(p.pid))


def check_files(files):
    for path, expected in files.items():
        if digest(Path(path)) != expected:
            raise ValueError('Protected file changed: '+path)


def training_evidence():
    summary = read(TRAIN/'training-summary.json')
    check_files(summary['source_files'])
    check_files(read(TRAIN/'code-review/final-code-proof.json')['files'])
    checkpoint = summary['checkpoints']['epoch_001.pdparams']
    assert digest(Path(checkpoint['path'])) == checkpoint['sha256']
    assert checkpoint['sha256'] == '8ca6c7355fbdfbd12cd86d96898500e02a13f9d87c0ca2711c22d4eb89c00592'
    return checkpoint


def prepare():
    from scripts.operating_environment import limit_cpu
    reject_active()
    with exclusive(BASE/'locks/execution.lock'):
        RUN.mkdir(exist_ok=False)
        checkpoint = training_evidence()
        workbook = ROOT/'학습대상_정답지/answer_000001_002610_manual.xlsx'
        assert digest(workbook) == '765db2f4781ec1975893e66b7c3c755f8a68246c68fc05d302597d36900a4d2d'
        preservation = read(BASE/'answer-correction-20260915-v1/preservation.after.json')['protected_hashes']
        check_files(preservation)
        write(RUN/'authorization.json', dict(actor='user', instruction=INSTRUCTION, recorded_at=now(),
            source_reference='Current conversation user message following training completion report',
            checkpoint=checkpoint, rounds=list(COUNTS), order=[[1],[2,3],[4,5]],
            online_execution=True, online_authority='Prior user instruction: 관리자 실행 승인요청화면 띄울 필요 없이 온라인으로 실행',
            prior_internal_gate_passed=False, evaluation_only=True, promotion_allowed=False, training_allowed=False))
        limit_cpu([0,1,2,3])
        config = TRAIN/'release/config.yml'
        export = RUN/'export'
        command = [str(ROOT/'.training_env/Scripts/python.exe'), str(ROOT/'training_runtime/PaddleOCR-v3.7.0/tools/export_model.py'),
            '-c',str(config),'-o','Global.pretrained_model='+str(Path(checkpoint['path']).with_suffix('')),
            'Global.checkpoints=null','Global.save_inference_dir='+str(export),'Global.use_gpu=False']
        write(RUN/'export-command.json', dict(command=command, checkpoint=checkpoint, config_sha256=digest(config), cpus=[0,1,2,3]))
        with (RUN/'export.log').open('x',encoding='utf-8') as log:
            subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        bundle = RUN/'bundle'
        shutil.copytree(TRAIN/'starting_bundle',bundle,ignore=shutil.ignore_patterns('korean_PP-OCRv5_mobile_rec'))
        shutil.copytree(export,bundle/'korean_PP-OCRv5_mobile_rec')
        before = source_lock(ROOT)
        code = RUN/'code'
        for name in before:
            target=code/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
        assert source_lock(code)==before==source_lock(ROOT)
        embedded_source_manifest(code)
        control=RUN/'control';control.mkdir()
        for name in ('test_to_original_mapping.csv','excluded_derivatives.csv'):
            shutil.copy2(BASE/name,control/name)
        shutil.copy2(LABELS_SOURCE,RUN/'labels.csv')
        mapping={r['test_id']:r for r in csv_read(control/'test_to_original_mapping.csv')}
        seen=set();manifests={}
        for number,count in COUNTS.items():
            path=BASE/f'test_round_{number:02d}.csv';rows=csv_read(path)
            assert len(rows)==count
            original_inputs(control,rows)
            originals={mapping[r['image_id']]['original_id'] for r in rows}
            expected = ({f'AMLC{i:06d}' for i in range(1,217)} if number==1 else
                {f'AMLC{i:06d}' for i in range(217,353)} | {f'BMLC{i:06d}' for i in range(2247,2611)} if number==2 else
                {f'AMLC{i:06d}' for i in range(*{3:(353,853),4:(853,1247),5:(1247,1747)}[number])})
            assert originals==expected and not seen&originals
            seen.update(originals);shutil.copy2(path,control/path.name)
            manifests[number]=dict(images=count,sha256=digest(path),cpus=cpu_set(number))
        assert len(seen)==2110
        model=model_lock(bundle)
        for group,rounds in [('group_01',[1]),('group_02_03',[2,3]),('group_04_05',[4,5])]:
            write(control/'groups'/group/'release/release.json',dict(rounds=rounds,code_root=str(code),asset_root=str(ROOT),
                code=before,weights=str(bundle),model=model,previous_completion=None,scope='User-authorized cumulative development evaluation only'))
        protected={str(p):digest(p) for p in control.rglob('*') if p.is_file()}
        protected.update(preservation)
        for p in (workbook,RUN/'labels.csv',RUN/'authorization.json',Path(checkpoint['path']),config):protected[str(p)]=digest(p)
        write(RUN/'release.json',dict(code=before,model=model,manifests=manifests,protected_files=protected,
            code_root=str(code),bundle=str(bundle),checkpoint=checkpoint,internal_gate_passed=False,created_at=now()))
        print(json.dumps(dict(status='prepared',run=str(RUN),checkpoint=checkpoint,manifests=manifests),ensure_ascii=False))


def verify_release():
    release=read(RUN/'release.json');check_files(release['protected_files'])
    assert source_lock(RUN/'code')==release['code'] and model_lock(RUN/'bundle')==release['model']
    return release


def probe():
    from scripts.operating_environment import limit_cpu
    limit_cpu([0,1,2,3])
    import numpy as np
    import paddle.inference as infer
    folder=RUN/'bundle/korean_PP-OCRv5_mobile_rec'
    config=infer.Config(str(folder/'inference.json'),str(folder/'inference.pdiparams'))
    config.disable_gpu();config.set_cpu_math_library_num_threads(4)
    predictor=infer.create_predictor(config)
    names=predictor.get_input_names();assert len(names)==1
    x=np.zeros((1,3,48,320),dtype='float32');handle=predictor.get_input_handle(names[0])
    handle.reshape(x.shape);handle.copy_from_cpu(x);predictor.run()
    shapes={}
    for name in predictor.get_output_names():
        values=predictor.get_output_handle(name).copy_to_cpu();assert np.isfinite(values).all();shapes[name]=list(values.shape)
    write(RUN/'model-load.json',dict(status='passed',synthetic_only=True,output_shapes=shapes,model=model_lock(RUN/'bundle')))


def worker(number, qualification):
    verify_release()
    dest=RUN/('qualification' if qualification else 'evaluation')/f'round_{number:02d}'
    folder,runtime=run_notebook(RUN/'control',number,qualification=qualification,weights=RUN/'bundle',output_dir=dest,
        code_root=RUN/'code',network_mode='online')
    if qualification and (runtime['status']!='completed' or not runtime['child_affinity_checks']):
        raise RuntimeError('Online qualification failed; outputs retained')


def score_round(number):
    from scripts.evaluate_pipeline import read_labels,read_predictions,score_predictions
    folder=RUN/'evaluation'/f'round_{number:02d}';runtime=read(folder/'runtime.json')
    ids=[r['image_id'] for r in csv_read(RUN/'control'/f'test_round_{number:02d}.csv')]
    labels=labels_for(RUN/'control',ids,read_labels(RUN/'labels.csv'))
    assert all(v and v['라벨 상태'] in ('manual','approved') for v in labels.values())
    output=folder/'submission.csv';partial=Path(str(output)+'.partial.csv')
    source=output if output.exists() else partial if partial.exists() else None
    predictions=read_predictions(source) if source else []
    assert {p['image_id'] for p in predictions}<=set(ids)
    metrics=score_predictions(labels,predictions,runtime.get('failures',[]),expected_ids=ids)
    assert metrics['field_total']==3*COUNTS[number] and metrics['evaluated_labels']==COUNTS[number]
    mapping={r['test_id']:r for r in csv_read(RUN/'control/test_to_original_mapping.csv')}
    by_id={r['image_id']:r for r in predictions}
    errors=[dict(e,original_id=mapping[e['image_id']]['original_id'],expected=labels[e['image_id']]['정답 날짜'],prediction=by_id.get(e['image_id'])) for e in metrics['field_errors']]
    report=dict(round=number,metrics=metrics,runtime=runtime,prediction_source=str(source),partial=source==partial,
        errors=errors,release_sha256=digest(RUN/'release.json'),scope='cumulative development, not independent final test')
    write(folder/'report.json',report)
    REPORTS.mkdir(parents=True,exist_ok=True)
    body=f'''# {number}회 1 epoch 후보 평가

원본 {COUNTS[number]}장. 상태 `{runtime['status']}`. 필드 {metrics['field_correct']}/{metrics['field_total']} = {metrics['field_accuracy']:.4%}. 95% 목표 {'충족' if metrics['accuracy_target_met'] else '미달'}.

완전 날짜 {metrics['exact_matches']}/{COUNTS[number]}는 보조 지표입니다. 실패 {len(runtime.get('failures',[]))}건, 출력 누락 {len(metrics['labels_without_predictions'])}건은 분모에 남고 득점하지 않습니다. NONE 일치는 득점합니다.

노트북 전체 {runtime['total_elapsed_seconds']:.3f}초 / 목표 {3.2*COUNTS[number]:.1f}초. 목표 충족: {runtime['time_target_met']}. 강제 종료 기준은 별도 2,400초입니다. 초기화·CSV 저장·종료를 포함하며 준비 복사와 사후 채점은 제외합니다.

CPU {cpu_set(number)}·4스레드. 프로세스 트리 RSS 관측 최대 {runtime['peak_tree_rss_bytes']/2**30:.3f}GiB, 관측 최소 시스템 여유 RAM {runtime['minimum_available_memory_bytes']/2**30:.3f}GiB. 온라인 실행이며 OS 오프라인 검증으로 표시하지 않습니다.

오답 필드 원본 {len(errors)}장. 유형 집계(완전 날짜 기준): `{json.dumps(metrics['error_type_counts'],ensure_ascii=False)}`. 원본 ID·정답·출력·오답 필드는 `{folder/'report.json'}`에 있습니다. 인식 부재와 선택 오류의 확정 분류에는 trace 검토가 필요하며, 채점 불일치만으로 원인을 단정하지 않습니다.

사용 checkpoint SHA `{read(RUN/'release.json')['checkpoint']['sha256']}`. 목록 SHA `{digest(RUN/'control'/f'test_round_{number:02d}.csv')}`. 코드·모델·정답·승인 원문은 `{RUN/'release.json'}`에 고정했습니다.

누적 개발 성적이며 독립 최종 성적이 아닙니다. 기존 최초 결과·정답·기본 weights는 보존했습니다. 추가 학습·모델 채택·단계 종료·commit/push를 하지 않았습니다.
'''
    with (REPORTS/f'round_{number:02d}.md').open('x',encoding='utf-8') as stream:stream.write(body)
    return report


def execute():
    reject_active()
    with exclusive(BASE/'locks/execution.lock'):
        with (RUN/'execution-started.json').open('x',encoding='utf-8') as stream:json.dump(dict(pid=os.getpid(),started_at=now()),stream)
        verify_release()
        script=RUN/'code/notebooks/project/scripts'/WORKER_SCRIPT
        with (RUN/'model-load.log').open('x',encoding='utf-8') as log:
            subprocess.run([sys.executable,str(script),'probe'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        reports=[]
        for qualification,groups in [(True,[[1],[2,3]]),(False,[[1],[2,3],[4,5]])]:
            for group in groups:
                verify_release();jobs=[]
                write(RUN/'status.json',dict(status='qualification' if qualification else 'testing',rounds=group,updated_at=now()))
                for number in group:
                    log=(RUN/f'{"qualification" if qualification else "test"}-{number:02d}.log').open('x',encoding='utf-8')
                    command=[sys.executable,str(script),'qualify' if qualification else 'worker','--round',str(number)]
                    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                    jobs.append((number,process,log))
                failures=[]
                for number,process,log in jobs:
                    code=process.wait();log.close()
                    if code:failures.append(dict(round=number,returncode=code))
                write(RUN/f'{"qualification" if qualification else "test"}-group-{group[0]:02d}.json',dict(rounds=group,failures=failures,ended_at=now()))
                if not qualification:
                    for number in group:
                        if (RUN/'evaluation'/f'round_{number:02d}'/'runtime.json').exists():
                            reports.append(score_round(number))
                if failures:raise RuntimeError('Worker failure; preserve counterpart results: '+repr(failures))
        verify_release()
        total=sum(r['metrics']['field_correct'] for r in reports)
        summary=dict(status='completed',images=2110,field_correct=total,field_total=6330,field_accuracy=total/6330,
            rounds=[dict(round=r['round'],field_accuracy=r['metrics']['field_accuracy'],seconds=r['runtime']['total_elapsed_seconds'],time_target_met=r['runtime']['time_target_met']) for r in reports],
            independent_final_score=False,model_adopted=False,shared_weights_changed=False,release_sha256=digest(RUN/'release.json'))
        write(RUN/'summary.json',summary);write(RUN/'status.json',dict(status='completed',updated_at=now()))
        lines=['# 1~5회 1 epoch 후보 종합 평가',f'누적 개발 필드 {total}/6330 = {total/6330:.4%}. 독립 최종 성적이 아닙니다.',
            '| 회차 | 필드 정답/3N | 정확도 | 전체 초 | 시간 목표 충족 |','|---|---:|---:|---:|---|']
        for r in reports:lines.append(f"| {r['round']} | {r['metrics']['field_correct']}/{r['metrics']['field_total']} | {r['metrics']['field_accuracy']:.4%} | {r['runtime']['total_elapsed_seconds']:.3f} | {r['runtime']['time_target_met']} |")
        lines += ['', '1회 단독 → 2·3회 병행 → 4·5회 병행으로 실행했습니다. 회차별 95%·시간·실패·누락을 별도 판단하며 평균으로 미달 회차를 숨기지 않습니다.',
            '내부 검증 미통과 이력을 유지한 1 epoch checkpoint를 이번 사용자 지시에 따라 평가했습니다. 모델 채택·공용 weights 변경·추가 학습·6회 실행·commit/push는 하지 않았습니다.',
            f'정확한 실행·해시·채점 증거: `{RUN}`. 회차별 보고서는 이 폴더의 round_01.md~round_05.md입니다.']
        with (REPORTS/'summary.md').open('x',encoding='utf-8') as stream:stream.write('\n\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','execute','probe','worker','qualify'])
    parser.add_argument('--round',type=int,choices=COUNTS)
    args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='execute':execute()
    elif args.action=='probe':probe()
    else:worker(args.round,args.action=='qualify')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if RUN.exists():write(RUN/f'failure-{os.getpid()}.json',dict(error=repr(error),time=now(),auto_retry=False))
        raise
