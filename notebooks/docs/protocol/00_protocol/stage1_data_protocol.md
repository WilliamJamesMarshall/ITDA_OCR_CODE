> 문서 열람용 사본. 계획 수정은 원본 `C:\ITDA_OCR_CODE\학습 및 테스트 결과\00_protocol\stage1_data_protocol.md`에서 수행한 뒤 이 도구로 다시 게시합니다. 승인/정답 데이터는 포함하지 않습니다.

# 1단계 데이터·정답지 정비 계약

정책 버전: 1.0. 사용자 확정일: 2026-09-11.

## 확정된 정답과 출력

- 상품사진/추가수집 XLSX를 원본 수준 최종 날짜 정답으로 승인한다. 테스트/학습 XLSX는 대응되는 파생 정답지다.
- 원본 ID 000157의 정답은 사용자 확정값 `2027-07-08`이다. 상품사진·테스트·학습 XLSX의 C158에 반영한다. 이 확정은 해당 정답 라벨에만 적용하며 날짜 파서의 전역 DMY/MDY 정책을 변경하지 않는다.
- 유효한 소비기한 정보를 얻지 못해 year/month/day가 전부 NONE이면 final_date는 `NONE`이다. XLSX의 기존 `NONE-NONE-NONE`도 모두 `NONE`으로 바꾼다.
- 정본 날짜는 `YYYY-MM-DD`, `YYYY-MM-NONE`, `NONE-MM-DD`, `NONE`만 허용한다. 부분 날짜의 알려진 필드를 보존하고 전체 날짜의 달력 유효성을 검사한다.
- 내부 선택 실패는 Python None으로 유지한다. 제출, 완료 행 저장, 타임아웃 부분 저장은 공통 `submission_fields`로 출력한다. 실행 오류를 정상 미인식 정답으로 세지 않는다.
- 과거 실험 결과·백업의 NONE-NONE-NONE은 보존한다. 현재 평가기는 의미상 비교만 호환하며 새 제출 형식으로 인정하지 않는다.

## 정본과 식별자

- `dataset_inventory.json`: 원본 논리 자산 3,716건. `data/source_labels.jsonl`은 같은 자산별 정본 라벨이다.
- `data/training_labels.jsonl`: 선택된 2,610건. `training_image_id`는 실제 AMLC/BMLC 파일 stem이다.
- `data/product_labels.csv`, `additional_labels.csv`, `test_labels.csv`, `training_labels.csv`: 정본의 UTF-8 BOM 검사·평가용 뷰. CSV의 True/False는 추론 전에는 빈값이며 XLSX 수식 문자열을 결과로 내보내지 않는다.
- source_image_id는 6자리 문자열이다. 원본 ID와 학습 재번호 ID를 같은 식별자로 취급하지 않는다.
- asset_id는 전체 SHA-256이다. 각 원본/테스트/학습 복사본의 경로, 크기, 해상도, SHA-256 및 원본 XLSX 경로·해시·셀을 기록한다.
- 테스트용데이터는 동일 이미지 복사본이므로 독립 외부 테스트셋이 아니다.
- `data/originals/`는 수정 전 XLSX·매핑·원천 메타데이터 백업이다. `original_hashes.json`으로 백업을 검증하고 `frozen_hashes.json`으로 현재 데이터 산출물을 동결한다.

## 메타데이터와 승인

- XLSX E열 `approved`는 최종 날짜만 승인한다. 원문·polygon·상품 그룹 승인으로 해석하지 않는다.
- 날짜 승인, 인식 원문 승인, 검출 polygon 승인은 각각 별도 상태로 기록한다. 현재 OCR 학습 승인 건수는 0이다.
- 상품사진 난이도·조건은 기존 CSV의 정보를 `legacy_imported`로 계승한다. 기존 자동 OCR의 `rapidocr`, `needs_review`, `manual`은 legacy_label_status로만 보존한다. 기존 CSV 날짜가 XLSX 날짜를 덮어쓰지 않는다.
- 추가수집처럼 난이도 근거가 없는 항목은 `unassessed`와 `difficulty_status=needs_review`로 명시한다. 결측값을 easy로 추정하지 않는다. 2단계 사람 검수에서 easy/medium/hard로 확정한다.
- 난이도 기준: easy는 날짜 줄의 문자가 분명하고 기하·광학 훼손이 거의 없음, medium은 국소 훼손이나 읽기 위한 확대·회전이 필요하지만 원문 확인 가능, hard는 반사·곡면·점 인쇄·저해상도·흐림 등으로 원문 확인에 강한 불확실성이 있음. 현재 모델 성공 여부로 난이도를 정하지 않는다.
- condition_tags는 복수 값이며 XLSX/CSV에서는 세미콜론으로 연결한다. full_date/partial_date/no_expiry는 승인 날짜에서 산출하고, multiple_date_lines/latin_text는 원천 주석에서 산출한다. 기존 한국어 조건 태그는 이력을 유지하되 사람 재확인 전 확정 관측으로 간주하지 않는다.
- 추가로 확인할 조건: 전체/부분 날짜, 일반/점 인쇄, 반사, 곡면, 흐림, 저해상도, 복수 날짜 줄, 제조일·소비기한 동시, 한글·영문 월·숫자 전용, 출처. 해당 여부를 사진으로 검수하고 모델 오류 유형은 별도 평가 결과에 기록한다.

