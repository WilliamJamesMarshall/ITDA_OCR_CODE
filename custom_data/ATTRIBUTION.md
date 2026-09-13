# 추가 수집 데이터 출처와 라벨 안내

## 출처와 라이선스

이 폴더는 Korea Institute of Science and Technology(KIST)의 **ExpDate / Products-Real**에서 선별 수집한 실사 이미지 364장과 관련 주석을 포함합니다. 팀이 직접 촬영한 사진이 아닙니다.

- 원출처: [ExpDate: Expiration Date Dataset](https://felizang.github.io/expdate/index_expdate.html)
- 원천 데이터 라이선스: [Creative Commons Attribution 4.0 International(CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- 관련 논문: Ahmet Cagatay Seker and Sang Chul Ahn. “A generalized framework for recognition of expiration dates on product packages using fully convolutional networks.” *Expert Systems with Applications*, 203, 117310, 2022.

원천 이미지와 원천 주석을 재사용할 때 위 출처·저작자·라이선스 및 변경 사항 표시를 유지하세요.

## 구성과 변경 사항

- `003353.jpg`–`003716.jpg`: 선별 수집한 이미지 364장. 원래 파일명과 현재 파일명은 `metadata/source_manifest.csv`로 연결됩니다. 원천 분할 기준 `real_train` 219장, `real_evaluation` 145장이며, 이 값은 원천 출처의 분할명입니다.
- `metadata/annotations.json`: 현재 이미지 파일명을 키로 사용하는 원천 영역 좌표(`bbox`), 클래스(`cls`), 문자열(`transcription`) 주석입니다. `date`, `exp`, `due`, `prod`, `code` 클래스를 포함합니다. 최종 소비기한 정답과 구분해 사용하세요.
- `metadata/source_manifest.csv`: 원천 데이터셋·분할·파일 경로, 현재 파일명, 이미지 크기, SHA-256, 라이선스 및 출처 URL입니다.
- `metadata/source_archives.json`: 원천 압축파일의 다운로드 기록입니다. 기록에 Products-Synth가 포함되어 있으나 이 제출 폴더의 이미지 364장은 모두 Products-Real이며 합성 이미지와 원천 ZIP은 포함하지 않습니다.
- `labels/answer_003353_003716_manual.xlsx`: 팀의 최종 날짜 검수 결과입니다. 원천 OCR 주석과 별도로 제공합니다.

원천 데이터에서 일부 이미지를 선별하고 파일명을 재번호화했으며, 원천 주석 키와 출처 대응표를 현재 파일명에 맞추었습니다. 이번 제출 패키징에서는 보관 중인 이미지·메타데이터·정답지를 그대로 복사했습니다. 사진의 추가 리사이징·재압축과 주석 좌표 변경은 하지 않았습니다.

## 최종 날짜 정답지 사용법

`image_id` 열을 여섯 자리 숫자로 맞추고 `.jpg`를 붙이면 대응 이미지가 됩니다(예: `3353` → `003353.jpg`). `정답 날짜` 열이 최종 날짜 정답이며, `라벨 상태`의 `approved`는 **최종 날짜만 승인**했다는 의미입니다. 364개 이미지 모두 정답과 승인 상태가 있습니다.

정답이 `NONE`이면 최종 기한 날짜 정보가 없는 경우이며, `NONE-MM-DD` 또는 `YYYY-MM-NONE` 등의 부분 날짜는 알려진 부분만 보존합니다. `추출한 날짜`와 `True/False` 열은 모델 출력 비교용으로, 정답 열이 아닙니다. `unassessed` 난이도나 원천 OCR 영역·문자열을 별도 사람 검수 완료로 해석하지 마세요.

제출 정답지는 기존 승인본 `answer_003353_003716_manual.xlsx`를 채택했습니다. 별도 보관된 과거 `validation` XLSX와 다른 6개 ID(`003457`, `003510`, `003522`, `003564`, `003614`, `003630`)는 모두 `NONE-NONE-NONE` → `NONE` 형식 정리이며, 그 밖의 정답은 같습니다. 정답 열이 비어 있는 과거 CSV는 포함하지 않았습니다.

구체적인 수집 필요성, 선별 기준, 검수 과정과 모델링 활용 방식은 제출 요약서에서 설명합니다.
