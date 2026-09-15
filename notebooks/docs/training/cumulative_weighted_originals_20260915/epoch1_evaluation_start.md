# 원본 수 비례 가중 학습 epoch 1 전수 평가

사용자 지시: “학습이 종료되었으므로 1회~5회 전체 이미지 테스트를 실행한다. 1회는 단독으로 실행한다. 2회와 3회, 4회와 5회를 동시에 묶어서 실행한다.”

전체 4단계 중 현재 3단계다. 이번 작업은 1~5회 누적 개발 평가이며, 최초 결과 덮어쓰기·단계 종료·모델 채택이 아니다.

## 학습 종료와 사용할 후보

- 원본 수 비례 누적 학습은 1 epoch·415 steps·실제 crop 3,316개 소비 검증까지 완료했다. 학습·내부 검증 89.8분.
- 내부 25 crop 결과는 67/75 → 66/75필드로 비퇴행 gate 미통과다. 내부 선정 epoch는 0이다.
- 이번 지시에 따라 새로 학습된 epoch 1 자체를 별도 export하여 평가한다. gate 실패와 미채택 이력을 유지한다.
- checkpoint: `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/cumulative-1-5-original-weighted-20260915-v3/training-run/epoch_001.pdparams`.
- checkpoint SHA-256: `aa4666d0612c2fd45e0208b42a30e9ccf9c5530d7ee1463d32e636ee3aaa9e35`.
- 평가용 한국어 inference.pdiparams SHA-256: `ef4eaeeef756b1c88011605a189433dca7cc6e91481b0cd1daa75e54539460b6`.
- 기존 공용 weights는 그대로다. 검출기·영어 인식기는 시작 bundle과 같다.
- 추론 src와 predict.ipynb는 직전 비가중 후보 전체 평가와 같은 SHA다. 실행 제어는 이번 checkpoint·폴더·실제 지시를 연결하는 별도 진입점을 사용한다.

## 고정 실행과 순서

- 실행 폴더: `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/cumulative-1-5-original-weighted-epoch1-eval-20260915-v1`.
- 실행 release SHA-256: `5872fc63d3a66653c2d41c2200a0d55fbbe041bdb031a8b65aa054b839fad502`.
- `authorization.json`에 실제 지시·checkpoint·온라인 실행 범위·순서를 연결했다. `release.json`에 회차 목록·코드·bundle·정답·보호 파일 해시를 고정했다.
- 합성 입력으로 새 bundle 로딩/출력 유한값을 확인했다. CPU 0~3 및 병행 슬롯 0,1,4,5 / 2,3,6,7에서 온라인 노트북 실행 검증 후 본 테스트를 시작한다. 과거 오프라인 검증으로 이번 모델 검증을 대신하지 않는다.
- 실행 순서: 1회 216장 단독(CPU 0~3) → 2·3회 각 500장 병행 → 4회 394장·5회 500장 병행. 병행 CPU는 0,1,4,5 / 2,3,6,7, 각 4스레드다.
- 한쪽이 먼저 끝나면 그대로 보존하고 재실행하지 않는다. 실패 시 상대 결과도 보존하며 자동 재시도하지 않는다.
- 시작 전 활성 OCR 학습·테스트 작업 없음 확인. 기존 uvicorn 서버는 작업 범위 밖이므로 유지한다. 실행 coordinator는 공유 execution.lock을 소유한다.

## 입력·채점·보존

원본 공급원은 `C:/ITDA_OCR_CODE/학습대상데이터`이며 회차 범위는 기존 216/500/500/394/500장이다. 전체 6회 2,610장 SHA 검증, 중복·누락 0 확인. 이번 1~5회는 2,110개 고유 원본이다. 저장 증강 1,106장은 제외한다. 초기 개발 노출 이력과 기존 상품 그룹 역할을 유지하며 상품 독립성을 주장하지 않는다.

정답 XLSX SHA는 `765db2f4781ec1975893e66b7c3c755f8a68246c68fc05d302597d36900a4d2d`다. 881~1161 및 1117 정정이 반영된 직전 평가의 동일 labels.csv를 사용한다. 정답은 추론 입력에 포함하지 않고 종료 후 채점한다.

정확도는 정답 year/month/day 필드 수 / 3N, NONE 일치는 정답이다. 실패·누락은 분모에 남고 득점하지 않는다. 완전 날짜는 보조 지표다. 시간은 노트북 초기화·CSV 저장·종료 포함이며 목표는 691.2/1600/1600/1260.8/1600초, 강제 종료는 각 2400초다.

회차별 보고서는 `epoch1_evaluation/round_01.md`~`round_05.md`, 종합은 `epoch1_evaluation/summary.md`에 생성한다. 기존 채택 모델과 직전 비가중 누적 후보를 같은 최신 정답으로 비교하고, 저장 trace 기반 오답 분류·후속 원본 학습 검토안을 함께 작성한다. 시각 검증 없이 모든 원인을 확정하지 않는다.

최종 상태는 실행 폴더 `status.json`의 `completed_reports_verified` 및 `final-report-audit.json`으로 확인한다. `summary.json`만 있으면 후속 분석이 남았을 수 있다. 추가 학습·공용 모델 변경·6회·commit/push는 하지 않는다. 2,110장 성적은 누적 개발 성적이며 별도 독립 최종 성적은 없다.
