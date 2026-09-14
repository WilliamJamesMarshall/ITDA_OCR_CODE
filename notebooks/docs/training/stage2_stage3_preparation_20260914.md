# 2·3단계 테스트·머신러닝 실행 준비 및 다른 세션 인계

현재 2단계(2·3회) 사용자 검토 대기. 이번 지시는 준비만 허용하며 테스트·OCR·replay·학습·보정 fitting을 실행하지 않는다.
새 기준은 [6회차 정본](../protocol/grouped_6_rounds.md)이며 기존 결과·승인·공용 모델은 보존한다.

## 준비 산출물

작업 공간: `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/execution-preparation-20260914-v2`.
실제 생성 여부와 파일 해시는 이 폴더의 `preparation.json`을 확인한다. 파일 존재만으로 실행 성공을 주장하지 않는다.

준비 완료 감사: [preparation-audit.json](C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/execution-preparation-20260914-v2/preparation-audit.json).
v2 생성 후 사본 332파일 SHA 일치, 보존 이력 34파일 불변, 원본 2610장 중복/누락 0,
현재 2단계·활성 작업 없음으로 확인했다. 이는 읽기 전용/정적 감사이며 동작 테스트가 아니다.
v1은 이전 준비 이력으로 보존하고 실행용으로는 v2를 사용한다.

- `round_02/code`, `round_03/code`: 같은 논문 전체 계획 구현에서 출발한 별도 사본. 모델은 기존 검증 bundle 유지.
- 각 `review/groups.draft.json`, `review/crops.draft.json`, `review/configs/*.draft.yml`: 회차별 검토 초안. 승인/학습 입력 아님.
- `historical-crops.draft.json`: 1회 이관 crop 필드 검토용. 과거 승인 원문을 대체하지 않음.
- `stage3-deferred.json`: 4·5회 목록 해시·장수·선행 조건만 연결. 모델 미선정, 미래 이미지/정답/crop 미편입.
- `preparation.json`: 코드·모델·입력·초안·실행기 해시, 보존 근거, 미완료 관문. 테스트/학습 승인 false.

재준비는 새 버전 경로로만 수행한다. 기존 준비 사본, full-01/full-02, migration.json,
최초 보고서·상태·승인·group_roles를 덮어쓰지 않는다.

## 이번 최신화

1. 1 → (2·3) → (4·5) → 6, 누적 216 → 1216 → 2110 → 2610. 7/8 신규 실행 금지.
2. 목표 3.2×N초와 전체 notebook watchdog 2400초 분리. 내부 예산은 정상 회차에서 목표−30초,
   pipeline 저장 여유 30초를 유지한다. 작은 qualification은 90초 로딩 진단이며 성능 평가가 아니다.
3. 2/4회 CPU 0,1,4,5, 3/5회 CPU 2,3,6,7. 1/6회·통합 CPU 0–3, 모두 4스레드.
4. 전체 startup/초기화/CSV/종료 시간, RSS/commit/가용 RAM과 실제 자식 CPU 기록.
   deadline은 0.2초, 비싼 자원 샘플은 1초 간격. 준비 중 관리자 창/방화벽 조작 없음.
5. 이전 작업 공간의 개발 폴더 안 execution.lock까지 조회. 생존/소유자 불명 작업과 중복 실행 금지.
   현재 작업 공간의 정식 jobs 외 개발 runner도 공유 execution.lock을 통해 status에 표시한다.
6. review_status가 pending인 crop, pending 필드 정답을 가진 내부 검증 crop,
   Global.paper_review_status가 pending인 config는 학습 release에서 거부.
   optimizer crop에 날짜 필드 정답을 일괄 요구하지는 않는다.

옛 최초 테스트 CPU 0–3/4–7과 당시 시간 판정은 그대로 유지한다.
v15는 비교 기준이지 최신 실행 전체를 대표하지 않는다. 이후 full-01 실패/퇴행 및 full-02 중단을 함께 읽는다.
새 후보에 예전 511개 테스트 통과, 저장 OCR 재생 +8/+9 개선을 그대로 전가하지 않는다.

## 다른 세션: 새 구현의 실행 전 관문

1. status/verify, migration/승인/원본/모델 해시와 활성 PID를 다시 읽는다. CPU/RAM은 실행 직전 재확인.
2. 테스트 지시가 실제로 주어진 뒤에만 기존 회귀 테스트와 새 `test_grouped_preparation_policy.py`,
   후보 `test_paper_plan.py`를 실행한다. 현재는 작성·구문 확인만 했고 실행하지 않았다.
3. 패키징된 소스 해시 및 외부 src 없이 실행되는 notebook 일치, 날짜/시각·부분 crop·역할·출력 순서·캐시를 확인한다.
4. 1회 보호 204건 및 보호 필드, 저장된 2·3회 OCR 재생에서 획득/손실을 분리한다.
5. 승인된 원본 crop/전사 개입으로 원인 분리, 폭별 배치 비교, 선택적 CTC 기록을 확인한다.
   신뢰도 보정/복구 효율 table은 실제 분리 그룹 자료·검증·배포 승인 없이는 활성화하지 않는다.
6. 사전검증 실패 시 전체 OCR을 시작하지 않는다. 통과 후 실제 보고한 고정 사본에 대한 실행 지시를 연결한다.

## 2·3회 개발 재시험 실행 인터페이스 — 여기서는 실행하지 않음

