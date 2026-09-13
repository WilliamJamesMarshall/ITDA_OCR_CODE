# 5단계 병행 실행 운영

정본: [grouped_8_rounds.md](../protocol/grouped_8_rounds.md).
저장소 루트 `C:/ITDA_OCR_CODE`에서 실행한다. 예시의 `<...>`는 실제 검토된 파일로 대체해야 한다.
명령 예시는 실행/학습 승인이 아니며 사용자 승인 JSON은 실제 지시를 기록할 때만 작성한다.

## 상태 조회와 준비

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups status
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups verify
```

`status`는 읽기 전용이며 총 5단계, 현재 미완료 단계·대상 회차·회차별 상태·증거 오류·다음 작업을 출력한다.
옛 readiness.training_started=false만으로 학습 미실행이라고 판단하지 않는다.
legacy_training_summary 및 기존 1회 학습/검증 보고도 읽어 후보 기각·모델 유지·미완료를 설명한다.

최초 한 번만 `prepare`, `import-round1`을 실행한다. 이미 생성된 작업 공간/이력은 덮어쓰지 않는다.
회차 1의 새 정식 테스트를 불필요하게 다시 실행하지 않는다.
다른 기기에서 controller 의존성은 `notebooks/environment/requirements-grouped-control.txt`로 추론 환경에 설치한다.

## 고정·오프라인·최초 테스트

### 이미 사용자가 종료한 기존 1회 승계

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

1회에는 사용할 bundle을 명시한다. 기본 weights와 204건 개발 검증 bundle은 다르므로 모델 해시를 확인한다.
2회 이후는 앞 묶음 완료 증거의 단일 모델·코드를 자동으로 선택한다.

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups freeze --round 1 --weights <검토한_bundle>
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/run.py scripts.run_round_groups freeze --round 2
```

관리자 PowerShell에서 해당 묶음의 자원 슬롯별 오프라인 확인 후 실제 시작 지시에 따라 실행한다.
CPU·방화벽 권한은 기존 관리자 실행 방식을 유지한다. 임시 방화벽 규칙은 두 자식 작업이 모두 끝난 후 정리한다.
같은 Python을 쓰는 다른 작업에도 이 규칙이 적용된다는 기존 범위를 유지한다.

```powershell
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupQualify -Round 2
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupTest -Round 2 -ApprovalsDirectory <시작승인폴더>
```

Round 2는 2·3, Round 4는 4·5, Round 6은 6·7을 실행한다. Round 1/8은 단독이다.
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

2·3, 4·5, 6·7은 두 후보를 검토한 뒤 승인 원본 합집합의 통합 학습을 별도로 승인한다.
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
1·8회는 별도 통합 학습 없이 회차 후보의 평가·finish를 사용한다.

## 실패와 새 세션

한 worker가 실패해도 상대 worker의 결과는 보존한다. 다음 묶음으로 자동 넘어가지 않는다.
qualify/test/train을 다시 요청하면 완료 증거가 유효한 worker는 건너뛰고 아직 시작하지 않은 쪽만 실행한다.
이 경우 jobs의 already_finished와 rounds에 실제 실행 범위를 남긴다. 중단 출력만 있는 worker는 완료로 간주하지 않는다.
이미 생성된 최초 실행/학습/평가 폴더는 재실행으로 덮어쓰지 않는다.
중단 시 jobs/*/result.json, worker 로그, runtime, state와 PID를 확인한다.
실패 작업 재시도는 원인 확인과 새 실행/승인 범위를 확정한 별도 이력 경로가 필요하다.
stale lock을 자동 삭제하여 생존 프로세스와 중복 실행하지 않는다.
대표 프롬프트: [grouped_session_prompts.md](grouped_session_prompts.md).
