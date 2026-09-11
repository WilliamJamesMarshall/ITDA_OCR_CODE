# validation_000001_003352 검수 근거

이 폴더는 `labels/validation_000001_003352_manual.xlsx`를 작성하고 검증할 때 사용한 최소 감사 자료만 보존한다.

- `visual_overrides.json`: 이미지별 수동 판독 덮어쓰기 440건
- `summary.json`: 판독 방식과 재검수 대상 집계
- `refine_ids.txt`: 추가 정제가 필요하다고 분류된 이미지 ID
- `unresolved_ids.txt`: 자동 판독으로 확정하지 못한 이미지 ID
- `pipeline_submission_3352.csv`: 3,352장 전체의 OCR 파이프라인 최종 출력

캐시, 미리보기, 크롭 이미지, 중간 체크포인트, `node_modules`, 샤드용 이미지 복제본은 재생성 가능한 임시 산출물이므로 저장소에서 제외한다.

정답지를 수정한 뒤 `python scripts/manual_validation_guard.py sync --update-lock`으로 CSV·NDJSON·잠금 파일을 함께 갱신한다. 커밋·병합 전 검사는 `python scripts/manual_validation_guard.py check`로 실행한다.