`notebooks/experiments/paper_ocr/phase2/run_prepared.py`는 2·3회 개발 재시험 전용이다.
기존 run_candidate.py/run_monitor_candidate.py는 과거 기록용이며 새 실행에 사용하지 않는다.
승인 폴더에 각 `round_02.json`, `round_03.json`을 실제 지시 수신 후 기록한다.
필수 필드는 actor=user, action=start_development_test, round, instruction, source_reference,
approved_at(시간대), preparation_sha256, runner_sha256, manifest_sha256, network_mode이다.
준비 지시를 테스트 승인으로 만들지 않으며 예시나 기본 선택을 승인 원문으로 사용하지 않는다.
이미 수행된 과거 승인은 재승인 요청하지 않는다. 변경된 미검증 코드 실행은 그 과거 완료 작업과 다른 범위다.

```powershell
# 실제 새 실행 지시와 사전검증 통과 후 다른 세션에서만 실행. 예시는 승인이 아님.
.\.labeling_paddle_env\Scripts\python.exe notebooks/experiments/paper_ocr/phase2/run_prepared.py --execute --preparation <준비폴더/preparation.json> --approvals <실제승인폴더> --output <새실행폴더> --rounds 2 3 --network-mode <offline또는범위확인된online>
```

기본은 offline. 기존 2·3회 온라인 예외는 해당 지시·새 고정 사본·로컬 모델 범위에 연결하여 기록한다.
온라인은 외부 OCR·이미지 전송·학습·4/5회·방화벽 변경 승인이 아니다.
한쪽이 유효하게 완료됐다면 동일 후보에 대해서는 그 결과를 보존하고 `--rounds`에 남은 회차만 지정한다.
중단/실패 폴더를 재사용하지 않는다. runner는 학습·채점·공용 반영·정식 상태 변경을 하지 않는다.
원본 500장과 전체 runtime이 모두 있어야 완결 평가이며 부분 CSV는 공식 성적/시간이 아니다.
사후 채점은 scorer_only의 승인 정답으로 3N 분모를 유지하고 누락/실패 0점, NONE 일치 득점으로 수행한다.

## 회차별 학습 준비와 관문

각 후보는 이전 단계 승인 누적 자료와 해당 회차 승인 자료만 사용한다. 병행 상대 회차를 개별 학습에 섞지 않는다.
현재 그룹 초안은 이미지 SHA 기반 임시 식별이며 상품/촬영 그룹 검증으로 인정하지 않는다.
상품/촬영 관계와 optimizer/inner-validation 역할은 사용자가 검토한 후 영구 registry에 편입한다.
이미 등록된 역할은 변경하지 않는다. 동일 상품이 새 회차에서 발견되면 기존 역할을 계승한다.

crop의 전사·영역·원본/주석/crop SHA·제조/소비기한 역할·실패 유형을 확인한다.
내부 검증 crop의 명시적 date_fields를 검토하고 pending을 승인된 정답/NONE으로 취급하지 않는다.
과거 223개 crop의 주석 revision 차이는 실제 정정 이력을 검토해 연결하며 record_sha를 임의로 최신화하지 않는다.
검토 끝난 자료는 새 reviewed 파일로 저장하고 초안을 보존한다. 준비 도구는 학습 목록이나 승인 JSON을 만들지 않는다.

설정 초안은 저장소 기본 config에서 파생된 5개 비교안이며 과거 승인 config 자체가 아니다.
기본 control/포장 mild/no-concat/head-only/점 형태 후순위, 15 epoch·LR 5e-5 또는 1e-4는 검토 시작값이다.
과거 실제 A는 MildPrintAug, B는 증강 없음이었다. 기존 승인은 그 당시 1 epoch A/B에 한정한다.
새 설정의 구조·사전 유지, BN 통계 고정, seed 20260911, 내부 검증 필드 정확도→CER→NED→이른 epoch,
patience 5를 확인한다. 저장 증강본 1106장 제외와 실시간 증강 사용은 별개다.
승인될 config의 `Global.paper_review_status`를 실제 검토 후 approved로 바꾸고 그 최종 SHA를 승인에 연결한다.
이를 자동으로 바꾸거나 다섯 후보를 모두 승인됐다고 가정하지 않는다.

사용자 보고서 확인·피드백·정확한 데이터/config/코드 범위 승인 후 운영 안내의 bindings/release를 사용한다.
`--code-root`는 해당 준비 회차의 code를 명시해 포장 증강 학습기/정책 변경이 빠지지 않게 한다.
두 회차 최초 보고서가 있어야 release가 가능하며, optimizer는 별도 실행 지시 후에만 시작한다.
개별 후보 완료 후 누적 1216장 회귀, 별도 통합 승인·학습·누적 평가·선정이 필요하다.
목표 미달·기존 정답 퇴행을 숨기거나 후보를 공용 weights에 자동 반영하지 않는다.

## 3단계 대기 조건

4/5회 입력 목록(394/500장)은 이미 잠겼다. 지금은 미래 이미지/정답/crop을 읽거나 학습에 편입하지 않는다.
2단계 완료·선정 증거가 유효해진 후 현재 운영 도구로 `freeze --round 4`하여 선택 모델/코드를 받는다.
두 최초 테스트와 보고서 → 사용자 검토/원본 crop 승인 → 개별 후보 → 통합 학습/누적 2110장 평가/선정 순서다.
4회 목표 1260.8초, 5회 1600초, 각각 watchdog 2400초. 온라인 예외를 자동 승계하지 않는다.
최종 6회까지 누적 2610장은 개발 성적이며 별도 독립 최종 성적은 없다.

## 현 상태의 한계

실행기·테스트 코드 작성과 파일 준비는 성능 검증이 아니다. 아직 테스트/학습/보정 fitting을 실행하지 않았다.
상품 그룹·crop 필드·학습 설정·실제 실행 지시 및 단계별 승인 관문이 남아 있다.
실행 전 준비 파일과 실제 controller가 달라졌으면 원래 준비 폴더를 보존하고 새 버전으로 준비한다.
