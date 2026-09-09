# 연도 하한 제거 재검증

사용자 요청에 따라 기존 기준군의 2024년 이전 날짜 거부 설정만 제외한다. 운영 소스는 변경하지 않고, 판독 프로세스에서 MIN_YEAR=1로 바꾼다. MAX_YEAR=2035와 파서·문맥·날짜 쌍 선택의 나머지 규칙은 유지한다. 특히 선택 함수의 year>=2024 구분은 거부 필터가 아니므로 그대로 둔다.

1. run_rebaseline.py는 이미지 386장을 새로 실행하여 지정 labels/audit/..._year_unrestricted에 원시 OCR와 시간·설정을 저장한다. 정답·annotations·기존 예측을 판독에 사용하지 않는다.
2. prepare.py는 원본·이미지·운영 코드·가중치·기존 결과 해시를 확인하고, 이전 결과 11개를 작업 디렉터리에 백업한다. prepare.py collect는 완료된 새 기준군 기록을 가져온다.
3. 기존 개선안 p3의 386개 예측과 실행 시간을 검증 후 재사용한다. 판독값은 바꾸지 않으며 새 기준 대비 개선/회귀 여부만 결과 비고에 갱신한다.
4. 새 기준군에서 수집한 동일 OCR 출력에 baseline, p1, p2, p3 재평가를 각각 적용한다. 기준 대조만 MIN_YEAR=1, MAX_YEAR=2035를 사용하며 기존 p1/p2/p3 실험 규칙(연도 2000–2099 포함)은 변경하지 않는다. OCR 실행과 재평가 시간 측정을 동시에 수행하지 않는다.
5. score.py, paired_timing.py, report.py로 채점·동일 입력 시간 통제·비교 보고서를 계산한다. 과거 2.59% 기준군과 +70.98%p·약 2배 속도 차이는 현재 주 비교에서 제외한다.
6. 번들 Artifact Tool로 기존 8열·수식·서식을 유지한 두 XLSX를 작업 outputs에 작성한다. 공유 수식 행을 원본 그대로 명시하고 누락된 서식 메타데이터만 복원한다. read-only openpyxl 검산으로 모든 값·수식·서식과 CSV를 확인한다.
7. publish.py는 승인된 labels 폴더에서 현재 결과가 최초 스냅샷과 같은지 확인한 후 previous_results에 백업하고 검증된 결과 11개만 교체한다. 원본 manual 파일 3개는 교체 대상에서 제외한다. 새 판독 결과와 이전 개선안의 측정 시점 차이를 보고서에 명시한다.

실행 순서: prepare.py, test_baseline.py, run_rebaseline.py(새 전용 디렉터리에서 1회), prepare.py collect, replay.py baseline/p1/p2/p3, paired_timing.py, score.py, build_results.mjs inspect/build, restore_export_metadata.py, verify_outputs.py, report.py, publish.py. 실제 실행에서는 판독과 가벼운 준비·단위 검사 일부가 겹쳤고 이를 통제된 반복 벤치마크로 주장하지 않는다.

독립 블라인드 테스트가 아닌 개발 검증이다. 외부 모델·VLM 호출·추가 학습·새 ROI 정책은 포함하지 않는다. 완전일치는 사용자가 수정한 XLSX 정답 문자열과 비교하며 부분 날짜의 NONE 위치까지 일치해야 한다. 예외는 항상 실패다.
