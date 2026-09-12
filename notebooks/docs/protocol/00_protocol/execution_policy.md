> 문서 열람용 사본. 계획 수정은 원본 `C:\ITDA_OCR_CODE\학습 및 테스트 결과\00_protocol\execution_policy.md`에서 수행한 뒤 이 도구로 다시 게시합니다. 승인/정답 데이터는 포함하지 않습니다.

> 과거 5-fold 기록. 현재 정본: C:/ITDA_OCR_CODE/notebooks/docs/protocol/sequential_8_rounds.md. 기존 normalization·선정·검출 계약은 새 정본에서 유지하며 fold 접근 정책은 대체되었습니다.

# ITDA OCR 학습·평가 실행 정책 (과거 기록)

상태: **확정 — 0단계 완료**  
정책 버전: `1.3`  
확정일: 2026-09-11 / 정책 1.3 갱신: 2026-09-12  
기준 계획: `학습 및 테스트 결과/학습_및_평가_실행계획.md`

이 문서는 학습과 평가를 시작하기 전에 고정해야 하는 선택 규칙을 정의한다. 아래 규칙은 Round 0 드라이런 전에 기계적으로 검증하며, fold 5를 공개한 뒤에는 변경하지 않는다.

## 1. 모델 개발 범위

1. 1차 학습 대상은 날짜 줄 인식기다. 현재 `korean_PP-OCRv5_mobile_rec`과 같은 아키텍처의 학습 가능한 공식 초기 체크포인트에서 미세조정한다.
2. 날짜 줄 검출기는 별도 2차 학습 대상으로 둔다. 날짜 줄 polygon 주석과 기존 검출기 기준선이 준비된 뒤에만 학습한다.
3. 날짜 역할 선택과 `final_date` 생성 규칙은 기존 파이프라인 모듈에 남긴다. 인식 모델 지표와 전체 파이프라인 지표를 합치지 않는다.
4. 현재 저장된 `inference.pdiparams`는 기준선 추론 모델이다. 학습 가능한 초기 체크포인트로 승인하지 않는다.

## 2. 실행 자원과 재현성

- 학습과 평가 모두 CPU만 사용한다. CUDA, GPU, 외부 가속 서비스는 사용하지 않는다.
- 학습과 평가의 기본 CPU 스레드 수는 4로 고정한다.
- 평가 환경은 Standard 4-Core vCPU 상당 환경을 기준으로 한다.
- 학습 중 자동 다운로드를 허용하지 않는다. 패키지와 초기 가중치는 실행 전에 준비하고 SHA-256을 기록한다.
- Python, NumPy, Paddle의 seed는 모두 `20260911`로 고정한다.
- fold 분할과 내부 validation 분할에도 seed `20260911`을 사용한다.
- 각 회차는 이전 회차 체크포인트에서 이어서 학습하지 않는다. 같은 승인 초기 체크포인트에서 누적 개발 데이터로 다시 학습한다.
- 초기 체크포인트의 경로, 출처, 버전과 SHA-256이 달라지면 같은 실험 계열로 집계하지 않는다.

## 3. 데이터 공개와 fold 정책

- fold 1~4는 순차적 개발 평가 배치다. 평가가 끝난 fold만 모델 개발 데이터로 공개한다.
- fold 5는 최종 잠금 테스트다. 학습, 체크포인트 선택, early stopping, 임계값 선택, 규칙 수정에 사용하지 않는다.
- 기존 파이프라인 개발에 사용한 705장은 fold 5에 배정하지 않는다. fold 1~4에만 배정할 수 있다.
- 2026-09-12 사용자는 OCR 주석 2,610장 초안을 그대로 일괄 승인했다. 승인 당시 스냅샷은 `../02_annotations/approvals/user-as-is-approval-20260912`에 동결한다. 일괄 승인은 개별 시각 검수 이력을 뜻하지 않으며, 누락 polygon/원문을 채워주지 않는다. 사용자 승인과 모델별 학습 기술 요건 충족을 분리하고, 기술 요건 미충족 자료를 정답 없는 검출 음성 샘플로 사용하지 않는다. 705장 정책 검토 진입과 실제 fold·학습 실행 게이트는 구분한다.
- 705장을 학습에 편입한 시점부터 기존 705장 성적은 독립 일반화 성능으로 보고하지 않는다.
- 같은 상품, 포장 버전, 연속 촬영, 확대·회전 파생본은 같은 `group_id`에 둔다.
- 학습, 내부 validation, 다음 평가 fold, fold 5 사이에 `group_id` 교집합이 있으면 실행을 중단한다.
- 그룹을 쪼개서 정확히 90:10 또는 522장을 맞추지 않는다. 정확한 522장 분할이 불가능하면 fold를 생성하기 전에 실행계획을 개정한다.
- `테스트용데이터`는 학습대상 2,610장과 동일 이미지가 있으므로 외부 독립 테스트셋으로 사용하지 않는다.

