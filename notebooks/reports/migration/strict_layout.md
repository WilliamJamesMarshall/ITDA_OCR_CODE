# 엄격 제출 구조 적용 결과

2026-09-12. 이전의 루트 코드 폴더 유지안이 아니라, 요청한 7개 루트 항목만 Git 제출 대상으로 남기는 구조를 적용했다.

```text
predict.ipynb
requirements.txt
README.md
.gitignore
download_weights.sh
notebooks/
  project/{src,scripts,configs,tests}/
  project/run.py
  docs/
  reports/
  experiments/
  environment/
weights/
```

## 변경 및 보존

노트북 첫 CONFIG 셀은 동일하다. 두 번째 셀만 notebooks/project를 import 경로로 연결했다. OCR src는 pipeline.py의 기본 가중치 위치 계산 외에 내용이 동일하다. 학습·평가·검수 도구는 새 코드 루트와 기존 데이터 루트를 구분하도록 경로를 수정했다. 개발 CLI는 `python notebooks/project/run.py scripts.<모듈명>`으로 실행한다.

로컬 8개 데이터·정답지 폴더 10,058파일의 경로·크기·SHA-256 변경은 0건이다. 이 폴더들을 삭제하거나 이동하지 않았다. 주석 2,610장 승인과 검증 오류 0건도 확인했다. Git 제출에는 데이터, 결과, junction, 캐시, 가중치 바이너리가 포함되지 않는다. weights/.gitkeep만 추적하며 가중치는 실행 전 준비한다.

## 검증

- 로컬 및 데이터 없는 제출 사본의 회귀 테스트 303개 통과. 실제 정답지 의존 테스트 2개는 합성 자료 기반 단위검사로 분리했고, 로컬 XLSX/CSV/NDJSON/lock 실제 일치 검사는 별도로 통과했다.
- CPU 학습 preflight 통과: 초기 가중치·문자 사전 해시 일치, 968개 텐서 호환.
- Git index를 별도 ZIP으로 내보내고 깨끗한 디렉터리에 풀어 루트 7개 항목을 확인했다.
- 그 사본에 추론 가중치 파일만 준비하고, 외부 입력·출력 경로를 지정해 nbconvert Run All을 실행했다. 코드/데이터 junction은 사용하지 않았다.
- BMLC002247(기존 개발 노출 자료) 1장 실제 OCR CSV가 이전 구조 결과와 동일했다. 새 holdout은 사용하지 않았다.
- 공식 Linux/4-core 환경, OS 수준 네트워크 차단 및 500장 성능 검증은 수행하지 않았다. 소규모 Windows 회귀 검증을 공식 성능 인증으로 해석하지 않는다.

근거와 복구본: `C:/ITDA_OCR_WORKSPACE/strict-layout-20260912/`. `verification.json`, `training_preflight_verified.json`, `verified-submission.zip`, `verified-clean/`, `verified-executed.ipynb`, `verified-submission.csv`, 변경 전 소스와 보호 파일 manifest가 있다.

## 상태와 다음 단계

로컬 변경과 Git 제출 대상 정리는 완료했다. **커밋·푸시는 수행하지 않았으므로 원격 GitHub 반영 완료와 구분한다.** 이전 커밋의 데이터 노출 이력도 제거하지 않았다.

사용자가 예고한 학습·평가 계획 수정사항을 먼저 반영한 뒤 3단계를 재개한다. 이번 작업으로 새 fold, 잠금, 사용자 승인 또는 실제 학습을 실행하지 않았다. 로컬 데이터 보존 폴더는 탐색기에 계속 보이지만 제출 사본에는 없다.
