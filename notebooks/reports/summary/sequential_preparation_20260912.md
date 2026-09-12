# 8회 순차 실행 준비 보고서

> 최초 준비 기록. 이후 1회 그룹 검토와 합성 학습 검증이 추가되었으며, 현재 상태는 [1회 후속 준비 보고서](round1_remaining_work.md)를 우선한다.

2026-09-12. 정식 테스트 0회, optimizer 학습 0회, 사용자 승인 생성 0건.
현재 판정: 준비 구현과 가능한 검증 완료, 정식 1회 시작은 공식 환경 확인 전 차단.
실행 정본은 [8회 실행계획](../../docs/protocol/sequential_8_rounds.md)이다.

## 단계별 결과

| 단계 | 결과 | 남은 조건 |
|---|---|---|
| 1. 기준선 | 보호 파일 10,058개 기록, 과거 정책 백업, Git 시작 상태 clean 확인 | 없음 |
| 2. 정책 전환 | 새 정본 작성, 과거 문서·상태를 구분, 기존 fold 작성 CLI 차단 | 없음 |
| 3. 테스트 목록 | 216+500×7, 3,716장 누락·중복 없음 | 없음 |
| 4. 원본 대응 | 2,610건 SHA-256 직접 연결, 1회 216쌍 전부 일치 | 증강본 1,106건의 파생 원본 확인 |
| 5. 승인 통제 | 실제 지시·시각·보고서·코드·모델·manifest 결합 검사 | 실제 시작/학습 승인은 아직 없음 |
| 6. 누적 학습 | 원본 중복 제거, 그룹 영구 배정, 승인 crop 선택, 1~8회 실행 연결 | 상품 그룹 검토, 실제 epoch 학습 검증 |
| 7. 평가·보고 | 노트북 추론과 scorer 분리, 실패 보고, 원본·노출별 지표 준비 | 공식 환경, 실제 회차 성능 측정 |
| 8. 사전검사 | CPU preflight 및 초기 checkpoint 실제 export·pipeline loading 통과 | 학습된 checkpoint 자체 검증은 미실행 |
| 9. 보존·회귀 | 보호 데이터 변경 0건, 제출 루트 7항목, CONFIG 보존 | 최종 검증 로그 참조 |
| 10. 시작 판정 | 환경 미검증으로 정식 1회 실행 차단 | 공식 자료/실행환경과 사용자 시작 지시 |

## 원본 대응 수량

| 회차 | 테스트 | 직접 원본 연결 | 연결 검토 필요 |
|---|---:|---:|---:|
| 1 | 216 | 216 | 0 |
| 2 | 500 | 500 | 0 |
| 3 | 500 | 337 | 163 |
| 4 | 500 | 280 | 220 |
| 5 | 500 | 273 | 227 |
| 6 | 500 | 272 | 228 |
| 7 | 500 | 286 | 214 |
| 8 | 500 | 446 | 54 |
| 합계 | 3,716 | 2,610 | 1,106 |

증강본 분류는 기존 제외 이력과 사용자 데이터 정책에 따른다.
기존 출처 manifest는 테스트 파일과 수집 이미지를 연결하지만, 증강본을 만들어낸 원본 관계는 제공하지 않는다.
번호·유사도만으로 원본 연결을 확정하지 않았다. 기존 상품 그룹 pair_decisions는 비어 있었다.
따라서 현재 SHA 그룹을 완성된 상품 그룹으로 취급하지 않는다.

## 확인한 환경과 범위

- 학습 Python 3.10.20, Paddle 3.2.2 CPU, 초기 가중치·문자 사전 해시 일치, 968개 텐서 호환.
- 추론 Python 3.10.20, PaddleOCR 3.7.0, PaddleX 3.7.2, nbconvert 7.16.4.
- 학습 환경에서 전체 회귀검사 1건은 PaddleX 부재로 실행되지 않았다. 추론 환경에서 기존 303개 통과 확인.
- 신규 정책 검사 15개를 포함한 총 318개가 로컬 및 정답 없는 제출 사본에서 통과했다.
- 초기 학습 checkpoint를 실제 inference 파일로 export하고 BMLC002247 기존 개발 노출 자료로 파이프라인 로딩 확인.
- 이 모델을 정식 1회 모델로 교체하지 않았다. 현행 weights/paddle을 별도 해시로 고정한다.
- 원본 predict.ipynb Run All은 기존 개발 노출 1장으로 통과했고, CSV는 이전 검증 결과와 동일했다.
- 실제 optimizer 학습·epoch별 선택·early stopping·학습 모델 promotion은 이번 작업에서 실행하지 않았다.
- 공식 Notion 자료를 가져오지 못했고 검색에서도 근거를 확보하지 못했다. 최신 조건을 확인했다고 표시하지 않는다.
- WSL 설치 배포판 및 Docker 사용 환경을 확인하지 못했다. Linux/4-core와 OS 네트워크 차단 검증 미완료.
- 500장 시간이나 정확도 95% 목표를 인증한 상태가 아니다.

## 자료 위치

외부 작업 폴더: `C:/ITDA_OCR_WORKSPACE/sequential-8-rounds`.
baseline.json, preservation.json, manifest_lock.json, test_round_01~08.csv,
test_to_original_mapping.csv, mapping_review_queue.csv, round_summary.json,
training_preflight.json, initial-export-loading.json, clean-regression.log,
label-verification.log, preparation_verification.json, execution_readiness.json에 근거를 보관한다.
scorer_only/labels.csv는 승인된 기존 날짜 3,716건을 복사한 scorer 전용 자료이며 추론 사본에 포함하지 않는다.
XLSX·기존 CSV/NDJSON/lock 정합성 검사는 bundled Python의 openpyxl 환경에서 통과했다.

보호 대상 8개 폴더와 주석의 기존 일괄 승인 이력을 보존했다.
이번 세션에서 커밋·푸시·Git 이력 변경은 수행하지 않았다.
