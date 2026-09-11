import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
LABELS = OUT.parents[1]
scores = json.loads((OUT/'scores.json').read_text(encoding='utf-8'))
data = json.loads((OUT/'workbook_data.json').read_text(encoding='utf-8'))
assert set(scores) == {'baseline','baseline_replay','p1_replay','p2_replay','p3_replay','p3'}
def pct(x): return f'{100*x:.2f}%'
def cell(s,k):
    a=scores[s]['categories'][k]
    return f'{a["correct"]}/{a["total"]} ({pct(a["correct"]/a["total"])})'
def exact(s):
    a=scores[s]
    return f'{a["correct"]}/364 ({pct(a["accuracy"])})'
def records(stage): return {r['image_id']:r for r in data[stage]['records']}
def compare(a,b):
    left,right=records(a),records(b)
    return {'gained':[k for k in left if not left[k]['correct'] and right[k]['correct']],
            'lost':[k for k in left if left[k]['correct'] and not right[k]['correct']]}
comparisons={f'{a}_to_{b}':compare(a,b) for a,b in [('baseline','baseline_replay'),('baseline_replay','p1_replay'),('p1_replay','p2_replay'),('p2_replay','p3_replay'),('p3_replay','p3')]}
(OUT/'comparisons.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2),encoding='utf-8')
baseline,improved=scores['baseline'],scores['p3']
speedup=baseline['runtime']['loop_wall_seconds']/improved['runtime']['loop_wall_seconds']
delta=(improved['accuracy']-baseline['accuracy'])*100
paired=json.loads((OUT/'paired_timing.json').read_text(encoding='utf-8'))
text=[
'# 소비기한 OCR 364장 검증 결과',
'',
f'현재 파이프라인은 {exact("baseline")}, 개선 실험안의 이미지 재실행은 {exact("p3")}였다. 정확도 차이는 {delta:+.2f}%p이며, 이미지 처리 구간은 {speedup:.2f}배 속도 차이를 보였다.',
'',
'이 결과는 앞선 주석 정보·시각 검토 방식의 99.48%를 재현한 점수가 아니다. 그 판단 기준 중 연도·부분 날짜·날짜 순서·문맥 처리 규칙을 이미지 전용 CPU 파이프라인에 이식한 개발 검증 결과다. 기존 코드의 낮은 점수는 연도 제한과 이 검증셋의 불일치가 크게 작용했다.',
'',
'## 1. 이미지 전수 실행 결과',
'',
'| 항목 | 기준 실행(기존 완료 기록) | 개선 실험안 p3(새 실행) |',
'| --- | ---: | ---: |',
f'| 전체 완전일치 | {exact("baseline")} | {exact("p3")} |',
f'| 완전 날짜 | {cell("baseline","full")} | {cell("p3","full")} |',
f'| 부분 날짜 | {cell("baseline","partial")} | {cell("p3","partial")} |',
f'| NONE | {cell("baseline","none")} | {cell("p3","none")} |',
f'| 이미지 처리 구간 | {baseline["runtime"]["loop_wall_seconds"]:.1f}초 | {improved["runtime"]["loop_wall_seconds"]:.1f}초 |',
f'| 초기화 포함 전체 측정 구간 | {baseline["runtime"]["total_wall_seconds"]:.1f}초 | {improved["runtime"]["total_wall_seconds"]:.1f}초 |',
f'| 이미지별 시간 중앙값 | {baseline["median_image_seconds"]:.2f}초 | {improved["median_image_seconds"]:.2f}초 |',
f'| 이미지별 시간 p95 | {baseline["p95_image_seconds"]:.2f}초 | {improved["p95_image_seconds"]:.2f}초 |',
f'| OCR 호출·입력 해시 계측 누적 | {baseline["ocr_call_and_input_hash_seconds"]:.1f}초 | {improved["ocr_call_and_input_hash_seconds"]:.1f}초 |',
f'| 나머지 이미지 처리 누적 | {baseline["other_image_work_seconds"]:.1f}초 | {improved["other_image_work_seconds"]:.1f}초 |',
f'| 추가 복구 검출 실행 수 | {baseline["pass_counts"].get("recovery:original",0)} | {improved["pass_counts"].get("recovery:original",0)} |',
f'| 실행 오류 | {baseline["error_types"].get("실행 오류",0)} | {improved["error_types"].get("실행 오류",0)} |',
'',
f'500장 선형 환산은 이미지 처리 구간 기준 각각 {baseline["runtime"]["loop_wall_seconds"]*500/364:.0f}초, {improved["runtime"]["loop_wall_seconds"]*500/364:.0f}초다. 이는 500장 실측이나 공식 평가 환경 점수가 아니다.',
'프로젝트 README의 시간 기준은 500장 2,400초, 내부 목표는 1,800초다. 이번 장비는 8코어 개발 PC이며 OCR 스레드 수만 4개로 설정했으므로 공식 4-vCPU 환경의 통과 여부를 이 환산치로 확정하지 않는다.',
'',
'나머지 이미지 처리 시간에는 이미지 읽기, 전처리, 후보 해석·선택, 로그용 객체 변환 등이 포함된다. 순수 날짜 파서 시간으로 해석하지 않는다.',
'',
f'시간 비교 통제: 모든 이미지의 첫 mobile 원본 패스 입력 해시는 동일했다. OCR 문자열 출력도 {paired["same_text_count"]}/364건이 동일했다. 그럼에도 동일 패스의 p3/baseline 시간비 중앙값은 {paired["median_p3_over_baseline_ratio"]:.2f}였다. 실행 시점에 따른 시간 변동이 관찰되므로 위의 속도 차이를 코드 변경만의 순수 효과로 단정할 수 없다. 정밀한 속도 추정은 교차 순서 반복 측정이 필요하다.',
'',
'현재 코드의 MIN_YEAR=2024, MAX_YEAR=2035 범위에 들어가는 정답은 완전 날짜 4건뿐이다. 부분 날짜 25건도 기존 출력 계약으로는 표현할 수 없다. NONE 정답 7건을 더해도 이 데이터에서 기존 코드의 이론적 상한은 11/364(2.85%)다. 이 낮은 점수를 OCR 인식기 자체의 일반 정확도로 해석해서는 안 된다.',
'',
'## 2. 실행 우선순위별 후처리 비교',
'',
'아래는 baseline이 수집한 동일 OCR 출력 전체를 고정한 비교다. 새 OCR를 수행하지 않았고 조기 종료 경로도 재현하지 않았다. 후처리 시간은 전체 처리시간과 비교할 수 없다.',
'',
'| 단계 | 추가한 변화 | 완전일치 | 후처리만 실행한 시간 |',
'| --- | --- | ---: | ---: |',
f'| baseline 대조 | 기존 규칙을 같은 OCR 출력에 최종 선택 모드로 적용 | {exact("baseline_replay")} | {scores["baseline_replay"]["runtime"]["parser_only_seconds"]:.2f}초 |',
f'| p1 | 과거 연도 허용, 부분 날짜 출력 | {exact("p1_replay")} | {scores["p1_replay"]["runtime"]["parser_only_seconds"]:.2f}초 |',
f'| p2 | p1 + 날짜 순서·영문 월 표기 | {exact("p2_replay")} | {scores["p2_replay"]["runtime"]["parser_only_seconds"]:.2f}초 |',
f'| p3 | p2 + 좌표계·문맥 분리, 전역 최후 날짜 우선 제거 | {exact("p3_replay")} | {scores["p3_replay"]["runtime"]["parser_only_seconds"]:.2f}초 |',
'',
'| 단계 | 완전 날짜 | 부분 날짜 | NONE |',
'| --- | ---: | ---: | ---: |',
*[f'| {stage} | {cell(stage,"full")} | {cell(stage,"partial")} | {cell(stage,"none")} |' for stage in ('p1_replay','p2_replay','p3_replay')],
'',
'각 단계는 여러 규칙을 묶은 누적 실험이다. 연도 범위와 부분 날짜 규칙 각각의 독립 기여도, 문맥 점수와 좌표계 분리 각각의 독립 기여도를 분해한 결과는 아니다.',
'',
]
for name,c in comparisons.items():
    text.append(f'- {name}: 정답으로 개선 {len(c["gained"])}건, 정답을 잃은 사례 {len(c["lost"])}건. 전체 ID는 audit의 comparisons.json에 기록했다.')
text += ['',
'## 3. 지정 사례 확인',
'',
'| image_id | 정답 | 현재 파이프라인 | 개선안 이미지 재실행 |',
'| --- | --- | --- | --- |']
a,b=records('baseline'),records('p3')
for i in ('003491','003565','003409','003502','003532','003556',):
    text.append(f'| {i} | {a[i]["truth"]} | {a[i]["prediction"]} | {b[i]["prediction"]} |')
text += ['',
'baseline 원시 로그에서 확인한 원인:',
'',
'- 003502: 원본의 날짜 문자열은 `EXP17 2 2022`로 오인식됐다. ROI 1은 전화번호가 포함된 주소, ROI 2는 `11200`을 읽었다. 현재 ROI 기준이 높은 OCR 점수와 구분자에 치우쳐 실제 날짜 영역을 놓치는 사례다. CLAHE에서는 `EXP:07. 12.2022`를 읽었지만 날짜 순서와 후보 선택 문제가 남았다.',
'- 003556: 원본·CLAHE·복구 검출에서 정답 날짜를 읽지 못했다. 이 경우 문자열의 MDY 해석 규칙만 추가해도 정답을 얻을 수 없다.',
'- 003565: CLAHE OCR 출력이 `15/07/2021`이었다. 정답 `2021-07-05`와 다른 숫자가 인식돼 파서 규칙만으로 확정 교정할 수 없다.',
'']
raw=[json.loads(s) for s in (OUT/'p3.jsonl').read_text(encoding='utf-8').splitlines()]
candidate_miss=[]
selection_miss=[]
for r in raw:
    target=b[r['image_id']]
    if target['kind']=='full' and not target['correct']:
        (selection_miss if any(c['value']==target['truth'] for c in r['candidates']) else candidate_miss).append(r['image_id'])
(OUT/'error_diagnostics.json').write_text(json.dumps({'full_date_correct_candidate_present_but_not_selected':selection_miss,'full_date_correct_candidate_absent':candidate_miss},indent=2),encoding='utf-8')
text += ['',
'## 4. 적용 판단과 남은 검증',
'',
f'- 개선안의 완전 날짜 오답 중 {len(selection_miss)}건은 정답 후보가 있었지만 선택되지 않았다. {len(candidate_miss)}건은 최종 후보 목록에 정답이 없었다. 후자는 OCR 인식, 날짜 파싱, 조기 종료의 원인을 이미지·원시 로그로 추가 분리해야 하며 모두 OCR 오류라고 단정하지 않는다.',
'- 새 요구사항 테스트는 p1 7/7, p2 11/11, p3 13/13을 통과했다. 기존 테스트는 baseline 15/15, p3 13/15였다. p3의 실패 2건 중 하나는 과거 날짜를 거부해야 한다는 기존 기대값과의 정책 차이이고, 다른 하나는 낮은 신뢰도의 제조일/소비기한 쌍을 놓치는 회귀다.',
'- 회귀 재현 입력은 신뢰도 0.65인 `제조 25.09.05`와 다음 줄 `26.03.04`다. 기존 기대값은 2026-03-04이지만 개선안은 NONE을 반환했다. 전역 최후 날짜 선택을 제거할 때 낮은 점수의 실제 기한 쌍을 보존하는 별도 근거가 필요하다.',
'- 운영 코드에는 반영하지 않았다. 회귀 오류가 남아 있으므로 즉시 배포할 단계는 아니다. 과거 연도·부분 날짜의 입출력 계약을 먼저 정리하고, 날짜 순서의 모호함과 낮은 신뢰도 날짜 쌍 선택을 보완한 뒤 기존 검증셋도 다시 평가해야 한다.',
'- 서로 다른 crop/원본 좌표 사이의 연산은 이번에 차단했다. 원본 좌표로 환산하여 여러 패스의 공간 정보를 결합하는 구현은 아직 검증하지 않았다.',
'- 외부 VLM, 모델 학습, 새로운 검출 모델, 선택적 추가 ROI 정책은 이번 수치에 포함하지 않았다. 기존 파이프라인의 ROI·CLAHE·복구 검출·조건부 타일 경로는 그대로 사용했다.',
'',
'## 5. 측정 조건과 원본 보존',
'',
'- 정답: 사용자가 수정한 manual.xlsx의 `검수 정답지!C2:C365`. 원본 CSV와 inspect.ndjson은 정답으로 사용하지 않았다.',
'- 판독 입력: 003353.jpg부터 003716.jpg까지 이미지 364장만 사용했다. metadata/annotations.json, 이전 라벨 매핑, 이미지 ID별 정답 예외 규칙은 사용하지 않았다.',
'- 완전일치는 정규화된 문자열 전체를 비교했다. 부분 날짜는 NONE-MM-DD 또는 YYYY-MM-NONE, 유효 날짜 부재는 NONE이다. 실행 예외는 실패로 처리한다.',
'- Windows, Intel Core Ultra 7 256V(8코어), CPU 스레드 4개. baseline과 개선안은 순서대로 각각 한 번 실행했다. 모델은 로컬 PP-OCRv5 mobile 검출, PP-OCRv6 small 복구 검출, korean PP-OCRv5 mobile 인식이다.',
'- baseline은 20260909 audit의 완료된 364장 실행 기록을 재사용했다. 원본 3개·이미지 364장·운영 코드 2개의 해시와 정답 스냅샷을 확인했다. 앞선 p3 282장 중단 기록은 최종 채점과 시간에서 제외하고 20260910에 364장 전부를 새 프로세스로 실행했다.',
'- baseline에는 당시 가중치의 해시가 없어 과거 가중치 동일성을 완전히 입증할 수 없다. 이번 검증 중 가중치 해시를 기록하고 완료 시점에 다시 대조했다. 모델 로딩 경로·설정·패키지 버전과 동일 입력 첫 OCR 출력 비교를 추가 근거로 사용했다.',
'- 초기화 포함 시간은 검증 스크립트 내부 측정 구간이며, OS 프로세스 생성 이전이나 OS 파일 캐시 초기화 시간을 포함하지 않는다. 원시 로그 계측 오버헤드는 포함된다. 개발 PC의 다른 활동은 완전히 통제하지 않았다.',
'- 이미 알려진 오류 유형을 바탕으로 설계한 개발 검증이다. 독립 블라인드 평가가 아니며 이 364장의 정확도를 일반화 성능으로 주장하지 않는다. 정답 채점 후 실험 규칙을 재조정하지 않았다.',
'- 앞선 384/364(99.48%) 판독은 주석 정보와 시각 검토를 사용한 작업이었다. 이번 이미지 단독 CPU OCR과 입력 조건이 다르므로 동일 방식의 재현 성능으로 볼 수 없다.',
'- 원본 CSV·XLSX·inspect.ndjson 세 파일의 SHA-256이 실행 전후 동일함을 확인했다. 운영 코드와 가중치도 수정하지 않았다.',
'',
'## 6. 저장 파일',
'',
'baseline과 p3의 새 XLSX는 원본 시트명·8열·정답·True/False 비교 수식을 유지했다. 각 단계의 CSV도 같은 8열을 사용한다. 실행 로그·측정 환경·채점 근거·테스트 결과·재현 코드는 labels/audit/validation_003353_003716_20260910에 있다.',
'',
'XLSX 생성 도구가 가져오기 과정에서 누락한 공유 수식의 후속 행은 새 파일에서만 원본과 동일한 수식으로 복원했다. 계산 결과와 CSV를 364행 전수 대조했고, 글꼴·채우기·테두리·정렬·표시 형식·보호 속성의 원본 대비 차이는 0건이었다. 표·고정 창도 보존했다. 각 새 XLSX의 inspect.ndjson에는 저장 파일 해시와 값·수식을 기록했다. 수식은 Artifact Tool에서 재계산하고 저장 파일은 별도 읽기 도구로 검산했으며 실제 Microsoft Excel 앱의 재계산은 시험하지 않았다.',
'']
target=LABELS/'validation_003353_003716_report_20260910.md'
target.write_text('\n'.join(text),encoding='utf-8')
print(target)
