# ITDA 소비기한 OCR

상품 뒷면 이미지에서 소비기한을 추출하여 `submission.csv`로 저장하는 CPU 전용 추론 파이프라인입니다. 운영진이 주입한 입력·출력 환경변수를 읽고 `predict.ipynb`를 처음부터 끝까지 실행합니다. 추론 중 가중치 다운로드, 외부 API 호출, GPU 또는 사용자 입력이 필요하지 않습니다.

## 채점 환경

| 항목 | 운영진 안내 기준 |
| --- | --- |
| OS | Ubuntu 22.04 LTS, x86_64 |
| Python | 3.10 |
| CPU / RAM | 4코어 / 8GB |
| GPU | 미제공 |
| 네트워크 | 추론 시 인터넷 차단 |
| 패키지 | 팀별 독립 venv에 `requirements.txt` 설치 |
| 평가 입력 | 운영진이 별도로 구성한 비공개 이미지 500장 |
| 실행 한도 | 노트북 Run All 2,400초 |

패키지 설치와 가중치 준비는 추론 전에 수행하며, 운영진 안내에 따라 속도 평가 시간에서 제외됩니다.

## 제출 저장소 구조

```text
ITDA_OCR_CODE/
├── predict.ipynb           # 채점용 메인 추론 노트북
├── requirements.txt        # 버전을 고정한 실행 패키지
├── README.md               # 설치·가중치 준비·실행 안내
├── .gitignore              # 가중치·로컬 데이터·결과 추적 제외
├── .gitattributes          # 셸 스크립트 LF 줄바꿈 등
├── download_weights.sh     # 온라인 사전 가중치 다운로드
├── weights/                # 다운로드한 모델과 모델 manifest
├── notebooks/              # 개발 소스·테스트·실험 문서
└── custom_data/             # 추가 수집 데이터·라벨·출처
```

채점용 추론 코드는 `predict.ipynb`에 포함되어 있습니다. `notebooks/project/`는 개발·테스트용 소스이며, 채점 노트북은 로컬 학습 폴더나 정답 파일을 읽지 않습니다. 가중치는 Git 추적에서 제외하고 다운로드 스크립트로 준비합니다. 과거 커밋 이력에는 이전에 커밋한 모델 파일이 남아 있습니다.

## 환경 설치 — 온라인 준비

새 폴더에 clone하고 제출한 커밋을 checkout한 뒤, 저장소 루트에서 실행합니다.

```bash
git clone https://github.com/WilliamJamesMarshall/ITDA_OCR_CODE.git
cd ITDA_OCR_CODE
# 특정 제출 버전을 검증할 때: git checkout <제출 커밋 해시>
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

패키지 버전의 기준은 [requirements.txt](requirements.txt)이며, 노트북 실행에 필요한 `nbconvert`와 `ipykernel`도 포함합니다. Ubuntu에는 Python 3.10의 venv 지원과 다운로드용 `curl` 또는 `wget`, SHA-256 유틸리티가 필요합니다. OpenCV가 요구하는 시스템 라이브러리는 `libgl1`, `libglib2.0-0`입니다. 재현용 [Dockerfile](notebooks/environment/grading/Dockerfile)에 시스템 패키지 구성을 명시했습니다.

## 가중치 다운로드 — 온라인 준비

인터넷이 연결된 상태에서 노트북 실행 전에 한 번 수행합니다.

```bash
bash download_weights.sh
```

스크립트에는 실행 권한이 등록되어 있어 `./download_weights.sh`로도 실행할 수 있습니다.

| 모델 | 다운로드 출처 |
| --- | --- |
| `korean_PP-OCRv5_mobile_rec` | 6회차 최종실험 후 채택한 모델의 [고정 Release](https://github.com/WilliamJamesMarshall/ITDA_OCR_CODE/releases/tag/adopted-recognizer-final-round6-20260915) |
| `PP-OCRv5_mobile_det` | PaddlePaddle 공식 Hugging Face 저장소, 고정 revision |
| `PP-OCRv6_small_det` | PaddlePaddle 공식 Hugging Face 저장소, 고정 revision |
| `en_PP-OCRv5_mobile_rec` | PaddlePaddle 공식 Hugging Face 저장소, 고정 revision |

각 모델은 `weights/paddle/<모델명>/` 아래 `inference.json`, `inference.pdiparams`, `inference.yml` 3개 파일로 구성됩니다. 총 12개 파일의 SHA-256을 스크립트에서 검증합니다. 이미 올바른 파일이 있으면 재사용하고, 다운로드 또는 검증에 실패하면 중단합니다. 채택한 한국어 모델을 다른 공개 모델로 대체하지 않습니다.

정확한 URL·revision·해시는 [download_weights.sh](download_weights.sh)와 [모델 manifest](weights/adopted_model.json)를 참조하세요. 추론 코드는 준비된 로컬 모델 경로를 명시하고 모델 소스 확인을 비활성화합니다.

## 공식 추론 실행 — 오프라인

가중치 준비를 마친 뒤 네트워크를 차단하고, 가상환경이 활성화된 저장소 루트에서 실행합니다. 첫 CONFIG 셀의 환경변수 읽기 코드는 수정하지 않습니다.

```bash
export ITDA_INPUT_DIR=./val_images
export ITDA_OUTPUT_PATH=./submission.csv

