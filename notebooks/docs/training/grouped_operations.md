# 원본 6회·4단계 실행 운영

정본: [grouped_6_rounds.md](../protocol/grouped_6_rounds.md).
현재 작업 공간은 `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1`이며 순서는 1 → (2·3) → (4·5) → 6회다.
테스트·학습·누적 평가의 원본 공급원은 `C:/ITDA_OCR_CODE/학습대상데이터`다.
회차 장수는 216/500/500/394/500/500, 500장 미만은 평균 3.2초/장 이하,
500장은 전체 1,600초 이하, 강제 종료는 노트북 전체 2,400초다.
이 기준은 새 실행에 적용하고 아래 v14/v15 등 과거 결과와 판정은 보존한다.
[이관·검증 기록](original_6_rounds_migration_20260914.md)에 실제 준비 결과와 보존 검증을 정리했다.
2026-09-14 정확도 정정: 이후 주 지표는 [date-fields-v1](date_field_accuracy_20260914.md)의
연/월/일 필드 정답 수 / 3N이다. 아래 보존된 v14의 380/500·332/500은 당시 전체 날짜 보조 성적이며,
동일 CSV를 새 기준으로 계산하면 1166/1500(77.7333%)·1039/1500(69.2667%)다. 기존 보고서 해시는 바꾸지 않는다.
2단계 구조 개선 개발·혼합 CPU 계측: [개발 기록](performance_development_20260913.md).

## 현재 개발 후보와 보존된 결과

2026-09-15 최신 사용자 결정: [재학습 인식기 채택·2단계 종료](../development/adopted_recognizer_20260915.md).
2·3회를 성능 기준 통과가 아닌 `explicit_user_adoption`으로 종료하고 4·5회 준비로 전환한다.
`status`는 실제 완료 근거 검증 후 3단계로 표시하며 미달·퇴행 판정을 보존한다.
4·5회 최초 테스트·환경 검증은 별도이며 이번 모델 채택이 그 실행 승인은 아니다.
아래 기록은 이 결정 이전의 역사적 상태로 보존한다.

최신 준비 경로와 실행 관문은 [2·3단계 준비·인계](stage2_stage3_preparation_20260914.md)를 먼저 읽는다.
전체 논문 계획 후보는 구현·패키징 단계이며 아직 테스트/학습하지 않았다. 준비는 실행 승인이나 단계 완료가 아니다.
`paper-ocr-20260914/full-01`은 2회 495/500 기본 처리 후 실패, 3회 1050/1500(70%)·1545.577초다.
후속 `full-02`는 2회 101장·3회 116장 부분 결과에서 중단됐으며 최종 CSV/runtime이 없다.
이 기록을 완결된 500장 성적이나 새 전체 계획 후보의 검증 결과로 사용하지 않는다.
[논문 1차 결과](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/paper-ocr-20260914/full-01/paper-summary.md)의
2회 0점은 최종 제출 실패 처리이며 처리된 모든 내용이 실제 오인식이라는 뜻은 아니다.

보존 기준 v15(2026-09-14)는 필드 기준 변경·부분 출력 수정 후 온라인으로 각각 500장을 완료했다.
2회 1192/1500(79.4667%)·1545.988초, 3회 1064/1500(70.9333%)·1545.213초다.
동일 기준 v14 대비 +26/+25 필드지만 95% 미달, 기존 필드 손실 5/3개로 공용 반영·단계 승격하지 않았다.
[v15 보존 결과](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/retest-stage2-field-accuracy-online-20260914-v15/summary.md)와
[v15 남은 문제](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/retest-stage2-field-accuracy-online-20260914-v15/findings.md)를 먼저 읽는다.

더 이전 2·3회 개발 재시험(2026-09-14, v14)은 사용자 지시로 수정 후 온라인 실행했다.
각 500장 완료, 380/500·1,545.603초 및 332/500·1,544.792초다. 이번 1,600초 목표는 충족했지만
95% 미달이며 v12 대비 개선/퇴행은 각각 7/5, 5/8건으로 미채택이다. 학습·공용 코드/가중치 반영·단계 승격은 하지 않았다.
[v14 결과·오답·보존 감사](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/retest-stage2-online-1600-20260914-v14/summary.md),
[수정 후 확인된 회귀](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/retest-stage2-online-1600-20260914-v14/case_review.md),
[이전 v12 결과](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/retest-stage2-online-20260914-v12/summary.md)와
[이번 온라인 실행 예외](online_stage2_exception_20260914.md)를 함께 읽는다.
`status`의 회차 정본은 보존한 최초 결과/사용자 검토 대기 상태다. 이 추가 개발 성적을 최초 성적이나 단계 완료로 덮어쓰지 않는다.

