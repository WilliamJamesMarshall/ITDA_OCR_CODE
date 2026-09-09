"""Verify the integrated results and publish one consolidated local report."""
import contextlib
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

assessment = read(OUT/'final_assessment.json')
fresh_assessment = read(OUT/'assessment.json')
existing = read(OUT/'final_existing_assessment.json')
for dirname in ('live_386_verified','live_existing_352'):
    for name,digest in read(OUT/dirname/'runtime.json')['code_sha256'].items():
        assert hashlib.sha256((OUT/'pre_clock_source'/Path(name).name).read_bytes()).hexdigest()==digest
labels = read(OUT/'existing_labels.json')
assert hashlib.sha256(Path(labels['source']).read_bytes()).hexdigest() == labels['sha256']
truth = {r['image_id']: r['truth'] for r in labels['rows'] if r['status']=='manual'}
reference = {r['image_id']: r for r in map(json.loads, (OUT/'reference_existing.jsonl').read_text(encoding='utf-8').splitlines())}
reference_meta = read(OUT/'reference_existing_runtime.json')
assert len(reference)==reference_meta['images']==352
for name, digest in reference_meta['code_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
current = {r['image_id']: r for r in existing['rows']}
assert set(current)==set(truth) and len(truth)==341
base_ok = {key for key, value in truth.items() if reference[key]['prediction']==value and not reference[key]['error']}
new_ok = {key for key, row in current.items() if row['correct']}
comparison = {'evaluated':341,'baseline_correct':len(base_ok),'integrated_correct':len(new_ok),
              'gained':sorted(new_ok-base_ok),'lost':sorted(base_ok-new_ok),
              'baseline_cache_hits':reference_meta['cached_calls'], 'baseline_fresh_calls':reference_meta['fresh_calls'],
              'reference_errors':sum(bool(row['error']) for row in reference.values()),
              'reference_timing_is_not_e2e':True}
(OUT/'existing_controlled_comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')

stream = io.StringIO()
with contextlib.redirect_stdout(stream):
    test_result = unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
tests = {'run':test_result.testsRun,'failures':len(test_result.failures),'errors':len(test_result.errors),'passed':test_result.wasSuccessful()}
(OUT/'tests.json').write_text(json.dumps(tests,indent=2),encoding='utf-8')
(OUT/'tests.log').write_text(stream.getvalue(),encoding='utf-8')
assert tests['passed']
smoke = read(OUT/'submission_smoke_release.json')
assert smoke['notebook_unchanged'] and smoke['network_connect_blocked']
for name, digest in smoke['code_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
s = assessment['summary']
actual = s['integrated']
details = assessment['details']['integrated']
regressions = ['003451','003482','003738']
gates = {'386_at_least_284':actual['correct']>=284,
         'three_previous_regressions_fixed':all(details[key]['correct'] for key in regressions),
         'previous_p3_no_lost_correct':not assessment['changes']['previous_p3']['lost'],
         'existing_manual_no_lost_correct':not comparison['lost'],
         'runtime_errors_zero':actual['errors']==existing['summary']['runtime_errors']==comparison['reference_errors']==0}
assert assessment['submission_contract_verified'] and assessment['source_config_weights_images_verified']
replay = read(OUT/'replay.json')['summary']
lines = ['# 날짜 정책 통합 적용 검증 — 2026-09-10', '',
         '기존 통합 변경을 보존·검토하고 평가 오류 ID 정규화, 날짜와 시각의 숫자 결합 방지, 합산 점수 기준의 종료일 선택, 명시적 종료 문맥 우선순위, 간접 제조 문맥의 조기 종료 방지, 겹친 숫자 해석의 날짜 구간 오인 방지를 보강했다. 날짜 정책·출력·문맥 선택·복구와 관련 테스트를 하나의 기능 변경으로 검증했다. 모델·가중치·CPU 스레드 수·기본 OCR 순서는 유지했다.', '',
         '## 1. 추가 수집 이미지 386장', '',
         '| 구성 | 완전일치 | 이미지 처리 구간 | 초기화 포함 | 실행 오류 |',
         '| --- | ---: | ---: | ---: | ---: |']
for key,label in [('baseline','연도 하한 제거 기준군: 이전 실행'),('previous_p3','p3: 이전 실행')]:
    row=s[key]
    lines.append(f'| {label} | {row["correct"]}/386 ({row["correct"]/386*100:.2f}%) | {row["loop_seconds"]:.1f}초 | {row["total_seconds"]:.1f}초 | {row["errors"]} |')
row=fresh_assessment['summary']['integrated']
lines.append(f'| 시각 결합 보강 전 통합안: 새 실측 | {row["correct"]}/386 ({row["correct"]/386*100:.2f}%) | {row["loop_seconds"]:.1f}초 | {row["total_seconds"]:.1f}초 | {row["errors"]} |')
lines.append(f'| 최종 통합안: 전체 분기 재검증 | {actual["correct"]}/386 ({actual["correct"]/386*100:.2f}%) | 최종 E2E 시간 미측정 | 최종 E2E 시간 미측정 | {actual["errors"]} |')
lines += ['', '최종 통합안은 이미지의 실제 전처리·분기·조기 종료·최종 선택을 전부 재실행했다. 동일 모델·설정·전처리 입력 해시의 OCR만 캐시로 재사용하고, 없는 입력은 실제 모델로 판독했다. 정답이나 ID별 예외는 판독에 사용하지 않는다. 이 최종 실행의 벽시계 시간은 새 전체 OCR 속도 측정값이 아니며, 보강 전 실측 시간을 최종 코드의 성능으로 표시하지 않는다.', '',
          '이 결과는 기존 Paddle OCR 자동 파이프라인에 날짜 판독 규칙을 통합한 성능이다. 사용자가 확인한 앞선 시각 판독 384/386건과 11분 미만 기록을 이 모델에서 재현했다는 뜻이 아니다. 외부 시각 모델이나 API는 추가하지 않았다.']
lines += ['', '| 정답 유형 | 통합안 정답 |', '| --- | ---: |']
for kind,row in actual['categories'].items():
    lines.append(f'| {kind} | {row["correct"]}/{row["total"]} |')
change=assessment['changes']['baseline']
lines += ['',f'새 기준 대비 개선 {len(change["gained"])}건, 회귀 {len(change["lost"])}건. 상세 ID·판독·OCR 경로는 final_assessment.json에 보존했다.',
          '', '| 이전 p3 회귀 사례 | 정답 | 통합안 |', '| --- | --- | --- |']
for key in regressions:
    row=details[key]
    lines.append(f'| {key} | {row["expected"]} | {row["prediction"]} |')
row=details['003613']
lines += ['',f'003613의 정답은 {row["expected"]}, 최종 출력은 {row["prediction"]}다. 시각 보강 전에는 03.31 뒤의 01:31을 묶어 2031-01-31로 오인했다. 두 자리 연도와 독립된 HH:MM 시각을 결합하지 않는 일반 규칙 및 정상 날짜 뒤 시각을 보존하는 테스트를 추가했다.']
lines += ['',f'고정 OCR 후처리 재평가는 {replay["correct"]}/386이었다. 이 점수는 전체 OCR 증거를 마지막에 제공하는 계산이며 조기 종료·추가 OCR이 있는 새 전수 실행과 구분한다.', '',
          '## 2. 기존 검증셋 회귀 검사', '',
          f'보강 전 코드로 352장을 새로 실제 판독하고, 보강 후 최종 코드로 동일 입력 OCR 캐시와 필요한 실제 모델 호출을 사용해 전체 분기를 다시 실행했다. 현재 수동 확정 341건만 채점하고 미확정 11건은 제외했다. 최종 통합안 {len(new_ok)}/341, 연도 하한 제거 기준군 {len(base_ok)}/341이다. 개선 {len(comparison["gained"])}건, 회귀 {len(comparison["lost"])}건.', '',
          f'기준군은 같은 이미지·같은 OCR 입력 해시의 기록을 {reference_meta["cached_calls"]}회 재사용하고, 없는 입력만 원래 모델로 {reference_meta["fresh_calls"]}회 판독했다. 실제 분기·조기 종료를 다시 실행한 정확도 대조이며, 캐시 실행 시간은 속도 비교에 사용하지 않는다. 예전 302/341 수치는 다른 시점의 라벨·정책 기록이므로 직접 대체하지 않는다.', '',
          '## 3. 계약 및 무결성 검사', '',
          f'- 단위·계약·평가 검사: {tests["run"]}개 통과.',
          '- 부분 날짜는 누락 필드를 NONE으로 보존하며 조기 종료하지 않는다. 부분 날짜만 남은 경우 기존 조건 아래 타일 복구까지 허용한다.',
          '- 서로 다른 OCR 좌표계의 줄·문맥을 섞지 않고, 같은 영역의 날짜 쌍만 종료일 판단에 사용한다.',
          '- 직렬화 실패를 이미지 단위로 격리하며, 정답이 NONE이어도 실행 실패는 오답으로 집계한다.',
          '- 원본 manual 파일, 기존 기준·p3 결과는 보존했다. 소스·이미지·가중치 해시와 5열 제출 계약을 검증했다.',
          '- Python socket.connect 호출을 실패시키는 검사에서 변경하지 않은 노트북의 Python 셀 실행을 완료했다. OS 전체 네트워크 차단이나 실제 Jupyter 커널 Run All 시험은 아니다.', '',
          '## 4. 통과 기준과 남은 작업', '']
for name,passed in gates.items():
    lines.append(f'- {name}: {"통과" if passed else "미통과"}')
lines += ['', '공식 4-vCPU·500장 환경의 초기화 포함 2,400초 한도 및 1,800초 내부 목표는 아직 검증하지 않았다. 현재 Windows 개발 PC의 단일 실행과 과거 참조 실행으로 일반적인 속도 개선을 확정하지 않는다. 반복 A/B 속도 측정과 독립 블라인드 평가는 남은 검증이다.', '',
          '구현·로컬 회귀 검사에 미통과 항목이 있으면 운영 채택 완료로 간주하지 않는다. 파일별로 같은 작업을 나누지 않고 기능 통합 → 정확도·회귀 검사 → 제출 환경 검증으로 구분한다.', '',
          '## 5. 기록', '',
          'artifacts/date-policy-integration-20260910의 live_386_verified와 live_existing_352는 최종 보강 전 실측이다. release_386_cache와 release_existing_cache는 최종 코드의 전체 분기 재검증이며 final_assessment.json과 final_existing_assessment.json이 최종 채점 기록이다. final_386_cache와 final_existing_cache는 중간 보강 단계의 기록이다. pre_clock_source와 clock_only_source는 중간 소스 해시 검증용 보존본이다. live_386 및 live_386_final은 중단 기록으로 최종 성능에서 제외했다. 원본 정답 및 기존 기준 결과를 덮어쓰지 않았다.', '']
(ROOT/'docs/date-policy-validation-20260910.md').write_text('\n'.join(lines),encoding='utf-8')
(OUT/'completion_checks.json').write_text(json.dumps({'tests':tests,'gates':gates,'remaining':['official_environment_benchmark','repeated_speed_comparison','independent_holdout']},indent=2),encoding='utf-8')
print(json.dumps({'integrated':actual,'existing':comparison,'gates':gates,'tests':tests},ensure_ascii=False,indent=2))