jupyter nbconvert --to notebook --execute predict.ipynb \
  --ExecutePreprocessor.timeout=2400 \
  --output /tmp/executed.ipynb
```

위 경로는 예시입니다. 운영진이 지정한 환경변수 값이 우선하며, `./val_images`와 `./submission.csv`는 환경변수가 없을 때의 기본값입니다. `/tmp/executed.ipynb`는 실행 기록 노트북으로, 채점 CSV의 저장 경로와는 별개입니다.

## 입력·출력 규격

### 입력

- `ITDA_INPUT_DIR`는 평가 이미지가 들어 있는 폴더입니다.
- 폴더 바로 아래의 `.jpg`, `.jpeg`, `.png` 파일을 읽으며 확장자의 대소문자를 구분하지 않습니다. 하위 폴더는 탐색하지 않습니다.
- 노트북은 입력 장수나 특정 파일명을 고정하지 않습니다. 운영진 평가의 정상 완료 결과는 입력 500장에 대응하는 500행입니다.
- `image_id`는 확장자를 제거한 파일명 그대로이며, `000001` 같은 선행 0도 유지합니다.

### 출력

`ITDA_OUTPUT_PATH`는 디렉터리가 아닌 **출력 파일의 전체 경로**입니다. 예를 들어 `/output/submission.csv`를 주입하면 해당 위치에 `submission.csv`를 생성하며, 없는 상위 폴더는 생성합니다. 출력 위치에는 쓰기 권한이 필요합니다.

CSV는 UTF-8로 저장하며 인덱스 열 없이 다음 5개 열을 순서대로 사용합니다.

```csv
image_id,year,month,day,final_date
000001,2026,05,29,2026-05-29
000002,NONE,11,29,NONE-11-29
000003,2026,05,NONE,2026-05-NONE
000004,NONE,NONE,NONE,NONE
```

- `year`: 4자리 문자열 또는 `NONE`.
- `month`, `day`: 각각 2자리 문자열 또는 `NONE`.
- `final_date`: 인식된 필드를 하이픈으로 연결합니다. 세 필드가 모두 미인식이면 `NONE`입니다.
- 부분 날짜의 누락 필드를 `NONE`으로 유지하고 `final_date`에 결합하는 형식은 운영진과의 개별 질의응답을 반영한 규칙입니다.
- 누락 숫자를 임의로 채우지 않습니다. 달력 유효성을 검증하며 코드의 유효 연도 상한은 **2099**입니다. 날짜가 과거라는 이유만으로 거부하지 않습니다.

CSV를 검증할 때는 문자열로 읽어 ID의 선행 0과 월·일의 두 자리 형식을 보존하세요.

## 완료 조건과 실패 시 동작

- 전체 입력의 기본 OCR을 완료하면 최종 CSV를 생성하고 조건부 복구 결과를 반영합니다.
- 기본 OCR 처리 실패가 있거나 전체 입력 처리를 완료하지 못하면 최종 CSV를 생성하지 않고 부분 결과와 실패 기록을 남깁니다. 처리 실패와 정상적인 날짜 미인식은 다릅니다.
- 복구 단계 오류가 발생하면 이미 생성된 CSV가 남을 수 있으므로, 파일 존재만으로 정상 완료를 판정하지 않습니다.
- 필수 기본 모델이 없으면 초기화 오류가 발생합니다. 지연 초기화하는 복구 모델이 없으면 해당 복구 오류를 기록합니다. 추론 중 모델을 다운로드하지 않습니다.
- 빈 입력 폴더 또는 확장자 제거 후 중복된 ID는 오류로 처리합니다.
- 같은 출력 경로의 CSV나 관련 기록 파일이 이미 존재하면 재실행을 거부합니다. 실행마다 새 출력 경로를 사용하세요.

CSV 옆에 `.partial.csv`, `.progress.jsonl`, `.status.json`, `.trace.jsonl` 기록이 생성됩니다. 채점 제출값은 `ITDA_OUTPUT_PATH`의 CSV이며, 부가 기록은 완료 여부와 오류 확인용입니다.

## 오프라인 재현성 검증

제출 커밋을 새로 clone한 환경에서 다음 순서로 확인합니다.

1. Python 3.10 venv를 만들고 `requirements.txt`를 설치합니다.
2. 온라인 상태에서 `download_weights.sh`를 실행하고 모든 해시 검증이 성공했는지 확인합니다.
3. 네트워크를 차단합니다.
4. 평가 입력 폴더와 새 출력 파일 경로를 환경변수로 주입합니다.
5. 위 공식 `nbconvert` 명령으로 Run All을 실행합니다.
6. CSV가 지정한 경로에 생성됐는지, 5열 순서·500행·중복 없는 입력 ID 일치·승인된 날짜 형식을 확인합니다.
7. `.status.json`의 `output_complete`, `processed_images`, `failures`와 프로세스 종료 결과를 확인합니다. 500장 처리 완료, 오류 없음, 실행 한도 준수 및 메모리 초과 종료가 없음을 확인해야 합니다.

Windows에서 Ubuntu 조건을 재현하는 방법은 [WSL/Docker 채점 환경 안내](notebooks/environment/grading/README.md)에 있습니다. Docker는 참가자의 로컬 검증 도구이며 운영진 실행의 필수 조건이 아닙니다. 컨테이너 검증 시 CPU·메모리를 제한하고 GPU를 전달하지 않으며 네트워크를 차단합니다. 운영진과 CPU 모델·커널까지 동일한 환경은 아니므로 처리시간이 같다고 보장하지 않습니다.

개발 소스의 계약 테스트는 다음 명령으로 실행할 수 있습니다. 단위 테스트 통과는 실제 평가 이미지의 추론 성공이나 정확도를 보증하지 않습니다.

```bash
python notebooks/project/run.py unittest discover -s notebooks/project/tests -v
```

## 모델 구성과 설계 요약

| 역할 | 모델 또는 방법 |
| --- | --- |
| 기본 텍스트 검출 | `PP-OCRv5_mobile_det` |
| 조건부 복구 검출 | `PP-OCRv6_small_det` |
| 한국어·영문·숫자 인식 | 재학습한 `korean_PP-OCRv5_mobile_rec` |
| 읽지 못한 날짜 줄의 보조 인식 | `en_PP-OCRv5_mobile_rec`, 지연 초기화 |
| 소비기한 선택 | 달력 검증, 기한·제조일 키워드, 좌표와 문자 인식 근거 |

전체 이미지의 기본 OCR을 우선 수행한 뒤, 미인식 날짜나 충돌하는 문맥에 대해 영역 확대·대비 보정·날짜 줄 재인식·추가 검출 등 조건부 복구를 수행합니다. 제조일과 소비기한을 구별하고 관측된 문자와 위치 근거를 사용해 날짜를 선택합니다.

날짜 순서는 명시된 형식과 문맥을 고려합니다. 기본 실행의 한국 식품 문맥 정책은 두 자리 날짜에 YMD를 우선 적용하고 시장·순서 충돌은 검토 상태로 처리합니다. 상세 규칙과 개발 근거는 [한국 식품 문맥 정책](notebooks/docs/architecture/korean-market-policy-20260911.md)과 [파이프라인 설계 문서](notebooks/docs/architecture/pipeline-spec.md)를 참조하세요.

## 검증 기록

2026-09-15 재현성 점검의 범위는 다음과 같습니다.

| 점검 | 결과와 범위 |
| --- | --- |
| 깨끗한 Python 3.10 venv | Windows에서 패키지 설치·import·`pip check` 성공 |
| Linux x86_64 / Python 3.10 패키지 | wheel 다운로드·의존성 해석 성공, Ubuntu 실행 검증과는 별개 |
| 실제 OCR 표본 실행 | 커밋 `435bf6e71f1c9f5740634153bf6d762b7a6b8e0b`에서 2장·20장 Run All 및 행 수 일치 확인 |
| 경로 주입 | 저장소 외부의 공백 포함 출력 경로에 CSV 생성 확인 |
| 500개 입력 구조 테스트 | 모의 OCR로 전체 순회·500행 생성 확인 |
| 단위 테스트 | 위 추론 버전에서 589개 통과 |
| Release 가중치 준비 | 배포 변경 커밋 `05d84f77269cb938a9699f2d9d12519c05aa8994`의 스크립트로 빈 폴더에 12개 파일 다운로드·SHA-256 검증 성공 |

실제 OCR 표본은 실패 프록시・오프라인 플래그를 사용하는 Windows 환경에서 검증했습니다. OS 수준의 네트워크 차단이나 Ubuntu 4코어·8GB 실행을 검증한 결과는 아닙니다. 사용 모델의 해시는 [모델 manifest](weights/adopted_model.json)에 있습니다.

Ubuntu 환경에서의 실제 500장 최종 평가 결과는 아직 이 문서에 기록되지 않았습니다. 환경 구축 후 검증한 제출 커밋, 모델 해시, 입력 수, 실행 환경, 전체 소요시간, 결과 및 오류 여부를 함께 기록합니다. 과거 352장 성능표와 소량 표본의 환산치는 현재 제출물의 최종 평가 성적으로 사용하지 않습니다. 이전 실험은 [파이프라인 설계 문서](notebooks/docs/architecture/pipeline-spec.md)와 [개발 검증 기록](notebooks/docs/architecture/date-policy-validation-20260910.md)을 참조하세요.

## 추가 수집 데이터와 출처

추가 수집 이미지 364장은 `custom_data/*.jpg`에, 날짜 정답은 [정답지](custom_data/labels/answer_003353_003716_manual.xlsx)의 `정답 날짜` 열에 있습니다(ID 3353 → `003353.jpg`). OCR 영역·문자열 주석과 출처 대응표는 `custom_data/metadata/`에 있습니다.

출처·라이선스·라벨 안내는 [ATTRIBUTION.md](custom_data/ATTRIBUTION.md)를 참조하세요. 추가 데이터와 라벨은 수집·학습 증빙이며, 추론 노트북의 입력은 운영진이 주입하는 평가 이미지 폴더입니다.

## 개발 기록 및 공식 참고 자료

- [개발·학습 문서 안내](notebooks/README.md)
- [원본 6회·4단계 개발 계획](notebooks/docs/protocol/grouped_6_rounds.md)
- [모델 채택 기록](notebooks/docs/development/adopted_recognizer_20260915.md)
- [ITDA 공식 제출 템플릿](https://github.com/b9511242000-blip/itda-ocr-template)
- [ITDA 공식 참가자 안내서](https://orchid-drum-814.notion.site/c74214f064ee837d81a80118ec8bf80a?pvs=143)
- [PaddleOCR 일반 OCR 파이프라인](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html)

제출 시 저장소는 Public으로 공개하거나 운영진 계정 `b9511242000-blip`에 접근 권한을 부여해야 합니다. 제출 이메일의 저장소 URL·커밋 해시와 아키텍처 요약서 PDF는 운영진 안내에 따라 별도로 제출합니다.
