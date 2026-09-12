# 8회 실행 준비와 운영

정책 정본: [sequential_8_rounds.md](../protocol/sequential_8_rounds.md).
아래 명령은 향후 실행용이며 명령 예시는 사용자 승인이 아니다.
외부 작업 폴더 기본값은 `C:/ITDA_OCR_WORKSPACE/sequential-8-rounds`이다.

## 준비

```powershell
.training_env/Scripts/python.exe notebooks/project/run.py scripts.prepare_sequential_rounds prepare
.training_env/Scripts/python.exe notebooks/project/run.py scripts.train_recognition_cpu --preflight-only --report C:/ITDA_OCR_WORKSPACE/sequential-8-rounds/training_preflight.json
.labeling_paddle_env/Scripts/python.exe notebooks/project/run.py unittest discover -s notebooks/project/tests -q
```

prepare는 정답을 추론 목록에 포함하지 않는다. 정식 실행 폴더가 생긴 뒤에는 manifest를 재생성하지 않는다.
기준선은 baseline.json, 예전 정책은 previous_policy에 보존된다.
기존 prepare_group_splits/prepare_stage3_policy/prepare_holdout_lock의 직접 실행은 차단됐다.
verify_split_inputs와 prepare_stage1_data verify는 과거 자료의 무결성 검사이며 새 실행 허용 판정이 아니다.

## 정식 테스트와 별도 채점

```powershell
.labeling_paddle_env/Scripts/python.exe notebooks/project/run.py scripts.sequential_rounds infer --round 1 --approval <실제_시작지시_기록.json>
.labeling_paddle_env/Scripts/python.exe notebooks/project/run.py scripts.sequential_rounds score --round 1 --labels C:/ITDA_OCR_WORKSPACE/sequential-8-rounds/scorer_only/labels.csv
```

infer는 execution_readiness.json의 formal_environment_verified 및 환경 증거 해시를 요구한다.
관리자 PowerShell에서 `notebooks/project/scripts/run_offline_verification.ps1`을 실행해 검증한다.
기존 개발 노출 이미지 한 장만 사용하며, 특정 Python 실행파일의 outbound 방화벽 규칙을 임시로 추가하고 finally에서 제거한다.
같은 Python 실행파일을 사용하는 다른 프로세스도 검증 동안 외부 통신이 제한된다.
PC 전체 인터넷 설정은 변경하지 않는다. 최초 검증 후에도 매 정식 테스트는 이 wrapper의 `-Action Test`로 실행한다.
추론 시 이미지와 모델만 별도 제출 사본에 복사하고, 원본 첫 CONFIG 셀을 유지한다.
실행하는 Python의 kernel을 지정해 다른 전역 Python으로 실행되지 않게 한다.
실패·시간초과도 inference_complete 기록을 남겨 별도 scorer에서 실패 보고서를 생성한다.
동일 회차 재실행은 기존 기록 덮어쓰기를 막기 위해 차단된다. 재평가가 필요하면 최초 기록을 별도 보존하고
그 변경과 승인 범위를 확인한 뒤 재평가용 작업 경로를 구성해야 한다. 자동 재평가는 구현하지 않았다.

승인 기록의 필수 필드: actor=user, action=start_test 또는 train, round, instruction,
source_reference, approved_at(시간대 포함), manifest_sha256, code(파일 해시 맵), model(파일 해시 맵).
학습 승인은 report_sha256도 필수다. feedback 필드에 실제 사용자 피드백을 보존한다.
실제 사용자 지시 없이 이 레코드를 작성하면 안 된다.

## 원본 편입과 학습

```powershell
.labeling_paddle_env/Scripts/python.exe notebooks/project/run.py scripts.sequential_rounds release --round 1 --approval <실제_학습승인.json> --groups <검증된_상품그룹.json>
.training_env/Scripts/python.exe notebooks/project/run.py scripts.train_recognition_cpu --round 1 --train-list C:/ITDA_OCR_WORKSPACE/sequential-8-rounds/rounds/round_01/optimizer_train.txt --validation-list C:/ITDA_OCR_WORKSPACE/sequential-8-rounds/rounds/round_01/inner_validation.txt
```

상품그룹 JSON은 원본 ID별 group_id, verified, evidence를 가진다. 비어 있는 예전 검토 기록을 승인으로 바꾸지 않는다.
원본 대응 검토 목록이 남은 회차는 편입이 차단된다. 새 검토 근거 반영 시 manifest와 승인 해시도 함께 갱신해야 한다.
인식 학습 목록은 승인된 원본의 기존 OCR crop/원문만 사용하며 최종 날짜 XLSX를 전사 라벨로 사용하지 않는다.

학습 adapter는 고정 runtime을 수정하지 않고 매 epoch 끝에 전체 내부 validation을 재채점한다.
고정 runtime의 Windows evaluator가 마지막 batch를 제외하는 경로를 사용하지 않는다.
선정 checkpoint와 전체 내부 예측을 외부 경로에 보존한다. patience=5를 적용한다.
학습 성공 후 export → 파이프라인 로딩 확인 → 이전 추론 모델 백업 → 선정 모델 반영 순으로 진행한다.
다음 회차는 training_complete와 반영 모델 해시가 맞아야 진행한다.

## 현재 검증 범위

단위검사·합성 승인 fixture는 실제 사용자 승인이 아니며 임시 디렉터리에만 존재한다.
초기 checkpoint의 실제 export/로딩 성공은 학습된 checkpoint의 검증을 대체하지 않는다.
별도 합성 이미지로 실제 optimizer·epoch hook·early stopping 검증을 수행한다. 학습 후 정식 모델 교체는 하지 않는다.
공식 문서는 Linux를 필수로 정하지 않았다. 4개 논리 CPU·OS outbound 차단의 Windows 재현과
운영진 서버 자체의 성능 인증은 구분한다. 95%/3초 목표 달성은 실제 회차 테스트에서 평가한다.