## 4. 내부 validation

평가 후 공개된 각 fold를 `optimizer_train`과 `inner_validation`으로 다시 분리한다.

- 목표 비율은 약 90:10이다.
- 분리는 `group_id` 단위로 수행한다.
- 한 번 `inner_validation`으로 지정된 그룹은 이후 회차에서도 학습에 넣지 않는다.
- 새 fold가 공개되면 그 fold 안에서 약 10%의 그룹을 내부 validation에 추가한다.
- 누적 개발 데이터 2,088장은 `optimizer_train + inner_validation`의 합이다.
- 예상 누적 규모는 Round 1 약 470/52장, Round 2 약 940/104장, Round 3 약 1,410/156장, Round 4 약 1,880/208장이다. 실제 수량은 그룹 경계를 우선한다.
- 전체/부분 날짜, 인쇄 유형, 반사·곡면·흐림·저해상도, 복수 날짜, 언어·문자 유형, 이미지 출처 분포를 가능한 한 유지한다.
- 다음 평가 fold와 fold 5는 체크포인트 선정에 사용하지 않는다.

## 5. 인식 모델 지표와 선택 규칙

### 5.1 지표 정규화

지표 계산 전 다음만 적용한다.

1. Unicode NFC 정규화
2. 앞뒤 공백 제거
3. 영문 월과 영문 표제의 대소문자 통일
4. 줄바꿈을 `\n`으로 통일

날짜 구분자, 숫자, 내부 공백은 제거하거나 치환하지 않는다.

### 5.2 지표 정의

- `string_exact_match_rate`: 정규화 후 전체 문자열이 정확히 같은 샘플 비율. 높을수록 좋다.
- `micro_cer`: 전체 삽입·삭제·치환 수를 전체 정답 문자 수로 나눈 값. 낮을수록 좋다.
- `normalized_edit_similarity`: 샘플별 `1 - edit_distance / max(정답 길이, 예측 길이)`를 평균한 값. 높을수록 좋다.
- `final_date_exact_match_rate`: 인식 결과가 전체 파이프라인을 통과한 뒤 최종 날짜가 정확히 같은 비율. 모델 체크포인트 선택과 분리해 보고한다.

### 5.3 체크포인트 선택

다음 순서를 고정한다.

1. `string_exact_match_rate`가 가장 높은 체크포인트
2. 동률이면 `micro_cer`가 가장 낮은 체크포인트
3. 다시 동률이면 `normalized_edit_similarity`가 가장 높은 체크포인트
4. 다시 동률이면 더 이른 epoch

매 epoch 종료 후 내부 validation을 실행한다. 위 선택 순서가 5 epoch 연속 개선되지 않으면 early stopping한다. `patience=5`는 fold 결과를 본 뒤 바꾸지 않는다.

PaddleOCR가 생성하는 `best_accuracy`는 실행 중 진단용이며 공식 선정 체크포인트가 아니다. 각 epoch의 내부 validation 예측을 `scripts/recognition_metrics.py`로 다시 계산하고, 그 결과에 위 선택 순서와 `patience=5`를 적용한 체크포인트만 승인한다.

## 6. 검출 모델 지표와 선택 규칙

### 6.1 검출 대상

검출 정답은 날짜가 실제로 적힌 줄 polygon이다.

- 소비기한 날짜 줄
- 제조일 날짜 줄
- 역할이 불명확한 날짜 줄

표제만 있는 영역과 날짜가 없는 설명문은 별도 속성으로 보존하며 날짜 줄 정답으로 세지 않는다.

### 6.2 판정과 지표

- polygon IoU `0.5` 이상을 true positive로 인정한다.
- 정답과 예측은 1:1로 대응한다.
- 같은 정답에 중복으로 대응한 나머지 예측은 false positive다.
- 전체 영역을 합산한 micro precision, micro recall, micro Hmean을 사용한다.
- 점 인쇄, 곡면, 반사, 작은 글씨, 복수 날짜 slice의 recall을 별도로 보고한다.

### 6.3 체크포인트 선택

