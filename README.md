# ITDA 소비기한 OCR

상품 이미지에서 소비기한을 찾아 `submission.csv`로 저장하는 CPU 전용 오프라인 추론 파이프라인입니다. 비공개 평가 입력 500장과 제한시간 2,400초를 기준으로 설계했으며, 외부 API·GPU·추론 중 다운로드를 사용하지 않습니다.

## 최종 구성

| 역할 | 모델 또는 방법 |
| --- | --- |
| 기본 텍스트 검출 | `PP-OCRv5_mobile_det` |
| 조건부 복구 검출 | `PP-OCRv6_small_det` |
| 한국어·영문·숫자 인식 | `korean_PP-OCRv5_mobile_rec` |
| 읽지 못한 날짜 줄의 조건부 보조 인식 | `en_PP-OCRv5_mobile_rec` (지연 초기화, 추가 검출 없음) |
| 소비기한 선택 | 달력 검증 + 키워드·좌표·신뢰도 규칙 |

모든 이미지에는 빠른 mobile 검출기만 먼저 실행합니다. 유효 날짜가 없거나 제조일·소비기한 문맥이 충돌할 때만 ROI 확대, CLAHE, PP-OCRv6 복구 검출을 순서대로 실행합니다. 명시 부분 표기와 문자 근거가 충족된 경우 외에는 부분 날짜의 복구를 계속합니다. 모든 전체 이미지 패스에서도 날짜가 없거나 부분 날짜만 남고, 원본 OCR 라인이 32개 이하이면서 날짜 조각이 보이거나 OCR 라인이 5개 이하인 경우에만 네 개의 겹치는 타일을 확대 판독합니다.

2026-09-11 보강: 기본 검출 후 날짜 줄 최대 2곳을 기존 인식기로만 재확인합니다(각 3개 화면, 추가 검출 없음). 원본 영역의 역할 근거, 날짜 문자 점수, 복구 채택/기각 이력을 분리해 보존합니다. 명시 기한을 우선하고 관련 무표제 날짜 두 개에는 제한된 나중 날짜 정책을 적용합니다. [구조적 개선·개발 검증 결과](docs/ocr-structural-integration-20260911.md)에 성과와 미달 목표를 구분했습니다.

후속 보강에서는 이 재확인까지 실패한 줄의 조건부 영문·숫자 보조 인식, 밝은 패널의 점 인쇄 줄 복구, 명시 누락/부분 기한의 빠른 종료, 원본 좌표에 근거한 프레임 간 제조일·기한 연결을 추가했습니다. [최신 검증과 남은 근거](docs/ocr-recovery-status-20260911.md)를 참조하세요. 작은 개발 표본의 결과는 독립 95%·500장 성능 인증이 아닙니다.

후속 개선으로 미검출 시 유일한 기한 표제 주변을 한 번 확대하고, 명시 월·년 안내를 완전 날짜 오독보다 우선하도록 보강했습니다. 표제 확대에도 검출되지 않은 납작한 점 인쇄 줄은 최대 2곳의 비율 보정 화면으로 재확인하고, 명확한 날짜에 낮은 점수의 비날짜 문장이 합쳐져 생기는 불필요한 재시도도 줄였습니다. [최신 검증 결과와 남은 작업](docs/ocr-dot-budget-20260911.md)을 참고하세요.

회전 90/180/270도, EasyOCR, RapidOCR, YOLOv8, LayoutLM은 기본 실행 경로에 포함하지 않습니다. 공개 검증에서 회전은 정답을 추가하지 않고 연도 없는 날짜 오탐과 지연만 만들었고, EasyOCR는 어려운 표본 8건에서 추가 정답 0건·약 10–14초/장이었습니다. RapidOCR/ONNX도 이 모델 조합에서 Paddle static보다 빠르지 않았습니다. YOLOv8은 날짜 박스 라벨이, LayoutLM은 토큰·박스 분류 라벨과 별도 OCR가 필요해 현재 병목인 점자형 숫자 인식에 비해 비용이 큽니다.

상세 근거와 실험표는 [파이프라인 설계 문서](docs/pipeline-spec.md)에 있습니다.

## 평가 목표와 로컬 검증

- 공식 한도: 500장 / 2,400초 = 평균 4.8초/장
- 내부 목표: 날짜 전체 일치율 95% 이상, 평균 3초/장(500장 1,500초), 오류로 인한 전체 중단 0건, 외부 비용 0원. 1,500초 초과만으로 중단하지 않고 2,400초를 강제 종료 기준으로 사용합니다.
- 내부 정확도 기준: 사람이 확정한 라벨만 사용한 `final_date` 완전일치율. 운영진의 공식 채점은 부분점수를 포함하지만 배점은 미확정이므로 연·월·일별 진단 지표와 공식 점수를 구분합니다.

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

스크립트는 PaddlePaddle의 공식 Hugging Face 저장소에서 고정된 revision의 다음 12개 파일을 받고 SHA-256을 검증합니다.

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
├── korean_PP-OCRv5_mobile_rec/
│   ├── inference.json
│   ├── inference.pdiparams
│   └── inference.yml
└── en_PP-OCRv5_mobile_rec/
    ├── inference.json
    ├── inference.pdiparams
    └── inference.yml