저장소 루트 `C:/ITDA_OCR_CODE`에서 실행한다. 예시의 `<...>`는 실제 검토된 파일로 대체해야 한다.
명령 예시는 실행/학습 승인이 아니며 사용자 승인 JSON은 실제 지시를 기록할 때만 작성한다.

## 상태 조회와 준비

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups status
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups verify
```

`status`는 읽기 전용이며 총 4단계, 현재 미완료 단계·대상 회차·회차별 상태·증거 오류·다음 작업을 출력한다.
옛 readiness.training_started=false만으로 학습 미실행이라고 판단하지 않는다.
legacy_training_summary 및 기존 1회 학습/검증 보고도 읽어 후보 기각·모델 유지·미완료를 설명한다.

새 `prepare`는 기존 grouped-8-rounds-v2에서 원본 2,610장을 검증하고 6회 목록과 1~3회 이력을 이관한다.
한 번만 실행하며 이미 생성된 작업 공간을 덮어쓰지 않는다. 이관 후 `import-round1`이나 과거 1회 종료 승계를 다시 실행하지 않는다.
`migration.json`은 이관한 파일 해시와 출처를 기록한다. 2·3회 사용 이력을 학습 완료로 바꾸지 않는다.
`verify`는 전체 원본·주석 SHA와 회차 목록을 확인한다. 입력 목록의 image_id는 과거 결과 연결용 별칭이며
image_path는 원본 폴더 경로다. 승인 정답은 새 작업 공간의 `scorer_only/labels.csv`를 사용한다.
기존 8회 도구와 과거 고정 사본은 역사적 이력용이며 새 실행은 현재 저장소의 도구를 사용한다.
회차 1의 새 정식 테스트를 불필요하게 다시 실행하지 않는다.
다른 기기에서 controller 의존성은 `notebooks/environment/requirements-grouped-control.txt`로 추론 환경에 설치한다.

## 고정·오프라인·최초 테스트

### 이미 사용자가 종료한 기존 1회 승계

아래는 8회 작업 공간을 준비했을 때의 역사적 절차다. 새 6회 작업 공간은 검증된 완료 증거를 이관하므로 재실행하지 않는다.

`prepare_grouped_stage2`는 기존 remediation_12 선택·12건 미해결 종료와 실제 A/B 학습 기각,
승인 원본/crop/상품 그룹 역할을 검증하고 2단계 준비 지시를 연결하는 일회성 이관이다.
현재 사용자 지시 원문과 출처를 인자로 기록한다. 새 테스트·학습 시작 승인을 생성하지 않는다.
기존 최초 보고서는 유지하며 `completion_kind=legacy_user_closure`로 행정적 종료를 구분한다.
95% 달성이나 선택 모델의 새 오프라인 전체 시간 검증으로 표시하지 않는다.
선택된 추론 소스·노트북·모델이 기존 평가와 동일해야 하고 기존 학습 및 종료 증거 해시를 계속 검증한다.
이미 승인된 190번 정정은 원본 관계를 바꾸지 않고 주석 참조 해시만 버전 보존 후 연결한다.
이 작업은 일반 `finish`의 대체 경로가 아니며 기존 1회에만 적용한다.

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.prepare_grouped_stage2 --instruction <실제2단계준비지시> --source-reference <실제출처>
```

검증 후 `status`는 2단계를 반환하며, 이때도 두 슬롯의 `GroupQualify` 및 정식 시작 지시는 필요하다.
2·3회 상품 그룹/승인 crop 검토는 최초 테스트 후 학습의 필수 관문으로 유지한다.

### 현재 6회 계획의 고정·실행

