# ITDA 소비기한 OCR

상품 이미지에서 소비기한을 찾아 `submission.csv`로 저장하는 CPU 전용 오프라인 추론 파이프라인입니다. 비공개 평가 입력 500장과 제한시간 2,400초를 기준으로 설계했으며, 외부 API·GPU·추론 중 다운로드를 사용하지 않습니다.

## 최종 구성

| 역할 | 모델 또는 방법 |
| --- | --- |
| 기본 텍스트 검출 | `PP-OCRv5_mobile_det` |
| 조건부 복구 검출 | `PP-OCRv6_small_det` |
| 한국어·영문·숫자 인식 | `korean_PP-OCRv5_mobile_rec` |
| 소비기한 선택 | 달력 검증 + 키워드·좌표·신뢰도 규칙 |

모든 이미지에는 빠른 mobile 검출기만 먼저 실행합니다. 유효 날짜가 없거나 제조일·소비기한 문맥이 충돌할 때만 ROI 확대, CLAHE, PP-OCRv6 복구 검출을 순서대로 실행합니다. 부분 날짜는 초기 패스에서 확정하지 않고 복구를 계속합니다. 모든 전체 이미지 패스에서도 날짜가 없거나 부분 날짜만 남고, 원본 OCR 라인이 32개 이하이면서 날짜 조각이 보이거나 OCR 라인이 5개 이하인 경우에만 네 개의 겹치는 타일을 확대 판독합니다.

회전 90/180/270도, EasyOCR, RapidOCR, YOLOv8, LayoutLM은 기본 실행 경로에 포함하지 않습니다. 공개 검증에서 회전은 정답을 추가하지 않고 연도 없는 날짜 오탐과 지연만 만들었고, EasyOCR는 어려운 표본 8건에서 추가 정답 0건·약 10–14초/장이었습니다. RapidOCR/ONNX도 이 모델 조합에서 Paddle static보다 빠르지 않았습니다. YOLOv8은 날짜 박스 라벨이, LayoutLM은 토큰·박스 분류 라벨과 별도 OCR가 필요해 현재 병목인 점자형 숫자 인식에 비해 비용이 큽니다.

상세 근거와 실험표는 [파이프라인 설계 문서](docs/pipeline-spec.md)에 있습니다.

## 평가 목표와 로컬 검증

- 공식 한도: 500장 / 2,400초 = 평균 4.8초/장
- 내부 목표: 500장 1,800초 이하, 오류로 인한 전체 중단 0건, 외부 비용 0원
- 정확도 기준: 사람이 확정한 라벨만 사용한 `final_date` 완전일치율

아래 표는 개선 규칙 반영 전의 과거 측정입니다. 공개 이미지 첫 352장 중 `manual` 341건만 평가하고 `needs_review` 11건은 제외했습니다. 새 날짜 정책의 검증 기록은 [2026-09-10 적용 검증](docs/date-policy-validation-20260910.md)에 별도로 정리합니다.

| 구성 | 완전일치 | 352장 시간 | 비고 |
| --- | ---: | ---: | --- |
| PP-OCRv5 mobile 기준선 | 261/341 (76.54%) | 574.2초 | 기본 + 부분 ROI |
| PP-OCRv5 server 복구 | 281/341 (82.40%) | 1,200.5초 | 정확도 대비 CPU 비용 큼 |
| PP-OCRv6 small 복구 초기안 | 287/341 (84.16%) | 827.3초 | 규칙 보강 전 |
| 최종 후보 규칙 | 302/341 (88.56%) | 1,508.9초 | 회전 포함 보수적 전수 측정 |
| 최종 구성 | 302/341 (88.56%) | 1,084.1초 | 회전 제거·타일 조건 축소, 단일 전수 측정 |

최종 구성은 평균 3.08초/장, p50 1.90초, p95 10.24초였고 500장 선형 환산은 약 1,540초입니다. 단일 전수 실행에서 이미지 처리 예외는 0건이었습니다. 이는 Windows 개발 장비 측정치이며 공식 채점 시간이나 공식 정확도 점수가 아닙니다. 기기·운영체제·입력 난이도에 따라 달라질 수 있습니다.

## 설치

Python 3.10 환경을 사용합니다.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell에서는 활성화 명령만 다음과 같이 바꿉니다.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 가중치 준비

인터넷이 연결된 준비 환경에서 노트북을 실행하기 전에 한 번 수행합니다.

```bash
bash download_weights.sh
```

스크립트는 PaddlePaddle의 공식 Hugging Face 저장소에서 고정된 revision의 다음 9개 파일을 받고 SHA-256을 검증합니다.

