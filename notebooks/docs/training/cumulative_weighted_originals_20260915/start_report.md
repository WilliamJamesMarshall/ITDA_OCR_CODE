# 원본 수 비례 누적 학습 시작

2026-09-15 12:31:35 KST 첫 optimizer 진입을 확인했다. 실제 trainer PID 30256, CPU 0~3(mask 15), 4스레드다. 전체 4단계 중 3단계이며 이번 학습 범위는 1~5회 누적이다. 단계 완료나 모델 채택을 의미하지 않는다.

## 승인·고정 실행

- [승인 계획](approved_plan.md)을 보고 받은 사용자가 “시작해.”라고 지시했다. 새 `instruction.json` 및 `release/authorization.json`에 실제 지시와 계획 SHA를 연결했다.
- 실행 폴더: `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/cumulative-1-5-original-weighted-20260915-v3`.
- release SHA-256: `614215650d52b5b3445e685afcedbbadf897192737663322fede638afe2cf25a`.
- 이전 채택 모델에서 시작. checkpoint SHA-256: `07f23a2059d05d9977969e1f4a8742974376a5e1e47e28f23af7f23f13c611d9`.
- 시작 내부 검증: 67/75필드, 문자열 18/25, CER 4.2471%. 기존 reference와 동일하다.
- 최신 정답 XLSX, 원본 2,110장·승인 주석·crop·그룹 역할 SHA 검증 통과. 3,316개 학습 crop, 내부 검증 25개 유지. 공용 모델은 변경하지 않았다.

## 학습 구성과 사전 검사

- 회차 목표 계수: 216/2110, 500/2110, 500/2110, 394/2110, 500/2110.
- 회차 내 원본별 동등 계수, 원본 안에서는 crop별 평균. 반복 추출 없이 각 crop 한 번.
- 1 epoch, batch 8, 415 steps, LR 5e-6, Adam/Cosine, seed 20260911, BN 통계 고정, 실시간 증강 없음. 한국어 recognizer만 학습.
- 실제 로더 검사: 3,316개 유일 crop, 8개 batch 414회+4개 batch 1회. 회차별 계수 합계 확인. `weighted-loader-check.json`에 보존.
- 단위 검사 589개 통과(23.890초). `unit-tests.log`에 원출력 보존. 실패/timeout 로그 일부는 합성 fixture의 의도된 실패 검사이며 실제 원본 OCR 시험이 아니다.
- v1/v2는 학습 전 준비 사본으로 보존했다. [로더 문제와 보완](loader_findings.md): CRLF 종결자와 NRTR 특수 토큰 공간 문제를 발견했고 원본/전사를 변경하지 않은 어댑터로 보완했다. 실제 optimizer 실행은 v3 한 작업이다.
- 메모리는 실제 trainer와 launcher/자식 프로세스 트리 표본을 구분하여 기록한다. 트리 표본 최대값은 미관측 순간의 절대 최대값을 보장하지 않는다.

## 보류와 종료 기준

전체 이미지 1~5회 테스트, 6회, 공용 weights 변경, 모델 채택, 단계 승격, commit/push는 하지 않는다. 기존 최초 결과·퇴행 후보·승인 기록은 보존한다.

1 epoch 완료 후 내부 비퇴행 gate를 확인하고 통과한 경우만 별도 후보 export한다. 실패 시 checkpoint와 실패 증거를 남기고 추가 epoch를 실행하지 않는다. 25 crop 내부 검증은 전체 2,110장의 성적이 아니다. 최종 결과는 runtime·supervisor·실제 crop 소비 기록·checkpoint를 확인한 후 별도 보고한다.

## 종료 후 보고서 작성 연결

실행 폴더의 `postprocess-code/wait_and_finalize.py`가 이번 supervisor 종료를 기다린 뒤, 고정 SHA의 `finalize.py`로 입력·모델 불변 및 실제 소비 증거를 검사한다. 성공 시 `training-summary.json`과 이 문서 옆 `training_report.md`를 생성한다. 상태는 `postprocess-status.json`, 오류는 `postprocess.stderr.log` 및 `postprocess.log`에 남긴다. 이것은 이번 실행에만 연결된 일회성 마무리 작업이며 새 학습·테스트·자동 재시도는 하지 않는다.