1. 같은 내부 validation에서 기존 검출기의 recall 기준선을 먼저 측정한다.
2. 기준선보다 micro recall이 낮은 체크포인트는 제외한다.
3. 통과 모델 중 micro Hmean이 가장 높은 체크포인트를 선택한다.
4. 동률이면 micro recall, micro precision, CPU 추론 시간, 더 이른 epoch 순으로 선택한다.
5. 핵심 slice의 정답 영역이 10개 이상이면 기존 기준선보다 true positive 수가 감소한 모델은 자동 채택하지 않는다. 10개 미만이면 지표를 진단값으로 보고하고 수동 검토한다.

CPU 시간은 모델 초기화를 제외하고 동일 이미지, 동일 전처리, 4스레드 환경에서 1회 warm-up 후 3회 측정한 총시간의 중앙값으로 비교한다.

## 7. 출력 계약

제출 열은 다음 순서로 고정한다.

```text
image_id,year,month,day,final_date
```

완전 미인식은 다음과 같이 출력한다.

```text
<image_id>,NONE,NONE,NONE,NONE
```

`<image_id>`에는 입력 파일 stem을 사용하고 `year`, `month`, `day`는 각각 `NONE`, `final_date`는 `NONE`으로 기록한다.

부분 날짜는 기존 계약의 `NONE-MM-DD` 또는 `YYYY-MM-NONE` 형식을 유지한다. 내부 의미 비교와 공식 CSV 형식 적합성을 별도로 보고한다.

## 8. 회차별 보존 증거

각 회차는 다음을 보존한다.

- 실제 학습 및 평가 manifest와 SHA-256
- 모델 이전·이후 체크포인트 SHA-256
- 초기 체크포인트 식별자와 SHA-256
- Git commit과 작업 트리 상태
- Python·패키지·OS·CPU 정보
- 모든 seed와 학습 설정
- epoch별 loss와 내부 validation 지표
- best checkpoint 선정 근거
- CPU 추론 시간과 전체 파이프라인 시간
- 출력 계약 검사 결과와 실행 오류

## 9. 변경 통제

- Round 0 전에 정책을 바꾸면 버전과 변경 이유를 기록한다.
- fold 1~4 결과를 보고 학습 설정을 바꿀 수 있지만, 변경 사항은 다음 회차 실행 전에 동결한다.
- fold 5를 공개한 뒤에는 모델, 규칙, 임계값, 정규화, 지표, 출력 계약을 변경하지 않는다.
- fold 5 실행 후 수정된 모델은 별도 배포 모델이며 기존 fold 5 점수를 해당 모델의 성능으로 사용하지 않는다.

## 10. 0단계 완료 근거

0단계의 학습 계약은 다음 값으로 확정했다.

- 공식 학습 소스: PaddleOCR `v3.7.0`, commit `b03f46425e8ff4442b268ce449e3eef758146cd4`
- 초기 체크포인트: `weights/training/korean_PP-OCRv5_mobile_rec_pretrained.pdparams`
- 체크포인트 SHA-256: `8975dede5e0c2f47e0a7712b3d79ffdc766972f872fd0441ebcccd9d77cd52a3`
- 한국어 문자 사전 SHA-256: `2193f5dd0c62a4f268902b5d96dadfec3908d299afa9a6e5cad2c6a96c772828`
- 호환성: 모델/체크포인트 텐서 `968/968`, 파라미터 `27,722,647/27,722,647` 일치
- 재현 환경: `.training_env`, CPython `3.10.20`, `paddlepaddle==3.2.2` CPU 빌드
- 의존성 잠금: `requirements-train-cpu.lock.txt`
- CPU 학습 설정: `configs/training/korean_PP-OCRv5_mobile_rec_cpu.yml`
- 학습 진입점: `scripts/train_recognition_cpu.py`
- 지표·선정 진입점: `scripts/recognition_metrics.py`
- 자동 준비·사전점검: `scripts/prepare_training_runtime.ps1`
- 사전점검 증거: `00_protocol/training_preflight.json`, 상태 `passed`
- CPU 1 epoch 합성 스모크 학습 증거: `00_protocol/training_smoke.json`, 상태 `passed`

재현 준비 명령은 다음과 같다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\prepare_training_runtime.ps1
```

실제 학습 명령은 OCR 주석 승인과 그룹 분할 이후 생성할 PaddleOCR 형식의 두 라벨 목록을 입력받는다. `--round`는 1~4만 허용하며, 초기 체크포인트를 지정하는 사용자 옵션을 제공하지 않으므로 모든 회차가 위 체크포인트에서 시작한다.

```powershell
.training_env\Scripts\python.exe scripts\train_recognition_cpu.py `
  --round 1 `
  --train-list <optimizer_train.txt> `
  --validation-list <inner_validation.txt>
```

