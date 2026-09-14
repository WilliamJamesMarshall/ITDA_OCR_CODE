# 실험·학습 문서 안내

- `docs/protocol/`: 학습·평가 실행계획, 계약과 정책의 열람용 사본
- `docs/data/`: 데이터·OCR 주석 구축과 승인 보고
- `docs/training/`: CPU 학습 및 환경 안내
- `docs/evaluation/`: 기존 705장·상품 그룹·holdout 관련 문서
- `docs/architecture/`: 기존 추론 설계와 진단 문서
- `reports/round_01` ~ `round_05_final`: 회차별 공개 가능한 결과 요약
- `reports/baselines`, `reports/summary`: 기존 개발 성적 및 누적 비교
- `reports/migration/`: 이번 구조 변경과 보존 검증
- `environment/requirements-train-cpu.lock.txt`: 학습 환경 고정 의존성
- `experiments/`: 실행 결과와 개인정보를 정리한 실험 노트북

주석 JSON·정답 XLSX·crop·checkpoint·샘플별 trace는 이 폴더에 추가하지 않습니다.

현재 실행 정본은 [원본 6회·4단계 규칙](docs/protocol/grouped_6_rounds.md)입니다.
`학습대상데이터` 원본 2,610장을 216/500/500/394/500/500장으로 배정하며 평균 3.2초/장을 목표로 합니다.
기존 경로의 8회·단계별 계획은 역사적 기록입니다. 현재 상태는 [운영 안내](docs/training/grouped_operations.md)의 명령으로 조회합니다.

이동한 `docs/`의 옛 로컬 링크는 호환 연결로 유지됩니다. 새 Git checkout에서는 호환 연결에 의존하지 말고 `notebooks/docs/architecture/`를 사용하세요. Git에는 junction이나 외부 데이터가 포함되지 않습니다.
