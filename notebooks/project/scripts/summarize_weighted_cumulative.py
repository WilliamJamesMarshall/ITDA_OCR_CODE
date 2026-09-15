"""Audit a completed weighted epoch and write its report; never launch tests."""
import argparse
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args();run=args.run.resolve()
    from scripts.frozen_batch_norm import validation_gate
    from scripts.grouped_rounds import model_lock
    release=read(run/'release/release.json')
    state=read(run/'training-run/runtime.json')
    supervisor=read(run/'supervisor-result.json')
    assert state['status']=='completed' and supervisor['status']=='completed' and supervisor['exit_code']==0
    assert state['optimizer_steps']==415 and state['epochs_completed']==1 and state['epoch_zero_reproduced']
    assert state['cpu_affinity']==[0,1,2,3] and state['threads']==4
    assert state['whole_image_evaluation']=='held_until_separate_user_instruction' and not state['shared_weights_changed']
    for path,digest in release['protected_files'].items():
        assert sha(path)==digest,path
    pool=read(release['pool'])
    for original in pool['admitted'].values():
        assert sha(original['original_path'])==original['original_sha256']
        assert sha(original['annotation_path'])==original['annotation_sha256']
    for sample in pool['samples']:
        assert sha(sample['crop_path'])==sample['crop_sha256']
        assert sample['role']==pool['group_roles'][sample['group_id']]
    root=Path(os.environ.get('ITDA_ASSET_ROOT',Path(__file__).resolve().parents[3])).resolve()
    assert model_lock(root/'weights/paddle')==model_lock(Path(release['bundle']))
    manifest=read(release['weight_manifest'])
    seen=set();sizes=Counter();rounds=Counter();totals=Counter();weighted_ctc=Counter();weighted_nrtr=Counter()
    batch_path=run/'training-run/weighted-loss-batches.jsonl'
    for line in batch_path.read_text(encoding='utf-8').splitlines():
        batch=json.loads(line)
        assert batch['divisor']==8
        ids=batch['indices'];assert not seen.intersection(ids) and len(ids)==len(set(ids))
        assert len(ids)==len(batch['scaled_weights'])==len(batch['ctc'])==len(batch['nrtr'])
        seen.update(ids);sizes[len(ids)]+=1
        for i,w,c,n in zip(ids,batch['scaled_weights'],batch['ctc'],batch['nrtr']):
            entry=manifest['entries'][i];r=entry['round'];q=entry['coefficient']
            assert math.isclose(w,entry['scaled_weight'],abs_tol=1e-12) and math.isfinite(c+n)
            rounds[r]+=1;totals[r]+=q;weighted_ctc[r]+=q*c;weighted_nrtr[r]+=q*n
    assert seen==set(range(3316)) and sizes=={8:414,4:1}
    for r,n in [(1,216),(2,500),(3,500),(4,394),(5,500)]:
        assert math.isclose(totals[r],n/2110,abs_tol=1e-10)
    consumed=read(run/'training-run/weighted-epoch-audit.json')
    assert consumed['unique_crops']==3316
    before=read(run/'training-run/validation_000.json')
    after=read(run/'training-run/validation_001.json')
    passed=validation_gate(after['metrics'],before['metrics'])
    assert passed==state['validation_gate_passed']
    assert before['frozen_bn']['statistics_sha256']==after['frozen_bn']['statistics_sha256']
    selected=read(run/'training-run/selected_checkpoint.json')
    assert selected['epoch']==(1 if passed else 0)
    if passed:
        exported=Path(state['candidate_bundle'])/'korean_PP-OCRv5_mobile_rec'
        assert all((exported/name).is_file() for name in ('inference.json','inference.pdiparams','inference.yml'))
    samples=supervisor['samples']
    trainer_samples=[s for s in samples if s.get('scope')=='trainer_only_not_process_tree' and s['pid']==state['pid']]
    tree_samples=[s for s in samples if s.get('scope')=='launcher_and_descendants_sampled_tree']
    assert trainer_samples and tree_samples
    memory=dict(trainer_sampled_working_set_max=max(s['working_set_bytes'] for s in trainer_samples),
        trainer_observed_peak_working_set_max=max(s['peak_working_set_bytes'] for s in trainer_samples),
        process_tree_sampled_working_set_max=max(s['working_set_bytes'] for s in tree_samples),
        scope='Sampled maxima, not guaranteed lifetime simultaneous tree maximum')
    checkpoint=run/'training-run/epoch_001.pdparams'
    summary=dict(status='training_completed_tests_held',release_sha256=sha(run/'release/release.json'),
        optimizer_steps=415,optimizer_crops=3316,optimizer_originals=2041,round_crop_counts=rounds,
        round_coefficient_sums=totals,round_online_weighted_ctc=weighted_ctc,round_online_weighted_nrtr=weighted_nrtr,
        baseline_metrics=before['metrics'],candidate_metrics=after['metrics'],validation_gate_passed=passed,
        checkpoint=dict(path=str(checkpoint),sha256=sha(checkpoint)),memory=memory,
        training_validation_seconds=state['training_and_validation_seconds'],
        trainer_total_seconds=state['total_process_seconds'],supervisor_total_seconds=supervisor['total_process_seconds'],
        weighted_batch_evidence_sha256=sha(batch_path),candidate_bundle=state.get('candidate_bundle'),
        shared_weights_changed=False,whole_image_tests=False,model_adopted=False)
    with (run/'training-summary.json').open('x',encoding='utf-8') as stream:json.dump(summary,stream,ensure_ascii=False,indent=2)
    a,b=before['metrics'],after['metrics']
    doc=root/'notebooks/docs/training/cumulative_weighted_originals_20260915/training_report.md'
    lines=['# 원본 수 비례 1~5회 누적 학습 결과','',
        f"1 epoch·415 steps를 완료했다. 내부 비퇴행 검증: **{'통과' if passed else '미통과'}**. 전체 이미지 테스트와 모델 채택은 하지 않았다.",'',
        '## 학습·입력 검증','',
        '- 승인 원본 2,041장의 crop 3,316개를 각각 한 번 사용했다. 실제 소비 인덱스·가중치 로그를 사후 대조했다.',
        '- batch 8×414회 + batch 4×1회. 모든 batch의 가중 손실 고정 분모는 8이다.',
        '- 회차 내 원본별 평균, 원본 내 crop별 평균, 회차 비중은 대상 원본 수/2,110이다.',
        '- 원본·승인 주석·crop·그룹 역할·고정 코드·runtime·config·공용 모델 해시 불변 확인.',
        '- 학습 자료와 내부 검증 역할은 변경하지 않았다. 저장 증강 제외·실시간 증강 없음 유지.','',
        '| 회차 | crop 수 | 실제 계수 합 |','|---|---:|---:|']
    for r in range(1,6):lines.append(f'| {r} | {rounds[r]} | {100*totals[r]:.6f}% |')
    lines+=['','## 내부 검증','',
        '| 지표 | 시작 모델 | 새 후보 |','|---|---:|---:|',
        f"| 날짜 필드 | {a['field_correct']}/{a['field_total']} | {b['field_correct']}/{b['field_total']} |",
        f"| 문자열 완전 일치 | {a['exact_match_count']}/25 | {b['exact_match_count']}/25 |",
        f"| CER | {100*a['micro_cer']:.4f}% | {100*b['micro_cer']:.4f}% |",'',
        '내부 25 crop는 1·3회만 포함한다. 2,110장 전체 정확도 또는 95% 달성 근거가 아니다. 학습 손실은 학습 중 변하는 모델의 관측값이며 고정 checkpoint의 회차별 성적이 아니다.',
        f"내부 선정 epoch는 {selected['epoch']}이며, {'별도 후보를 export했다' if passed else '후보 checkpoint만 보존하고 export·추가 epoch는 하지 않았다'}. 공용 모델은 기존 모델을 유지한다.",'',
        '## 실제 시간·메모리','',
        f"- 학습·내부 검증: {state['training_and_validation_seconds']:.3f}초 ({state['training_and_validation_seconds']/60:.1f}분).",
        f"- trainer 전체: {state['total_process_seconds']:.3f}초. supervisor 전체: {supervisor['total_process_seconds']:.3f}초.",
        f"- 관측 trainer peak working set: {memory['trainer_observed_peak_working_set_max']/2**30:.2f}GiB.",
        f"- 동시 프로세스 트리 표본 working set 최대: {memory['process_tree_sampled_working_set_max']/2**30:.2f}GiB. 미관측 순간의 최대값을 보장하지 않는다.",
        '- CPU 0~3·4스레드, 기존 로컬 온라인 승인 범위. 외부 업로드·관리자 창·방화벽 변경 없음.','',
        '## 이력과 다음 관문','',
        'v1/v2는 optimizer 이전 준비 사본이고 v3가 유일한 실제 학습이다. [로더 보완](loader_findings.md)의 NRTR 특수 토큰 공간·레코드 구분자 처리도 반영됐으므로 모든 변화를 회차 가중치 단독 효과로 해석하지 않는다.',
        '기존 1~5회 결과, 직전 퇴행 후보, 원본 정답과 승인 기록을 덮어쓰지 않았다. 전체 이미지 테스트·6회·모델 채택·단계 종료·commit/push는 실행하지 않았다.',
        '후속 전수 테스트는 별도 지시가 필요하며, 그 결과도 누적 개발 성적이지 독립 최종 성적이 아니다.','',
        '## 파일 증거','',f'- 실행 폴더: `{run}`.',
        f"- release SHA: `{summary['release_sha256']}`.",f'- epoch1 checkpoint SHA: `{sha(checkpoint)}`.',
        '- `training-run/runtime.json`, `supervisor-result.json`, `training-run/weighted-loss-batches.jsonl`, `training-run/weighted-epoch-audit.json`, `training-summary.json`에 원증거를 보존했다.']
    with doc.open('x',encoding='utf-8') as stream:stream.write('\n'.join(lines)+'\n')
    print(json.dumps(dict(status=summary['status'],field_before=a['field_correct'],field_after=b['field_correct'],
        validation_gate_passed=passed,report=str(doc)),ensure_ascii=True))


if __name__=='__main__':main()