## 경로 복구와 제외

- SHA-256으로 현재 원본을 유일하게 찾고 학습 source_mapping, 추가수집 source_manifest, 테스트 source_manifest, 추가수집 annotations 키를 함께 복구한다.
- 추가수집 364건의 이전 번호는 모두 2씩 어긋났지만 숫자 보정만으로 연결하지 않는다. 복구 전후 키와 경로는 `data/provenance_repairs.json`에 기록한다.
- 학습대상은 상품사진 원본 2,246장과 추가수집 364장이다.
- 640×640 파생본 1,106개는 `preexisting_640x640_augmented_derivative`로 제외한다. 근거는 기존 분류 기록 `artifacts/image-serial-number-groups-상품사진입니다.md`와 원래 제외 목록이다.
- 원래 제외 목록 SHA-256: `a8fe5be332257e6a7c7cf95eb506cc66bbd967767e9690df7b45c3a90f387ed0`.
- `data/excluded_images.jsonl`에 대상별 경로와 이미지 해시를 고정한다. 제외 이미지를 삭제하거나 학습·평가 원본 집합에 편입하지 않는다.

## 2단계 입력과 검수 절차

`data/annotation_review_queue.jsonl`은 2,610장 전체 작업 목록이다. `data/source_annotation_candidates.jsonl`은 추가수집 날짜 줄 404개 후보이며 `data/annotation_checks.json`은 자동 검사 결과다.

1. 이미지와 SHA 연결, 해상도, bbox 순서·범위, 빈 원문을 자동 검사한다. 원문은 숫자·구분자·내부 공백을 그대로 보존하며 ISO 날짜만 강제하지 않는다.
2. 기존 bbox는 직사각형 polygon 후보로 변환한다. 사람이 사진과 비교해 날짜 줄 전체 영역, 누락된 줄, 원문, 제조일/소비기한/불명 역할을 확인한다. source class만으로 날짜 역할을 승인하지 않는다.
3. 원본 상품사진의 원문·polygon을 구축하고, 추가수집 364장은 모든 후보를 사람이 확인한다. 자동 통과가 사람 승인을 대신하지 않는다.
4. 최종 날짜 NONE 이미지에도 제조일 등 날짜 줄이 있을 수 있으므로 검출 음성으로 자동 승인하지 않는다. 실제 날짜 줄이 없음을 확인한 경우에만 검출 음성으로 승인한다.
5. 승인할 때 원문·polygon별 approved 상태, 승인자, 시각, 이미지 해시와 주석 버전을 남긴다. 불명확한 원문·역할은 needs_review로 유지한다.
6. 같은 상품·연속 촬영·파생본을 그룹으로 확인한다. 현재 group_id는 완전 동일 자산만 묶은 초안이며 상품 그룹 확정값이 아니다. 제외 파생본의 부모 그룹도 근거를 확인해 연결한다.
7. 그룹 검수가 끝난 뒤 fold와 영구 inner validation을 생성한다. 기존 개발 노출 705장 및 같은 상품 그룹은 fold 5에서 제외한다. 고정 seed 20260911, 그룹 보존, fold 5 미사용 등 execution_policy의 규칙을 유지한다.
8. 학습 가능한 crop/원문 목록은 주석 승인과 분할이 완료된 뒤 생성한다. 최종 날짜를 인식 원문으로 대신 사용하지 않는다.

## 완료 기준과 검증

1단계 통과는 2단계 입력 준비 완료를 뜻한다. OCR 주석 사람 검수, 상품 그룹 확정, fold 생성, 모델 학습은 이후 작업이다.

- 원본 3,716개, 학습 이미지·최종 날짜 정답 각 2,610개, 제외 1,106개.
- ID 중복·누락 파일·날짜 형식/달력 오류·현재 경로/해시 불일치 0건.
- 원본/테스트/학습 대응 해시 일치 및 수정 전 백업 검증.
- 빈 라벨 상태·난이도·조건 필드 0건. unassessed/needs_review의 후속 검수 상태를 명시.
- 2,610장 검수 목록과 추가수집 404개 원문·영역 후보 준비. 사람 승인 여부를 별도 유지.

재검증: `scripts/prepare_stage1_data.py verify`를 Pillow와 openpyxl이 있는 Python으로 실행한다. Python openpyxl은 읽기 검증에만 사용하며 XLSX는 artifact-tool로 수정했다.

기존 `artifacts/ocr-recovery-closeout-20260911/training_readiness.json`은 당시의 역사적 감사 결과다. 현재 데이터 단계 상태는 이 디렉터리의 `stage1_readiness.json`을 따른다.
