# 제출 저장소 구조 점검 및 수정계획

점검일: 2026-09-12. 이번 작업은 조사·계획 작성만 수행했다. 파일 이동, 추론 코드 변경, Git 커밋·푸시·원격 변경, 3~5단계 실행, 실제 학습은 수행하지 않았다. 저장소 이름 변경은 범위에서 제외한다.

## 1. 결론

현재 프로젝트는 루트의 필수 파일을 갖추었지만, 제시된 7개 항목만으로 구성되지는 않았다. 폴더를 재배치하는 것 자체가 모델 정확도를 낮추지는 않지만, 현재 코드를 그대로 두고 폴더만 이동하면 import·가중치·학습 설정·승인 자료 경로가 깨진다. 특히 `src/`를 삭제하면 현재 노트북은 실행되지 않는다.

권장 우선순위는 **필수 제출 진입점을 유지하고 실행 의존성을 보존하는 것**이다. 템플릿 README에는 `src/`, `scripts/`, `docs/` 추가 금지라는 명시적 규정이 없다. 다만 이것이 운영진의 별도 규정까지 확인했다는 뜻은 아니다. 아래에 저위험 확장형과 요청한 루트 7항목에 맞춘 엄격형을 구분해 제시한다. 어느 경우든 코드·문서와 데이터·정답·실험 바이너리를 분리한다.

이번 확인에서 현재 로컬 회귀 테스트 **301개가 통과**했다. 이는 변경 전 기준선이며, 구조 변경 후 실제 OCR 정확도·시간·학습 재현성이 보장됐다는 결과는 아니다. 변경 전후 실제 모델 비교는 아직 수행하지 않았다.

## 2. GitHub와 로컬은 구분해야 한다

### 확인한 원격

