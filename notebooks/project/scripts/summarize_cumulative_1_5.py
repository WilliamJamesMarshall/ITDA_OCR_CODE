"""Verify completed cumulative training and report it without launching evaluation."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path
from scripts.audit_cumulative_1_5 import read, sha, write_new
from scripts import ocr_annotations as ann
from scripts.frozen_batch_norm import validation_gate
from scripts.grouped_rounds import embedded_source_manifest, model_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--record-code-review', action='store_true')
    args = parser.parse_args()
    run = args.run.resolve()
    if args.record_code_review:
        log = run / 'unit-tests-final.log'
        text = log.read_text(encoding='utf-8-sig', errors='replace')
        assert 'Ran 584 tests' in text and text.rstrip().endswith('OK')
        embedded_source_manifest(ann.ROOT)
        old = read(run / 'code-review/round4-selector-replay-before.json')['snapshots']
        new = read(run / 'code-review/round4-selector-final.json')['snapshots']
        assert len(old) == len(new) == 26
        changes = []
        for before, after in zip(old, new):
            assert (before['image_id'], before['trace_line']) == (after['image_id'], after['trace_line'])
            if before['output'] != after['output']:
                assert after['image_id'] == 'AMLT000953' and after['output'] == '2021-02-05'
                changes.append(dict(image_id=after['image_id'], trace_line=after['trace_line'], before=before['output'], after=after['output']))
        assert len(changes) == 12
        paths = list((ann.ROOT / 'notebooks/project/src').glob('*.py'))
        paths += [ann.ROOT / 'predict.ipynb', log,
                  ann.ROOT / 'notebooks/project/tests/test_cumulative_date_roles.py',
                  ann.ROOT / 'notebooks/project/tests/test_cumulative_training.py',
                  run / 'code-review/round4-selector-final.json']
        write_new(run / 'code-review/final-code-proof.json', dict(unit_tests=584,
            scope='Unit tests and independent saved selector snapshots only. No original-image OCR test.',
            changed_snapshots=changes, files={str(p): sha(p) for p in paths}))
        print('Final code proof recorded; training/evaluation was not launched.')
        return
    release_path = run / 'release/release.json'
    release = read(release_path)
    for path, digest in release['protected_files'].items():
        assert sha(path) == digest, path
    runtime = read(run / 'training-run/runtime.json')
    supervisor = read(run / 'supervisor-result.json')
    memory_observation = read(run / 'trainer-memory-observation.json')
    assert memory_observation['trainer_pid'] == runtime['pid']
    assert memory_observation['launcher_pid'] == supervisor['pid']
    assert runtime['status'] == 'completed' and supervisor['status'] == 'completed'
    assert supervisor['exit_code'] == 0
    assert runtime['epochs_completed'] == 1 and runtime['optimizer_steps'] == math.ceil(release['scope']['optimizer_crops']/8)
    assert runtime['cpu_affinity'] == [0,1,2,3] and runtime['threads'] == 4
    assert runtime['whole_image_evaluation'] == 'held_until_separate_user_instruction'
    assert not runtime['shared_weights_changed'] and runtime['epoch_zero_reproduced']
    before = read(run / 'training-run/validation_000.json')
    after = read(run / 'training-run/validation_001.json')
    passed = validation_gate(after['metrics'], before['metrics'])
    assert passed == runtime['validation_gate_passed']
    assert before['frozen_bn']['statistics_sha256'] == after['frozen_bn']['statistics_sha256']
    selected = read(run / 'training-run/selected_checkpoint.json')
    assert selected['epoch'] == (1 if passed else 0)
    preservation = read(run.parent / 'answer-correction-20260915-v1/preservation.after.json')['protected_hashes']
    assert all(sha(p) == digest for p, digest in preservation.items())
    assert model_lock(ann.ROOT / 'weights/paddle') == model_lock(run / 'starting_bundle')
    embedded_source_manifest(ann.ROOT)
    code_proof = read(run / 'code-review/final-code-proof.json')
    assert all(sha(p) == digest for p, digest in code_proof['files'].items())
    pool = read(release['pool'])
    samples = pool['samples']
    train = [s for s in samples if s['role'] == 'optimizer_train']
    valid = [s for s in samples if s['role'] == 'inner_validation']
    sampler = read(run / 'training-run/sampler-evidence.json')
    assert sampler['unique_indices'] == len(train) == sum(sampler['batch_sizes']) == 3316
    assert Counter(sampler['batch_sizes']) == {8: 414, 4: 1}
    assert len(valid) == 25
    checkpoints = {p.name: dict(path=str(p), sha256=sha(p)) for p in (run / 'training-run').glob('epoch_*.pdparams')}
    bundle = Path(runtime['candidate_bundle']) if passed else None
    if bundle:
        assert all((bundle / 'korean_PP-OCRv5_mobile_rec' / name).is_file() for name in ('inference.json','inference.pdiparams','inference.yml'))
    summary = dict(status='training_completed_tests_held', epochs=1, optimizer_steps=runtime['optimizer_steps'],
        optimizer_crops=len(train), validation_crops=len(valid), optimizer_originals=len({s['image_id'] for s in train}),
        validation_originals=len({s['image_id'] for s in valid}),
        round_crop_counts=dict(Counter(pool['admitted'][s['image_id']]['round'] for s in train)),
        baseline_metrics=before['metrics'], candidate_metrics=after['metrics'], validation_gate_passed=passed,
        selected_epoch=selected['epoch'], checkpoints=checkpoints,
        candidate_bundle=str(bundle) if bundle else None, candidate_model=model_lock(bundle) if bundle else None,
        training_and_validation_seconds=runtime['training_and_validation_seconds'],
        trainer_total_seconds=runtime['total_process_seconds'], supervisor_total_seconds=supervisor['total_process_seconds'],
        launcher_peak_working_set_bytes=max(s['peak_working_set_bytes'] for s in supervisor['samples']),
        observed_trainer_peak_working_set_bytes=memory_observation['observed_peak_working_set_bytes'],
        final_whole_run_peak_verified=False,
        memory_scope=memory_observation['scope'],
        cpus=runtime['cpu_affinity'], threads=runtime['threads'], frozen_bn=after['frozen_bn'],
        preserved_historical_files=len(preservation), shared_weights_changed=False,
        whole_image_tests='held_until_separate_user_instruction', model_adoption='awaiting_future_user_decision',
        source_files={str(p):sha(p) for p in [release_path, run / 'instruction.json', run / 'release/config.yml',
            Path(release['pool']), run / 'training-run/runtime.json', run / 'supervisor-result.json',
            run / 'training-run/validation_000.json', run / 'training-run/validation_001.json',
            run / 'training-run/sampler-evidence.json', run / 'trainer-memory-observation.json',
            ann.ROOT / 'notebooks/project/src/date_extraction.py', ann.ROOT / 'predict.ipynb', run / 'unit-tests-final.log',
            run / 'code-review/final-code-proof.json', run / 'shared-lock-attached.json', run / 'shared-lock-released.json']})
    write_new(run / 'training-summary.json', summary)
    b, a = before['metrics'], after['metrics']
    report = ann.ROOT / 'notebooks/docs/training/cumulative_1_5_20260915/training_report.md'
    body = f'''# 1~5회 누적 학습 결과

전체 4단계 중 현재 3단계이며, 이번 대상은 4회차 및 5회차입니다. 1~5회 누적 승인 crop의 1 epoch 학습을 완료했습니다. **1~5회 전체 이미지 테스트는 별도 지시까지 보류 중입니다.**

## 실제 실행 결과

- optimizer 원본 2,041장, crop 3,316개, 415 steps. 내부 검증은 기존 24개 원본의 25 crop입니다.
- 회차별 optimizer crop: 201 / 577 / 571 / 892 / 1,075.
- CPU 0–3·4스레드, batch 8, LR 5e-6, Adam, seed 20260911, BN 통계 고정, 실시간 증강 없음. 8개 batch 414회와 잔여 4개 batch 1회를 포함했습니다. 실제 실행 순서는 sampler가 섞으므로 잔여 batch가 시간상 마지막이라는 뜻은 아닙니다.
- 학습·내부 검증: {runtime['training_and_validation_seconds']:.3f}초({runtime['training_and_validation_seconds']/60:.1f}분).
- trainer 전체(준비/검증 및 수행된 export 포함): {runtime['total_process_seconds']:.3f}초.
- 외부 supervisor 전체: {supervisor['total_process_seconds']:.3f}초.
- 학습 중 직접 관측한 trainer 최대 working set: {summary['observed_trainer_peak_working_set_bytes']/1024**3:.2f}GiB. 종료 직전까지의 최종 최대값이나 전체 프로세스 트리 합계는 미확정입니다.
- 자동 supervisor 메모리 표본은 실제 학습기 PID 3376이 아니라 virtualenv 실행용 부모 PID 8120을 추적한 오류가 있습니다. 부모 최대 {summary['launcher_peak_working_set_bytes']} bytes를 학습 메모리로 사용하지 않았습니다. 원자료를 보존하고 `trainer-memory-observation.json`에 별도 관측 근거를 기록했습니다.

## 내부 crop 검증

| 지표 | 시작 모델 | 1 epoch 후보 |
|---|---:|---:|
| 연·월·일 정답 필드 | {b['field_correct']}/{b['field_total']} | {a['field_correct']}/{a['field_total']} |
| 문자열 완전 일치 | {b['exact_match_count']}/25 | {a['exact_match_count']}/25 |
| 문자 오류율(CER) | {b['micro_cer']:.4%} | {a['micro_cer']:.4%} |
| 숫자만 비교한 문자열 완전 일치 | {b['digit_metrics']['exact_match_count']}/25 | {a['digit_metrics']['exact_match_count']}/25 |

내부 비퇴행 검증: **{'통과' if passed else '미통과'}**. 내부 선정 epoch는 {selected['epoch']}입니다. {'후보 추론 bundle을 별도로 export했습니다.' if passed else '1 epoch checkpoint는 보존했지만 내부 비퇴행 조건을 충족하지 못해 후보 export와 추가 epoch를 진행하지 않았습니다.'}

이 검증은 1·3회에 속한 25 crop만 다룹니다. 4·5회 성능이나 2,110장 전체 정확도, 목표 95% 달성을 확인한 결과가 아닙니다. 모델은 아직 채택되지 않았습니다.

### 이번 내부 검증에서 확인한 변화

저장된 두 validation JSON의 예측을 학습 당시 고정된 PolicyMetric으로 항목별 비교했습니다. 추가 OCR은 수행하지 않았습니다.

- AMLC000108: `25.10.24)` → `25-10-241`. 승인 날짜는 2025-10-24이며, 끝에 붙은 숫자 때문에 내부 필드 득점이 1/3 → 0/3으로 감소했습니다.
- AMLC000421: `26.07.17` → `26.07:17`. 승인 날짜는 2026-07-17이며, 구분자 변화로 내부 필드 득점이 1/3 → 0/3으로 감소했습니다.
- AMLC000051·000120·000176은 불필요한 끝 문자 제거로 문자열 완전일치가 개선됐지만, 기존 날짜 필드 득점이 이미 3/3이어서 필드 점수는 늘지 않았습니다.
- AMLC000669는 불필요한 끝 점이 제거됐지만 과거 전사의 앞 `-`와 여전히 다르며, 날짜 필드 득점은 3/3으로 같습니다.

AMLC000421의 과거 검증 전사는 `2.17.17`, 별도 승인 날짜 필드 목표는 2026-07-17입니다. 기존 승인 증거와 epoch-zero 비교를 보존하기 위해 어느 쪽도 자동 정정하지 않았습니다. 따라서 문자열 성적과 날짜 필드 성적이 서로 다른 목표 표현을 쓰는 한계도 있습니다. 향후 검토 대상이며 이번 검증 실패를 사후 정답 변경으로 뒤집지 않았습니다.

관측된 두 퇴행은 숫자/구분자 인식과 날짜 해석의 결합 문제입니다. 더 많은 학습만으로 개선된다고 단정할 수 없습니다. 후속 작업에서는 검증 원본을 optimizer에 편입하지 않고, 승인된 학습 crop의 유사 오류·전사 품질·날짜 파서 경계를 검토해야 합니다. 추가 epoch나 규칙 완화는 이번 실행에서 하지 않았습니다.

이번 학습은 한국어 인식기가 승인 crop의 문자 전사를 학습한 것입니다. 날짜 역할·순서 선정은 별도 코드가 담당합니다. 표제 인식 개선을 기대할 수 있지만 실제 효과는 미검증입니다. 검출기·영어 보조 인식기는 학습하지 않았습니다.

## 데이터·코드·보존

2,110장 전체는 준비 범위이며 모두 optimizer에 들어간 것은 아닙니다. 내부 검증 24장, 미해결 검증 연결/역할 충돌 28장, 적합 crop가 없는 17장은 optimizer에서 제외했습니다. 원본 부재나 과거 22건 누락을 이유로 제외하지 않았습니다. 저장 증강 1,106장은 사용하지 않았습니다. 파일 SHA 그룹을 상품 독립성 증거로 사용하지 않았습니다.

881~1161 정답 이동과 AMLC001117=2021-06-26 정정을 final-date overlay로 반영했습니다. 원본 이미지·과거 승인 주석·crop 전사는 임의 수정하지 않았습니다. 기존 4회 저장 출력의 최신 정답 재채점은 973/1,182필드(82.32%), 완전 날짜 305/394이며 새 OCR 시험이 아닙니다. 5회 최초 결과는 그대로입니다.

코드에서는 일본어 제조일 역할, 부정 역할의 부분 날짜 철회, 기울어진 두 날짜/두 표제 블록 연결을 수정했습니다. AMLC000911의 저장 selector 입력 12개에서 잘못 고른 제조일 대신 2021-02-05를 선택했습니다. 단위 검사 584개 통과 및 Notebook 내장 소스 동기화를 확인했습니다. 회복 일정·OCR 인식 결과까지 포함한 실제 정확도와 시간은 아직 재평가하지 않았습니다. 숫자/표제를 전혀 읽지 못하는 사례는 선택 규칙만으로 해결했다고 주장하지 않습니다.

과거 보호 파일 {len(preservation)}개 SHA와 기본 weights 불변을 확인했습니다. 학습 중에는 고정 사본을 사용했고 병행 코드 수정은 저장소 작업 브랜치에 남겼습니다. 공용 weights 교체, main 반영, 커밋·push는 하지 않았습니다. v1은 optimizer 전 준비 수정 이력으로 보존했고 실제 학습은 v2 한 작업뿐입니다.

## 산출물과 다음 관문

- 실행 폴더: `{run}`
- 학습 release SHA: `{sha(release_path)}`
- 실제 실행 증거: `training-run/runtime.json`, `supervisor-result.json`, `training-summary.json`.
- checkpoint: `training-run/epoch_000.pdparams`, `training-run/epoch_001.pdparams`.
- 후보 bundle: `{str(bundle) if bundle else '내부 검증 미통과로 생성하지 않음'}`.
- 소스·목록·모델·config·승인 원문 SHA는 `release/release.json`과 `training-summary.json`에 있습니다.
- 구체적인 제외 사유·학습 시작 기록은 같은 저장소 폴더의 `start_report.md`에 있습니다.

별도 테스트 지시 전에는 새 원본 추론·5개 회차 결과보고서·종합 평가 점수를 생성하지 않습니다. 보류 해제 후 고정 개선 코드와 허용된 후보로 평가하고, 결과를 본 사용자가 채택 여부를 결정해야 합니다. 이후에만 승인한 코드·모델·보고서를 main 반영 대상으로 준비합니다. 향후 2,110장 점수는 누적 개발 성적이지 독립 최종 성적이 아닙니다.
'''
    with report.open('x', encoding='utf-8') as stream:
        stream.write(body)
    print(json.dumps(dict(report=str(report), summary=str(run / 'training-summary.json'), validation_gate_passed=passed), ensure_ascii=False))


if __name__ == '__main__':
    main()
