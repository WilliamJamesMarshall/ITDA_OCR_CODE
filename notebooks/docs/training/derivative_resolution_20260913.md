# 증강 테스트 이미지의 원본 대응 조사 결과

후속 사용자 지시로 원본 파일 부재 22건을 `상품사진입니다`의 해당 파일에 **기존 상품사진 참조**로 연결했다.
22개 참조 파일은 테스트 증강본과 SHA-256이 동일하다. 참조 연결 미완료는 0건이다.
이 연결은 증강본을 원본으로 재분류하거나 학습 편입하는 변경이 아니며, 원본 파일 부재 22건은 별도로 표시한다.
현재 연결 근거: [22건 상품사진 참조 목록](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/existing_product_references.json).

2026-09-13 사용자의 즉시 조사 요청에 따라 기존 미확정 1,106건 전체를 조사했다.

| 회차 | 조사 대상 | 현재 원본 연결 | 삭제 전 출처 확인·원본 파일 부재 |
|---|---:|---:|---:|
| 4 | 222 | 218 | 4 |
| 5 | 225 | 223 | 2 |
| 6 | 225 | 223 | 2 |
| 7 | 224 | 223 | 1 |
| 8 | 210 | 197 | 13 |
| 합계 | 1,106 | 1,084 | 22 |

1~3회는 기존 원본 연결을 그대로 보존했다. 전체 테스트 3,716장, 학습 원본 2,610장,
회차 구성 및 초기 개발 사용 표시는 변경하지 않았다. 테스트·학습·가중치 교체는 실행하지 않았다.

## 연결 근거

원본 2,610장 전체의 특징점을 검색한 뒤 후보별 기하 정합, 화면 전체 및 9구역 픽셀 비교,
밝기·채널 포화 변환 재현, 필요 시 조밀한 특징점 재검증을 수행했다.
1,067건은 유일한 후보가 자동 검증을 통과했다.
17건은 자동 기준을 완화하지 않고 Codex가 실제 원본과 증강본을 각각 직접 열어
포장 주름·반사광·손가락·주변 배경·미세 얼룩과 배치를 대조한 검토 기록으로 확정했다.
이는 사람의 OCR 라벨 검수·학습 승인이라는 뜻이 아니다.

번호가 가깝다는 사실은 후보 탐색에만 사용했다. AMLT002358은 어두운 변형 때문에
초기 특징점 검색에서 후보가 없었으나 AMLC001683과 실제 유리 반사광·향신료 분포·손가락을 직접 비교해 연결했다.

대응표와 큐, 잠금 해시를 갱신했고, 이전 대응표·큐·잠금 파일은 mapping_revisions에 보관했다.
새 연결 1,084건마다 test/original SHA, 원본 주석 SHA, 계산·시각 검토 근거를 저장했다.
학습용 상품 그룹 검토 및 회차별 학습 승인은 별도이며 자동 승인하지 않았다.

## 남은 22건의 정확한 상태

이 22건은 과거 추가수집데이터 중복 제거에서 원본 파일이 삭제됐다.
기존 중복 조사에 남은 실제 동일 사진 확인 기록, 원본 아카이브 내부 경로·해시,
삭제 목록을 대조해 출처를 확인했다. 현재 학습 원본 2,610장의 해시 목록에는 해당 파일이 없다.

- 4회: AMLT000896, AMLT000982, AMLT001129, AMLT001330
- 5회: AMLT001431, AMLT001782
- 6회: AMLT001906, AMLT002020
- 7회: AMLT002610
- 8회: AMLT003014, AMLT003019, AMLT003099, AMLT003183, AMLT003221, AMLT003228,
  AMLT003245, AMLT003258, AMLT003271, AMLT003280, AMLT003289, AMLT003308, AMLT003320

원본 출처는 ExpDate의 Products-Real.zip 내부 개별 이미지이며, 파일별 경로·SHA는 아래 missing_originals.json에 있다.
이번 작업은 그 파일을 새로 다운로드하거나 이전 삭제 결정을 되돌린 것이 아니다.
복원·학습 데이터 재편입은 원본을 다시 확보하고 해시를 검증한 뒤, 보호 데이터 목록·신규 ID·OCR 주석·그룹 검토까지
포함하는 변경이므로 명시적 결정을 받아 진행해야 한다. 실제 학습은 여전히 해당 테스트 보고서에 대한 승인 이후이다.
현재 대응표에서 이들의 original_id는 비워 두고 mapping_status=source_identified_file_missing으로 구분해 학습 차단을 유지한다.
기존 상품사진 경로와 SHA는 product_reference_path/product_reference_sha256에,
파일 유형과 용도는 augmented_existing_product/reference_only로 기록한다.

## 실제 파일

- [현재 대응표](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/test_to_original_mapping.csv)
- [조사 요약·검증](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/derivative-resolution-20260913/summary.json)
- [삭제 원본 22건 출처·해시](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/derivative-resolution-20260913/missing_originals.json)
- [17건 실제 시각 대조 기록](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/derivative-visual-review-20260913.json)
- [변경 전 대응표](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/derivative-resolution-20260913/mapping_before.csv)

재현 코드: resolve_original_derivatives → refine_derivative_photometry → verify_derivative_color →
refine_derivative_geometry → 시각 검토 기록 → finalize_derivative_mapping.
이미 완료한 조사 출력 폴더는 덮어쓰지 않는다. 재조사는 새 출력 경로를 사용한다.