## 11. 데이터 정비와 OCR 주석 단계의 경계

2026-09-11 사용자 요청에 따라 단계 경계를 구체화한다.

- 1단계: XLSX 최종 날짜 승인, 정본 JSONL/CSV, 이미지 ID와 SHA-256 대응, provenance 복구, 제외 목록 고정, 주석 검수 입력 준비.
- 2단계: 날짜 줄 원문·polygon 구축과 사람 승인, 상품/연속 촬영/파생본 그룹 검수, 미평가 난이도·조건 보완.
- 주석·그룹 승인 후: fold와 영구 inner validation 분할, 누수 검사, PaddleOCR 학습 목록 생성.

최종 날짜 승인만으로 OCR 원문·polygon 또는 상품 그룹을 승인하지 않는다. 1단계의 입력 무결성 통과는 2단계 진입을 뜻하며 실제 모델 학습 허가는 아니다. 상세 계약과 검증 결과는 `stage1_data_protocol.md`, `stage1_readiness.json`을 따른다.

## 12. 출력 계약 정정

사용자가 전달한 학술제 안내에 따라 year/month/day가 전부 NONE이면 final_date는 NONE이다. 이전 정책 1.1의 NONE-NONE-NONE을 대체한다. 부분 날짜는 기존 형식을 유지한다. 과거 실험 결과는 역사적 기록으로 보존한다.

## 13. 2026-09-12 3~5단계 착수와 705장 정책 확정

- 565장 보완 후 전체 2,610장에 대한 최신 승인은 `../02_annotations/approvals/user-full-2610-approval-20260912-closeout`이다. 주석 미완료 565장이라는 이전 기록은 현재 상태에 적용하지 않는다.
- 기존 개발 705장을 영구 학습 제외하지 않는다. 배정된 fold의 평가 후에만 fold 1~4 누적 개발 데이터로 편입하며, 별도 선행 학습에 사용하지 않는다.
- 기존 개발 성적은 회귀 진단용이며 독립 일반화 성능으로 보지 않는다. 705장을 학습에 편입한 후에는 이를 독립 평가값으로 재사용하지 않는다.
- 기존 705장이 속한 상품 그룹 전체는 fold 5 후보에서 제외한다. 미노출 1,905장 중에서도 이 그룹과 연결되는 이미지는 fold 5에 넣지 않는다. 나중에 교집합이 발견되면 실행 중단 후 그룹·분할을 재검토하며, 같은 그룹의 705장을 그대로 학습시키는 예외는 없다.
- 522장은 목표값이다. 그룹 무결성을 우선하고, 승인된 상품 그룹 때문에 정확한 522장 달성이 불가능하면 실제 fold 크기 및 허용 범위를 사용자에게 확인받은 뒤 계획을 개정·동결한다. 이번에는 크기 허용 범위를 임의 확정하지 않았다.
- `../01_splits/draft`는 파일 해시 그룹에 대한 분할 알고리즘 드라이런이다. 상품 그룹 검수 전이므로 공식 fold나 최종 holdout이 아니다. 이 시점에 최종 fold 5 선정 해시를 확정했다고 주장하지 않는다.
- 최종 공개 manifest에는 정답을 넣지 않으며, fold 5 manifest에는 ID·이미지 경로만 둔다. 정답 잠금은 별도 채점 계정/외부 보관자와 학습 실행 계정의 접근 분리가 확인된 뒤 완료로 판정한다.
- Excel, 승인 주석, recognition/detection export, history, approval snapshot, 과거 trace에 남은 정답도 접근 분리 대상이다. 원본 삭제·이동이나 ACL/계정 변경은 보관자와 범위를 확정하기 전 실행하지 않는다.
- 현재 환경에서 기존에 열람 가능했던 자료를 소급하여 '한 번도 보지 않은 정답'으로 만들 수 없다. 최종 보고에는 기존 705장 노출 및 주석 구축 범위와 잠금 시점을 명시한다.
- 학습 진입점은 공식 분할, 해당 회차 평가 완료, 영구 inner validation, 승인된 crop/라벨 해시, 채점자 분리 확인이 없는 상태에서 실제 학습을 차단한다. 이 검사는 워크플로 게이트이며 운영체제 접근 권한을 대신하지 않는다.