```

가중치는 `.gitignore`로 제외되며 Git에 커밋하지 않습니다. 다운로드 스크립트가 해시를 검증하고, 추론 코드는 로컬 파일의 존재를 확인합니다(추론 때 해시를 다시 검사하는 것은 아닙니다). 필수 기본 모델이 없으면 초기화 오류이며, 지연 복구 모델이 없으면 해당 복구의 오류를 기록하고 가능한 기존 경로를 유지합니다. 모델 경로를 모두 명시하고 Paddle의 모델 소스 확인도 비활성화하므로 `predict.ipynb` 실행 중에는 네트워크를 사용하지 않습니다.

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
- 유효한 날짜 정보가 전부 없음: `year,month,day`는 각각 `NONE`, `final_date`는 `NONE`
- 부분 날짜의 개별 `year,month,day` 열도 누락 위치를 `NONE`으로 유지합니다. 날짜가 과거라는 이유로 거부하지 않으며 유효 연도 상한 2035와 달력 검증은 유지합니다.
- 날짜 순서는 명시 안내·달력 유효성·검증된 로컬 제품 규칙을 우선하며, 숫자는 명확하지만 순서만 모호하면 일-월-년(DMY)으로 출력합니다. 기본값 사용은 내부 `fallback_dmy` 사유로 기록하고 추가 OCR 없이 종료할 수 있습니다. 제조일·불가능한 날짜·누락 숫자를 기본값으로 채우지는 않습니다.
- 내부 목표는 전체 날짜 완전일치율 95% 이상이며, 500장 2,400초는 목표 시간이 아닌 타임아웃입니다. 목표 달성 여부는 독립 평가와 초기화 포함 실제 시간 측정으로 확인해야 합니다.
- 한 이미지 처리 실패: `year,month,day`는 각각 `NONE`, `final_date`는 `NONE`으로 기록하고 다음 이미지 계속 처리. 실패 원인은 별도로 보존하며 정답으로 집계하지 않습니다.
- 중복 stem 또는 빈 입력 폴더: 잘못된 제출 파일을 만들지 않고 즉시 오류

## 검증

2026-09-11부터 기본 실행은 CSV 옆의 `출력파일명.trace.jsonl`에 원본 좌표 변환, 관측/영역 ID, 미파싱·미인식 영역, 역할 어휘, 패스별 결정과 시간을 기록합니다. 날짜 선택 규칙은 그대로이며 영역 연결은 기하학적 가설로만 보존합니다. `PipelineConfig(collect_trace=False)`로 기록을 끌 수 있습니다. [오류 계측·영역 식별 결과](docs/ocr-region-trace-20260911.md)에 형식·실제 개발 점검·남은 한계를 정리했습니다.

2026-09-10 근거 연결 보완의 구현 범위, 회귀 검증 및 미달 목표는 [근거 연결 개선 보고서](docs/date-evidence-repair-20260910.md)에 기록했습니다. 개발 중 확인한 사진/기록의 성적을 독립 평가 정확도로 취급하지 않습니다.

후속 문자 처리·부분 날짜·조기 종료 개선과 재번호 후 705건 비교는 [후속 구현 보고서](docs/date-recognition-repair-20260910.md)를 참조하십시오. 95% 목표와 공식 환경 500장 속도 검증은 아직 완료되지 않았습니다.

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

과거 `NONE-NONE-NONE`은 의미 비교에서 `NONE`과 같게 처리하지만 새 제출 형식 준수로 인정하지 않습니다. `field_metrics`에는 연·월·일별 일치율과 값 존재/부재별 분모, 오독·미출력·추가 출력·평가 불가를 나눠 기록합니다. `submission_format`은 5열 순서와 날짜 필드 일관성을 별도로 검사하며, 형식 미준수/미확인이면 결합 합격을 표시하지 않습니다. `official_partial_score`는 배점 확인 전 `null`입니다. 부분 출력은 기존 `NONE-MM-DD`, `YYYY-MM-NONE`을 유지하고 미확정 형식을 새로 허용하지 않습니다. 상세 구현·확인은 [제출·평가 계약 정비](docs/submission-contract-20260910.md)를 참조하십시오.

## 제출 전 체크리스트

최신 날짜 정책은 [한국 식품 문맥 정책](C:/ITDA_OCR_CODE/docs/korean-market-policy-20260911.md)이다. 기본 실행은 한국 식품의 기한 문맥에서 두 자리 날짜를 YMD 우선 해석한다. 명시 순서는 우선하며, 수입/시장 충돌이나 미확정 순서는 REVIEW로 남긴다. REVIEW의 제출 날짜는 `NONE`, 상세 상태·근거·시각/코드는 trace에 기록한다. 이전 DMY 마지막 기본값과 다른 사용자 승인 정책이므로 정확도 변화와 보류율을 함께 확인해야 한다.

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