```text
weights/paddle/
├── PP-OCRv5_mobile_det/
│   ├── inference.json
│   ├── inference.pdiparams
│   └── inference.yml
├── PP-OCRv6_small_det/
│   ├── inference.json
│   ├── inference.pdiparams
│   └── inference.yml
└── korean_PP-OCRv5_mobile_rec/
    ├── inference.json
    ├── inference.pdiparams
    └── inference.yml
```

가중치는 `.gitignore`로 제외되며 Git에 커밋하지 않습니다. 파일이 없거나 해시가 다르면 추론 시작 시 명확한 오류로 중단합니다. 모델 경로를 모두 명시하고 Paddle의 모델 소스 확인도 비활성화하므로 `predict.ipynb` 실행 중에는 네트워크를 사용하지 않습니다.

## 실행

운영진과 동일하게 환경변수로 입력 폴더와 출력 파일을 주입합니다. 첫 CONFIG 셀은 수정하지 않습니다.

```bash
export ITDA_INPUT_DIR=./val_images
export ITDA_OUTPUT_PATH=./submission.csv

jupyter nbconvert --to notebook --execute predict.ipynb \
  --ExecutePreprocessor.timeout=2400 \
  --output /tmp/executed.ipynb
```

PowerShell 예시:

```powershell
$env:ITDA_INPUT_DIR = "C:\path\to\val_images"
$env:ITDA_OUTPUT_PATH = "C:\path\to\submission.csv"
jupyter nbconvert --to notebook --execute predict.ipynb `
  --ExecutePreprocessor.timeout=2400 `
  --output "$env:TEMP\executed.ipynb"
```

지원 확장자는 `.jpg`, `.jpeg`, `.png`이며 대소문자를 구분하지 않습니다. 파일 개수나 이름을 하드코딩하지 않습니다.

## 출력 계약

열 이름과 순서는 정확히 다음과 같습니다.

```text
image_id,year,month,day,final_date
```

- `image_id`: 확장자를 제거한 파일명 그대로
- 유효 날짜: `2026,05,29,2026-05-29`
- 연도는 없고 월/일 정보만 있음: NONE-MM-DD 형태로 출력
- 연/월 정보는 있으나 일자 정보가 없음: YYYY-MM-NONE 형태로 출력
- 유효한 날짜 정보가 없음: NONE 형태로 출력
- 부분 날짜의 개별 `year,month,day` 열도 누락 위치를 `NONE`으로 유지합니다. 날짜가 과거라는 이유로 거부하지 않으며 유효 연도 상한 2035와 달력 검증은 유지합니다.
- 한 이미지 처리 실패: 해당 행을 `NONE`으로 기록하고 다음 이미지 계속 처리
- 중복 stem 또는 빈 입력 폴더: 잘못된 제출 파일을 만들지 않고 즉시 오류

## 검증

빠른 계약 테스트:

```bash
python -m unittest discover -s tests -v
```

수동 라벨 CSV가 로컬에 있을 때 검증 구간 실행:

```bash
python scripts/evaluate_pipeline.py \
  ./val_images ./labels/validation.csv ./artifacts/validation_submission.csv \
  --limit 352
```

이 스크립트는 기본적으로 모든 입력 이미지를 실행하고 `라벨 상태 == manual`인 행만 점수에 사용합니다. 예시의 `--limit 352`는 명시적으로 범위를 줄이는 옵션입니다. OCR로 자동 생성한 미검수 값은 정답으로 취급하지 않습니다. 평가 대상 0건이나 중복 ID는 오류로 처리하고, 미매칭 라벨 및 실행 실패를 별도 집계합니다. 실행 실패는 정답이 `NONE`이어도 오답입니다. `--report-json 경로`로 평가 보고서를 저장할 수 있습니다.

## 제출 전 체크리스트

- `predict.ipynb` 첫 CONFIG 셀과 두 환경변수 이름을 변경하지 않았는지 확인
- `bash download_weights.sh`를 채점 노트북 실행 전에 수행
- 네트워크를 끈 새 Python 3.10 환경에서 Run All 완주 확인
- 입력 이미지 수와 CSV 행 수, 5개 열 순서, 중복 `image_id` 여부 확인
- 실행 경로에 `input()`·`getpass()`·외부 API 호출이 없는지 확인
- 저장소를 Public으로 두거나 운영진 계정 `b9511242000-blip`에 접근 권한 부여
- 가중치·원본 이미지·실행 결과를 Git에 포함하지 않았는지 확인

## 참고 자료

- [ITDA 공식 참가자 안내서](https://orchid-drum-814.notion.site/c74214f064ee837d81a80118ec8bf80a?pvs=143)
- [PaddleOCR 일반 OCR 파이프라인](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html)
- [PaddleOCR 텍스트 검출 모델](https://www.paddleocr.ai/main/en/version3.x/module_usage/text_detection.html)
- [PaddleOCR 텍스트 인식 모델](https://www.paddleocr.ai/main/en/version3.x/module_usage/text_recognition.html)
