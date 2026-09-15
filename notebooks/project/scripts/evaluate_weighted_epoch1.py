"""Evaluate the approved original-weighted epoch 1, preserving all prior results."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import evaluate_cumulative_epoch1 as evaluation

evaluation.TRAIN=evaluation.BASE/'cumulative-1-5-original-weighted-20260915-v3'
evaluation.RUN=evaluation.BASE/'cumulative-1-5-original-weighted-epoch1-eval-20260915-v1'
evaluation.REPORTS=evaluation.ROOT/'notebooks/docs/training/cumulative_weighted_originals_20260915/epoch1_evaluation'
evaluation.LABELS_SOURCE=evaluation.BASE/'cumulative-1-5-epoch1-eval-20260915-v1/labels.csv'
evaluation.WORKER_SCRIPT='evaluate_weighted_epoch1.py'
evaluation.INSTRUCTION='학습이 종료되었으므로 1회~5회 전체 이미지 테스트를 실행한다. 1회는 단독으로 실행한다. 2회와 3회, 4회와 5회를 동시에 묶어서 실행한다.'


def weighted_training_evidence():
    train=evaluation.TRAIN;read=evaluation.read;sha=evaluation.digest
    summary=read(train/'training-summary.json')
    release=read(train/'release/release.json')
    evaluation.check_files(release['protected_files'])
    assert sha(train/'release/release.json')==summary['release_sha256']=='614215650d52b5b3445e685afcedbbadf897192737663322fede638afe2cf25a'
    assert read(train/'postprocess-status.json')['status']=='report_completed_tests_held'
    state=read(train/'training-run/runtime.json')
    supervisor=read(train/'supervisor-result.json')
    assert state['status']=='completed' and supervisor['status']=='completed' and supervisor['exit_code']==0
    assert state['optimizer_steps']==415 and state['epochs_completed']==1
    assert summary['optimizer_crops']==3316 and summary['optimizer_originals']==2041
    assert not summary['validation_gate_passed'] and not state['validation_gate_passed']
    assert read(train/'training-run/weighted-epoch-audit.json')['unique_crops']==3316
    assert sha(train/'training-run/weighted-loss-batches.jsonl')==summary['weighted_batch_evidence_sha256']
    checkpoint=summary['checkpoint']
    assert sha(Path(checkpoint['path']))==checkpoint['sha256']=='aa4666d0612c2fd45e0208b42a30e9ccf9c5530d7ee1463d32e636ee3aaa9e35'
    prior=evaluation.BASE/'cumulative-1-5-epoch1-eval-20260915-v1'
    old_release=read(prior/'release.json')
    evaluation.check_files(old_release['protected_files'])
    # Inference implementation is unchanged from the previous full evaluation.
    now=evaluation.source_lock(evaluation.ROOT)
    keys=[k for k in old_release['code'] if k=='predict.ipynb' or k.startswith('notebooks/project/src/')]
    assert all(now[k]==old_release['code'][k] for k in keys),'Inference code changed; report before executing'
    return checkpoint


evaluation.training_evidence=weighted_training_evidence


def finish_reports():
    from scripts import analyze_cumulative_epoch1 as analysis
    from scripts import finalize_cumulative_epoch1_reports as finalizer
    from scripts.evaluate_pipeline import read_labels,read_predictions,score_predictions
    evaluation.write(evaluation.RUN/'status.json',dict(status='postprocessing',updated_at=evaluation.now()))
    comparison=[]
    for number in evaluation.COUNTS:
        analysis.analyze(number)
        folder=evaluation.RUN/'evaluation'/f'round_{number:02d}'
        report=evaluation.read(folder/'report.json')
        ids=[r['image_id'] for r in evaluation.csv_read(evaluation.RUN/'control'/f'test_round_{number:02d}.csv')]
        labels=evaluation.labels_for(evaluation.RUN/'control',ids,read_labels(evaluation.RUN/'labels.csv'))
        old=evaluation.BASE/'cumulative-1-5-epoch1-eval-20260915-v1/evaluation'/f'round_{number:02d}'
        runtime=evaluation.read(old/'runtime.json')
        before=score_predictions(labels,read_predictions(old/'submission.csv'),runtime.get('failures',[]),expected_ids=ids)
        after=report['metrics'];changes=[]
        for image_id in ids:
            a=before['field_results'][image_id];b=after['field_results'][image_id]
            gained=[f for f in a if not a[f] and b[f]];lost=[f for f in a if a[f] and not b[f]]
            if gained or lost:changes.append(dict(image_id=image_id,gained=gained,lost=lost))
        value=dict(round=number,previous_fields=before['field_correct'],current_fields=after['field_correct'],
            field_total=3*evaluation.COUNTS[number],gains=sum(len(c['gained']) for c in changes),
            losses=sum(len(c['lost']) for c in changes),changes=changes,previous_output_sha256=evaluation.digest(old/'submission.csv'))
        evaluation.write(folder/'previous_epoch_comparison.json',value);comparison.append(value)
        with (evaluation.REPORTS/f'round_{number:02d}.md').open('a',encoding='utf-8') as stream:
            stream.write(f"\n## 직전 비가중 누적 후보 대비\n\n{value['previous_fields']}/{value['field_total']} → {value['current_fields']}/{value['field_total']}. 획득 {value['gains']}필드, 손실 {value['losses']}필드. 동일한 최신 정답으로 비교했습니다.\n")
    with (evaluation.REPORTS/'summary.md').open('a',encoding='utf-8') as stream:
        stream.write('\n## 직전 비가중 누적 후보 대비\n\n| 회차 | 직전 후보 필드 | 이번 가중 후보 필드 | 획득 | 손실 |\n|---|---:|---:|---:|---:|\n')
        for v in comparison:stream.write(f"| {v['round']} | {v['previous_fields']} | {v['current_fields']} | {v['gains']} | {v['losses']} |\n")
        stream.write('\n직전 전체 평가와 추론 소스·노트북은 같은 해시입니다. 학습은 회차/원본 가중치 외에도 NRTR crop별 평균·잔여 batch 집계·실제 crop 누락 방지 보완이 포함되어, 가중치 단독 효과로 해석하지 않습니다.\n')
    evaluation.write(evaluation.RUN/'previous_epoch_comparison.json',comparison)
    finalizer.main()
    evaluation.write(evaluation.RUN/'status.json',dict(status='completed_reports_verified',updated_at=evaluation.now(),model_adopted=False))


if __name__=='__main__':
    try:
        evaluation.main()
        if sys.argv[1]=='execute':finish_reports()
    except BaseException as error:
        if evaluation.RUN.exists():
            evaluation.write(evaluation.RUN/'weighted-evaluation-failure.json',dict(error=repr(error),time=evaluation.now(),auto_retry=False))
        raise
