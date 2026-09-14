# 원본 6회 규칙 변경·검증 기록

2026-09-14 사용자 지시에 따라 테스트·학습 공급원을 `C:/ITDA_OCR_CODE/학습대상데이터`로 통일했다.
정본은 [grouped_6_rounds.md](../protocol/grouped_6_rounds.md), 새 세션용 파일은
[grouped_session_prompts.md](grouped_session_prompts.md)이다.

## 적용 결과

- 정책/작업 공간: `grouped-6-originals-v1`, `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1`.
- 회차 장수: 216/500/500/394/500/500. 총 원본 2,610장, 중복·누락 0.
- 1~3회 사용 원본 1,216장, 그 외 1,394장을 394/500/500장으로 배정했다.
- 순서: 1 → (2·3) → (4·5) → 6. 6회는 CPU 0–3 단독이며 7·8회는 새 실행 대상이 아니다.
- 전체 3.2초/장 목표를 최초 채점·후보 누적 평가·새 2·3회 재시험 기록에 적용했다.
  216장 691.2초, 394장 1,260.8초, 500장 1,600초. 노트북 전체 2,400초 강제 종료는 유지했다.
- 실제 이미지 경로·바이트를 원본에 연결하며 기존 테스트 ID는 출력·이력 별칭으로 보존했다.
  BMLT와 BMLC의 번호가 다른 경우에도 원본 정답으로 올바르게 연결한다.
- 증강 1,106장은 새 입력 목록에서 제외하고 학습 재편입 차단용 해시를 별도 보존했다.
- 최초 보고서·과거 시간 판정·승인·보호 정답·학습 그룹 역할을 이어받았다.
  이관 시 상태는 1회 완료, 2·3회 사용자 검토 대기, 4~6회 미시작이다.
- 기존 작업 공간의 실행 lock도 상태에 표시하고, 생존 작업이 있으면 새 coordinator 실행을 차단한다.

## 검증

전체 원본 2,610장 및 연결된 승인 주석의 SHA-256 검증을 통과했다.
기존 1~3회 목록 순서·원본 대응을 확인했고, 이관 파일 34개와 기존 manifest lock 대상의 변경은 0건이다.
검증 당시 별도 paper_ocr 실험이 이전 작업 공간의 고정 사본으로 실행 중임을 확인했다.
그 실험의 사본·입력·결과와 기존 작업 공간 파일을 수정하지 않았다.

`python notebooks/project/run.py unittest discover -s notebooks/project/tests`: 469개 통과.
변경 관련 검증에는 회차 경계, 216/394/500장 시간 경계값, 누락·실패 판정,
원본 외 입력 차단, 증강 바이트 재편입 차단, 별칭/원본 정답 연결, 이전 실행 lock 처리가 포함된다.
코드·문서 diff 공백 검사도 통과했다.

실제 정식 OCR 테스트나 optimizer 학습을 이번 규칙 변경 작업에서 새로 실행하지 않았다.
이 검증은 규칙·이관의 검증이며 새 모델의 95% 정확도나 처리속도 달성을 의미하지 않는다.

준비 증거: `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/preparation_verification.json`.
이관 원본·해시: `C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/migration.json`.
회차 목록: 같은 작업 공간의 `test_round_01.csv`부터 `test_round_06.csv`까지.
채점 전용 정답: 같은 작업 공간의 `scorer_only/labels.csv`.