- 사용자가 제시한 [공식 템플릿](https://github.com/b9511242000-blip/itda-ocr-template): 운영진 저장소. 실제 루트에는 `.gitignore`, `README.md`, `predict.ipynb`, `requirements.txt` 네 파일이 있다. 나머지 세 항목은 선택 사항으로 안내한다.
- 현재 로컬 `origin`: [WilliamJamesMarshall/ITDA_OCR_CODE](https://github.com/WilliamJamesMarshall/ITDA_OCR_CODE). GitHub API로 public/main 및 트리를 확인했다.
- 점검한 원격 HEAD와 로컬 HEAD는 모두 `7e76c7ae09829f6e5749601fc712bc5eb35435c7`이다. 그러나 로컬에는 수정·미추적 작업이 다수 있으므로 **작업 폴더 내용 전체가 GitHub에 올라갔다는 뜻은 아니다**.

현재 팀 원격의 루트 항목:

```text
.codex-tmp/  .git-session.json  .gitattributes  .githooks/
.gitignore  Harness_README.md  README.md  download_weights.sh
predict.ipynb  requirements.txt
src/  scripts/  tests/  docs/  artifacts/  labels/
상품사진_정답지/  추가수집_정답지/  테스트용_정답지/  학습대상_정답지/
```

| 제출 항목 | 팀 GitHub 현재 상태 | 조치 |
|---|---|---|
| predict.ipynb | 루트에 존재 | 위치·첫 CONFIG 셀 보존 |
| requirements.txt | 루트에 존재 | CPU 추론 의존성 유지 |
| README.md | 루트에 존재 | 채점용 가이드 중심으로 정리 |
| .gitignore | 루트에 존재 | Paddle 가중치·산출물·정답 제외 보강 |
| download_weights.sh | 루트에 존재 | 다운로드 위치와 SHA 검증 보존 |
| notebooks/ | 원격 트리에 없음 | 실험·보고서 위치로 신설 가능 |
| weights/ | 원격 추적 파일 없음 | 선택 폴더이므로 부적합 사유 아님; 다운로드 시 생성 |

`configs/`, `requirements-train-cpu.lock.txt`, 주석·학습 관련 신규 스크립트와 `학습 및 테스트 결과/` 등은 현재 로컬에서 미추적 상태다. 추후 제출 시 예전 커밋만 복제하면 최신 2단계 결과와 학습 코드가 재현되지 않는다. 반대로 이 폴더들을 무차별 커밋해서도 안 된다.

### 공식 실행 계약

[공식 README](https://github.com/b9511242000-blip/itda-ocr-template/blob/main/README.md)에 따르면 입력·출력은 `ITDA_INPUT_DIR`, `ITDA_OUTPUT_PATH`로 전달하고, 4-core CPU에서 `predict.ipynb`를 nbconvert로 실행한다. 제한은 2,400초이며 추론 중 인터넷은 차단된다. 가중치는 사전 준비해야 하고 첫 CONFIG 셀을 변경하면 안 된다. 미인식 `final_date`는 `NONE`이다. 구조 정리 과정에서도 이 계약을 유지한다.

## 3. 성능과 실행에 영향을 주는 실제 의존성

| 현재 근거 | 단순 이동 시 위험 | 보존·수정 방식 |
|---|---|---|
| predict.ipynb 두 번째 셀의 `from src.pipeline import run_pipeline` | src 삭제/이동 시 ModuleNotFoundError | src 유지 또는 두 번째 셀에서 새 코드 루트 연결; 첫 CONFIG 셀은 그대로 |
| src/pipeline.py의 `Path(__file__).resolve().parents[1] / weights/paddle` | 소스 깊이가 바뀌면 다른 weights 경로 검색 | 코드 루트와 저장소 루트를 분리하고 가중치 위치를 명시 |
| download_weights.sh의 스크립트 위치 기준 weights/paddle | 다운로드와 로딩 위치 불일치 | 루트 스크립트 유지, 실제 4종 모델 경로 일치 검사 |
| scripts/train_recognition_cpu.py의 ROOT/RUNTIME/CHECKPOINT/CONFIG | 학습 런타임·초기 가중치·문자 사전·설정 탐색 실패 | 별도 경로 설정과 이동 전후 사전검사 |
| configs/training/*.yml의 상대 경로 | 실행 cwd가 달라져 다른 출력·라벨 사용 | 실행 cwd 고정 및 해석된 절대 경로 검사 |
| ocr_annotations.py와 training_release_gate.py의 `학습 및 테스트 결과` 참조 | 승인 풀·release gate가 자료를 못 찾음 | 중앙 WORK_ROOT를 사용하도록 관련 도구를 함께 변경 |
| recognition_pool.jsonl의 절대 crop_path와 record_sha256 | 다른 PC에서 파일 없음 또는 검증 실패 | 기존 증거는 불변 보관, 새 경로용 manifest/내보내기 버전 생성 |
| split manifest·source_mapping·inventory·이전 승인 snapshot | 문자열 치환 시 문서 해시 및 provenance 변경 | 경로 변환표 작성, 원본 이미지 해시는 유지, 전후 manifest 해시를 각각 기록 |
| 테스트의 프로젝트 루트 기준 notebook/config 접근 | 코드가 정상이어도 테스트 탐색 실패 | 테스트 경로도 함께 수정, 테스트 의미와 기준값은 유지 |

정확도는 동일 이미지 바이트, 모델 파일, 문자 사전, 전처리, 임계값, 파서, 설정을 유지하면 구조만으로 달라질 이유가 없다. 그러나 경로 오류로 다른 모델을 읽거나 복구 모델이 빠지면 날짜 결과가 바뀔 수 있다. 일부 지연 복구 경로는 오류를 기록하고 계속 진행하므로 **실행이 끝났다는 사실만으로 동등성을 판단하지 않는다**.

추론 시간은 같은 로컬 저장장치의 폴더 이름 변경보다는 모델 초기화, I/O, 라이브러리·스레드 설정에 영향을 받는다. 데이터를 네트워크 드라이브로 옮기거나 매 추론 때 압축을 푸는 구조는 피한다. 학습도 동일 seed만으로 모든 수치가 반드시 비트 단위 동일하다고 주장하지 않는다. CPU 병렬 계산과 실행 환경을 함께 고정해 비교해야 한다.

## 4. 목표 구조

### A. 권장: 제출 필수 구조 + 코드 폴더 보존

```text
<저장소>/
├── predict.ipynb
├── requirements.txt
├── README.md
├── .gitignore
├── download_weights.sh
├── weights/                    # 바이너리 제외; 사전 다운로드
├── src/                        # 현재 추론 모듈 유지
├── scripts/                    # 재현 가능한 학습·평가·검증 도구
├── configs/                    # 공개 가능한 고정 설정
├── tests/                      # 합성 fixture 중심 회귀 검사
└── notebooks/
    ├── experiments/            # 분석/실험 ipynb; 출력 정리
    ├── docs/
    │   ├── protocol/           # 실행 계약, 지표 정의, 단계별 계획
    │   ├── data/               # 데이터·주석 정책과 완료 보고(정답 제외)
    │   ├── training/           # CPU 학습법, 초기 가중치·checkpoint 규칙
    │   ├── evaluation/         # 평가법, 노출 705장 정책, holdout 접근 규칙
    │   └── architecture/       # 기존 파이프라인 진단/설계 문서
    ├── reports/
    │   ├── baselines/          # 기존 점수: 개발 진단임을 명시
    │   ├── round_01/ ... round_04/
    │   ├── round_05_final/     # 최종 평가 해제 후 공개 가능한 요약만
    │   ├── summary/            # 누적 비교, 혼동 유형, CPU 시간
    │   └── migration/          # 구조 변경 전후 검증 결과
    └── environment/
        └── requirements-train-cpu.lock.txt
```

이 방식은 현재 src의 깊이와 import를 유지하므로 위험과 변경량이 작다. 제시된 목록을 **유일하게 허용된 항목 목록**으로 적용해야 한다면 B를 선택한다. 추가 폴더의 공식 허용 여부는 README만으로 단정하지 않는다.

### B. 루트를 제시된 7개 항목으로 제한하는 경우

```text
<저장소>/
├── predict.ipynb
├── requirements.txt
├── README.md
├── .gitignore
├── download_weights.sh
├── weights/
└── notebooks/
    ├── project/
    │   ├── src/
    │   ├── scripts/
    │   ├── configs/
    │   └── tests/
    ├── experiments/
    ├── docs/                   # A와 동일한 문서 분류
    ├── reports/                # A와 동일한 회차별 보고서 분류
    └── environment/
```

B는 소스코드를 삭제하거나 거대한 노트북에 복사하는 방식이 아니다. 노트북의 두 번째 셀에서 `notebooks/project`를 코드 탐색 경로에 추가하고 기존 `src.pipeline`을 호출하는 방식으로 설계한다. `CODE_ROOT`, `REPO_ROOT`, 외부 `WORK_ROOT`를 분리해야 한다. import를 실제로 사용하는 실행 파일은 notebooks 아래에 있어도 추론 의존성이므로 반드시 제출해야 한다. “실험 노트북이 채점 대상 아님”을 “그 안의 코드는 자동으로 실행되거나 필요 없음”으로 해석하면 안 된다.

실험 코드 위치를 추론 코드 위치로도 사용하는 B는 A보다 관리·검증 부담이 크다. 공식 제한이 아니라 외형 정리 목적이라면 A를 권장한다. 어느 안도 전체 파이프라인을 노트북 한 파일로 합치거나, 추론 중 GitHub에서 코드를 내려받거나, import 실패 시 임의 모델로 대체하지 않는다.

## 5. 데이터·학습 결과·문서를 어디에 보관할 것인가

저장소 밖의 **별도 작업 저장소**를 둔다. 예시 경로는 `C:/ITDA_OCR_WORKSPACE`이며 아직 생성하거나 이동하지 않았다. 노트북 채점 입력은 이 경로를 사용하지 않고 기존 환경변수만 따른다.

```text
<WORK_ROOT>/
├── data/                       # 원본 이미지, 학습 복사본, XLSX, provenance
├── workspace/
│   ├── 00_protocol/            # inventory·정답 JSONL 포함 비공개 실행 자료
│   ├── 01_splits/              # ID/path/group/fold와 검사 증거
│   ├── 02_annotations/         # 2,610 레코드, 승인 snapshot/history, crop exports
│   ├── 03_existing_705_policy/
│   ├── 04_group_review/
│   └── 05_holdout_lock/        # 잠금 상태/해시만; 평문 정답 아님
├── runs/<run_id>/
│   ├── round_01/ ... round_04/ # predictions, trace, metrics, 로그
│   ├── round_05_final/         # 해제 절차 후 평가 결과
│   └── models/                # 회차별 checkpoint·optimizer 상태
├── training_runtime/           # 고정 PaddleOCR 외부 런타임
└── archive/                    # 과거 산출물과 이전 경로 증거; 읽기 전용 백업
```

**fold 5 정답과 복호화 키는 위 학습 계정이 접근 가능한 WORK_ROOT에도 두지 않는다.** 별도 scorer 계정/저장소·ACL 또는 scorer만 가진 키로 관리한다. 폴더 이름을 `locked`로 바꾸거나 경로를 전달하지 않는 것만으로 물리적 잠금이 되지 않는다.

| 현재 내용 | Git에 보관할 내용 | 외부에 보관할 내용 |
|---|---|---|
| 학습_및_평가_실행계획.md, execution_policy.md | notebooks/docs/protocol | 과거 원본 버전 백업 |
| 0~2단계 완료 보고, 주석 스키마·검수법 | notebooks/docs/data | 실제 정답·원문·polygon·승인 기록 |
| 705장 처리 및 그룹/fold 정책 | notebooks/docs/evaluation | 상세 이미지 연결표·그룹 후보 사진 |
| 학습 설정·seed·초기 가중치 해시·문자 사전 버전 | configs 및 notebooks/docs/training | checkpoint·환경 설치물 |
| 회차별 학습 및 평가 보고 | notebooks/reports/round_XX | 원본 로그·샘플 예측 CSV·OCR trace·오류 이미지 |
| 문자열 완전일치, micro CER, NED similarity | 공개 가능한 집계표 JSON/CSV/MD | 이미지별 정답·예측 대응표 |
| 검출 precision/recall/Hmean, 유형별 recall | 공개 가능한 집계표와 측정 조건 | polygon별 대응 결과·시각화 |
| 최종 날짜 완전일치·CPU 시간·p50/p95 | 집계 보고 및 측정 환경 | trace와 전체 실행 산출물 |
| 최종 checkpoint 선택 근거 | inner validation 기준·선택표 | 모든 epoch checkpoint 및 상태 |
| fold 5 결과 | 정해진 해제 이후 최종 보고서 | 해제 전 모든 정답과 샘플별 자료 |
| 기존 artifacts/, labels/, .codex-tmp/ | 선별한 역사적 요약만 | XLSX·이미지·캐시·원시 산출물 |

공개 run 요약에는 코드 commit, 설정/가중치/데이터·split manifest 해시, seed, 라이브러리 버전, CPU 스레드·장비, 실행 명령, checkpoint 선택 근거, 결과 파일 참조를 남긴다. 외부 보관 위치는 다른 PC에서도 해석 가능한 논리적 URI/상대 경로와 해시로 관리한다. 노트북 출력이나 Markdown 이미지에 정답·상품 사진이 포함돼 있으면 문서라는 이유만으로 공개하지 않는다.

## 6. 공개 정답과 Git 이력: 3~5단계 전에 처리할 별도 위험

현재 공개 팀 원격의 트리에 정답 XLSX 및 일부 검증 스크린샷이 있다. `labels/tools/node_modules`의 일부 파일도 추적된다. `.gitignore`는 이미 추적된 파일이나 이전 커밋에서 해당 내용을 제거하지 않는다.

따라서 다음을 구분한다.

1. 향후 실수 커밋 방지: 데이터·정답·원문 trace·runs·환경·Paddle의 `.pdparams`, `.pdiparams`, `.pdopt` 등을 제외한다. 현재 `weights/*`는 해당 폴더 안 가중치를 막지만 폴더 밖의 `.pdparams`는 막지 못했다. 필요한 소스·설정 JSON까지 일괄 제외하지 않는다.
2. 현재 추적 파일 정리: 안전한 백업과 재현용 manifest 후 필요한 파일만 추적 해제한다. 로컬 원본 삭제와 구분한다. 이 작업은 아직 하지 않았다.
3. 과거 공개 이력: 이력 정리나 별도의 깨끗한 제출 이력이 필요한지는 별도 승인 후 결정한다. force push나 저장소 교체는 이번 조사에 포함하지 않는다. 이미 공개·복제된 자료를 되돌렸다고 보장할 수 없다.
4. 평가 해석: 기존 705장 외 1,905장이라는 분류는 **기존 파이프라인 개발 사용 여부**의 구분이다. 정답이 공개되었거나 주석 구축·검토에 사용된 사실까지 없애지는 못한다. 향후 fold 5는 “과거부터 누구도 보지 않은 비공개 데이터”가 아니라, 실제 노출 범위를 기록한 뒤 잠금 시점 이후 튜닝에서 배제하는 내부 holdout으로 설명해야 한다. 이것만으로 모든 1,905장이 학습에 이미 사용됐다고 단정하지도 않는다.

인용된 3~5단계 원칙은 유지한다. 705장과 같은 상품 그룹은 fold 5 후보에서 배제하고, 그룹을 쪼개 정확히 522장을 맞추지 않는다. 기존 705장 점수는 개발 진단이며 독립 평가값으로 쓰지 않는다. 테스트용데이터와 학습대상데이터의 중복도 폴더 이동으로 해소되지 않는다. 폴더 이름이나 정답 파일 분리는 데이터 독립성을 만들어 주지 않는다.

현재 로컬에 3~5단계 준비 스크립트/폴더가 이미 존재하지만, 이를 이번 턴에서 실행하지 않았다. 기존 `05_holdout_lock/lock_readiness.json`도 물리적 잠금 미완료 및 scorer 접근 미검증 상태다.

## 7. 실제 수정 순서와 통과 조건

1. **현재 상태 동결:** dirty worktree 포함 코드, 2,610 승인 레코드, XLSX, 모델, 설정과 내보내기 snapshot을 백업한다. 변경 전 구조·경로·SHA-256 매핑표를 만든다. 기존 기록을 덮어쓰지 않는다.
2. **대상 확정:** 추가 코드 폴더 허용이면 A, 루트 7개만 필요하면 B. 데이터/산출물 공개 범위와 scorer 보관처를 확정한다. 이력 재작성은 별도 승인 항목이다.
3. **경로 의존성 분리:** 코드/저장소/작업/모델 루트를 구분한다. 추론의 INPUT_DIR·OUTPUT_PATH 계약은 그대로 유지한다. 학습용 외부 경로를 추론 필수 의존성으로 만들지 않는다.
4. **문서와 소스 이동:** 작고 검증 가능한 단위로 이동한다. 모든 imports, CLI 예시, README 링크, 테스트 탐색, 설정 경로를 갱신한다. 파일 형식·인코딩·전처리·모델 선택 로직은 변경하지 않는다.
5. **자료 연결 재발행:** 기존 snapshot과 해시는 불변 보관한다. 이동된 자료의 이미지 바이트 해시를 검증하고 새 manifest/내보내기 버전을 만든다. 승인 대상 내용은 유지하고 새 경로·레코드 직렬화 해시와 이전 해시의 연결을 기록한다. 과거 승인 해시를 몰래 새 값으로 바꾸거나 원본 판독 승인을 AI가 새로 만들지 않는다.
6. **커밋 대상 점검:** 소스·설정·요약 문서 allowlist 검사. 추적 데이터·정답·가중치·임시파일 확인 후 정리한다. 깨끗한 checkout만으로 코드 설치가 되는지 검증한다.
7. **변경 전후 회귀 비교:** 아래 검증을 통과해야 구조 변경 완료로 판정한다.
8. **그 후 3단계 재개:** 705장 정책, 상품 그룹/fold, scorer 잠금 순서로 진행한다. 구조 변경 검증에 fold 5나 아직 평가하지 않은 다음 fold를 새로 사용하지 않는다.

### 구조 변경 후 검증 항목

- 현재 301개 회귀 테스트 및 신규 경로/import 테스트 통과. 테스트 수만 유지하는 것이 아니라 동일 계약 검증을 유지한다.
- 필수 네 루트 파일, 첫 CONFIG 셀, CSV 5개 컬럼, `NONE`, 모든 입력에 대한 출력 행과 image_id 일치.
- 빈 캐시에 의존하지 않는 사전 가중치 준비, 4종 모델과 각 inference 파일의 SHA-256 일치.
- 격리된 깨끗한 Linux/4-core CPU 환경에서 공식 nbconvert 명령으로 Run All 완주. 입력/출력은 저장소 밖 경로도 시험하고 Windows 절대 경로 의존성이 없어야 한다. 네트워크 차단을 실제로 적용하며 GPU나 사용자 입력을 요구하지 않아야 한다.
- 이미 개발에 사용된 고정 표본에서 변경 전후 `submission.csv` 날짜 결과 전부 일치, 오류·누락·복구 패스와 모델 선택이 의도치 않게 바뀌지 않음. 새 holdout을 구조 검증에 사용하지 않음.
- 같은 장비에서 cold/warm 조건을 구분해 최소 3회 CPU 시간 비교. 예컨대 중앙값 5% 초과 악화는 조사 기준으로 미리 정하되, 이것은 공식 규정이 아닌 내부 회귀 기준이다. 공식 최대 2,400초 만족 여부는 별도로 검증한다.
- 승인 2,610건, 중복/누락 0건, 이미지·초기 가중치 해시 일치, 인식·검출 풀 수량과 제외 사유가 이동 전과 동일. 현재 2단계 기준은 인식 crop 3,103개, 검출 장면 2,610개, 인식 제외 영역 86개다.
- CPU 학습 preflight 및 합성 데이터 스모크 검사로 설정·사전·초기 가중치·저장 경로를 확인한다. 실제 2,610장 학습은 3~5단계 gate 통과 전 실행하지 않는다. 모델 재학습 결과 자체를 이번 폴더 정리의 범위로 삼지 않는다.
- 실패하면 이전 코드/설정과 경로 매핑으로 복귀할 수 있어야 한다. 원본·승인 이력과 이전 산출물을 먼저 삭제하지 않는다.

## 8. 조사 근거

- 공식 저장소 및 실행 규정: https://github.com/b9511242000-blip/itda-ocr-template/blob/main/README.md
- 팀 원격 기준 트리: https://github.com/WilliamJamesMarshall/ITDA_OCR_CODE/tree/7e76c7ae09829f6e5749601fc712bc5eb35435c7
- 로컬: `predict.ipynb`, `src/pipeline.py`, `download_weights.sh`, `.gitignore`.
- 학습/자료 경로: `scripts/train_recognition_cpu.py`, `scripts/training_release_gate.py`, `scripts/ocr_annotations.py`, `configs/training/korean_PP-OCRv5_mobile_rec_cpu.yml`.
- 승인 완료 근거: `학습 및 테스트 결과/02_annotations/stage2_closeout.json`.
- 잠금 현황: `학습 및 테스트 결과/05_holdout_lock/lock_readiness.json`.
- 이번 기준선 명령: `.labeling_paddle_env/Scripts/python.exe -m unittest discover -s tests -q` → 301 tests, OK.

최종 판단: **현재는 필수 진입점 충족, 정확한 외형 일치는 아님. 계획적으로 경로를 수정하면 구조만으로 성능이 손상될 이유는 없으나, 검증 전 성능 무손실을 확정할 수 없다.**