1회에는 사용할 bundle을 명시한다. 기본 weights와 204건 개발 검증 bundle은 다르므로 모델 해시를 확인한다.
2회 이후는 앞 묶음 완료 증거의 단일 모델·코드를 자동으로 선택한다.

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups freeze --round 1 --weights <검토한_bundle>
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups freeze --round 2
```

기본 오프라인 작업은 해당 묶음의 자원 슬롯별 오프라인 확인 후 실제 시작 지시에 따라 실행한다.
OS 방화벽 검증에 필요한 권한은 실제 실행 세션에서 확인하며 준비 명령이 관리자 창을 자동으로 띄우지 않는다.
2·3회 온라인 예외는 실제 지시·고정 사본·모델·실행 범위를 확인한 개발 재시험에만 적용하며 관리자 실행/방화벽 변경을 하지 않는다.
4·5회에 이 예외를 자동 적용하지 않는다. 임시 방화벽 규칙은 두 자식 작업이 모두 끝난 후 정리한다.
같은 Python을 쓰는 다른 작업에도 이 규칙이 적용된다는 기존 범위를 유지한다.

```powershell
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupQualify -Round 2
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupTest -Round 2 -ApprovalsDirectory <시작승인폴더>
```

Round 2는 2·3, Round 4는 4·5를 실행한다. Round 1/6은 단독이며 7·8회는 거부한다.
병행 슬롯은 CPU 0,1,4,5 / 2,3,6,7 (각 P2+E2·4스레드)이다.
이 배정은 회차별 후보 학습·누적 검증에도 동일하게 적용한다. 단독·통합 작업은 0–3을 유지한다.
실행기는 Windows CPU topology를 검사하고 job/runtime에 정책과 실제 affinity를 남긴다.
새 정책의 오프라인 증거는 `qualification_XX_mixed-p2e2-v1`에 저장한다.
기존 `qualification_XX`와 최초 실행 증거는 보존하며 새 배정의 검증으로 인정하지 않는다.
`status.cpus`는 앞으로 사용할 배정이고 `last_execution_cpus`는 이전 runtime의 실제 배정이다.
코드·모델이 바뀐 개발 재평가는 별도 사본·출력 경로에서 수행하며 최초 테스트를 덮어쓰지 않는다.
현재 실행기의 목표는 `3.2×N`, 외부 강제 종료는 `HARD_TIMEOUT_SECONDS=2400`이다.
내부 처리 예산은 정상 회차에서 목표보다 30초 작게 전달하고 pipeline의 저장 여유 30초는 별도 유지한다.
216/394/500장 내부 예산은 661.2/1230.8/1570초이며, 성능 목표 691.2/1260.8/1600초와 구분한다.
1,600초를 넘겨 정상 종료한 500장 실행은 목표 미달이지 강제 종료 사건이 아니다.
runtime에는 전체 시간·목표·강제 종료·내부 예산·메모리·실제 CPU를 함께 기록한다.
감시 주기는 deadline 0.2초, Windows 재귀 프로세스 자원 샘플은 1초로 분리한다.
시작승인폴더에는 각각 `round_02.json`, `round_03.json`처럼 회차별 실제 기록이 있어야 한다.
필드: actor=user, action=start_test, round, instruction, source_reference, approved_at(시간대),
manifest_sha256, code, model. code/model은 `groups/group_02_03/release/release.json`과 일치해야 한다.

각 추론이 끝난 후 회차별 채점한다. 승인 정답의 최신 정정 버전을 명시하고 과거 파일을 자동 선택하지 않는다.

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups score --round 2 --labels <승인정답.csv>
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups score --round 3 --labels <승인정답.csv>
```

출력: `rounds/round_XX/report.md`, 불변 `initial_report.json`, submission.csv, trace, runtime.json.
`analysis.json`에 실제 증거·실패 단계·개선 내용·검증 결과를 기록하면 대표 보고서에 반영된다.
이미 끝난 최초 실행을 덮어쓰거나 미래 회차 정답을 먼저 읽지 않는다.

## 원본 대응 수정·회차별 학습

`revise-mapping --mapping <검토된전체대응표.csv>`는 새로 확인한 증강본→원본 관계만 반영한다.
변경된 행에는 `mapping_review_path`, `mapping_review_sha256`가 필요하다.
근거 JSON은 test_id, original_id, test_sha256, original_sha256, relationship=derived_from,
reviewer, reviewed_at(시간대), source_reference를 포함한다. 기존 연결·테스트 구성은 바꾸지 않는다.
이 명령은 학습 승인을 만들지 않으며 수정 전 대응표와 lock은 mapping_revisions에 보존한다.

실제 보고서 확인·피드백·승인 전에 `bindings`로 검토할 코드·설정·데이터 해시를 확인할 수 있다.
각 작업의 코드 수정 사본은 `--code-root`로 명시한다. 생략하면 현재 저장소를 고정 복사한다.

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups bindings --round 2 --config <학습설정.yml> --groups <검토그룹.json> --pool <승인crop.jsonl> --code-root <코드사본>
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups release --round 2 --approval <2회학습승인.json> --config <학습설정.yml> --groups <검토그룹.json> --pool <승인crop.jsonl> --code-root <코드사본>
```

학습 승인에는 시작 승인 기본 필드에 action=train, feedback, report_sha256 및 bindings 출력 전부를 포함한다.
report_sha256은 해당 initial_report.json이다. 승인 시각은 보고서 created_at 이후여야 한다.
보고서를 보고 사용자가 '추가 의견 없음'이라고 명시한 경우만 그 내용을 feedback으로 기록한다.
config의 실제 epoch/LR/증강/BN/학습범위를 사용자에게 설명하고 승인한다. 75 epoch를 자동으로 가정하지 않는다.
한 묶음 양쪽에 release가 준비되면 controller가 두 CPU 슬롯에서 학습을 실행한다.

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups train --round 2
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupEvaluate -Round 2 -LabelsPath <승인정답.csv>
```

실제 optimizer는 `.training_env`를 사용한다. 이 작업은 원본 학습→epoch별 내부 검증→checkpoint 선정→export→로딩 검증까지 수행하고 후보만 저장한다.
GroupEvaluate는 각 후보를 현재 묶음까지의 누적 회차에서 재평가한다. 각각의 후보 작업은 별도 슬롯이며 회차별 점수와 시간을 분리한다.

## 통합 학습·단계 완료

2·3회와 4·5회는 두 후보를 검토한 뒤 승인 원본 합집합의 통합 학습을 별도로 승인한다.
`integration-review --round 2`를 먼저 실행하면 검토용 review.json을 만든다.
통합 승인 action=train_integration, round=묶음의 첫 회차,
report_sha256=integration/review.json의 SHA, feedback, approved_at, 실제 지시/출처,
bindings 출력(그룹/풀 인자 없이 조회), rounds, round_reports, input_releases를 사용한다.
마지막 세 필드는 integration/review.json에서 정확히 가져온다.

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups integration-review --round 2
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups release-integration --round 2 --approval <통합학습승인.json> --config <통합설정.yml> --code-root <통합코드사본>
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups train --round 2 --integration
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupEvaluate -Round 2 -Integration -LabelsPath <승인정답.csv>
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups finish --round 2 --approval <묶음선정승인.json>
```

finish 승인 action=complete_group, round=첫 회차, feedback/실제 지시/출처/approved_at,
report_sha256=integration/evaluation/review.json(단독은 회차/evaluation/review.json),
rounds, model, code, retained_previous=false, training_release_sha256을 포함한다.
개별 회차 95%/시간 미달을 인지한 실제 진행 승인에는 accept_target_shortfall=true를 명시한다.
회귀·오류·형식 실패를 이 옵션으로 우회할 수 없다.
기각·이전 모델 유지 시 같은 평가 명령에 `-Retain`, finish에 `--retain`을 사용하고
retain_evaluation/review.json을 검토하여 retained_previous=true로 승인한다.
공용 weights는 바꾸지 않고 다음 묶음 freeze가 선정한 불변 모델·코드를 사용한다.
1·6회는 별도 통합 학습 없이 회차 후보의 평가·finish를 사용한다.
6회 선정 후 4단계 종료이며 7·8회 신규 테스트·학습은 없다.
단계별 누적 평가 장수는 216 → 1,216 → 2,110 → 2,610이며 최종 성적은 누적 개발 재평가다.

## 실패와 새 세션

한 worker가 실패해도 상대 worker의 결과는 보존한다. 다음 묶음으로 자동 넘어가지 않는다.
qualify/test/train을 다시 요청하면 완료 증거가 유효한 worker는 건너뛰고 아직 시작하지 않은 쪽만 실행한다.
이 경우 jobs의 already_finished와 rounds에 실제 실행 범위를 남긴다. 중단 출력만 있는 worker는 완료로 간주하지 않는다.
이미 생성된 최초 실행/학습/평가 폴더는 재실행으로 덮어쓰지 않는다.
중단 시 jobs/*/result.json, worker 로그, runtime, state와 PID를 확인한다.
실패 작업 재시도는 원인 확인과 새 실행/승인 범위를 확정한 별도 이력 경로가 필요하다.
stale lock을 자동 삭제하여 생존 프로세스와 중복 실행하지 않는다.
새 작업 공간의 상태 조회는 이전 작업 공간의 실행 lock도 확인한다. 이전 실행이 살아 있으면 새 coordinator 시작을 차단한다.
대표 프롬프트: [grouped_session_prompts.md](grouped_session_prompts.md).
