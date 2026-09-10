"""Rebuild the comparison using the historical-year-unrestricted baseline."""
import json
from pathlib import Path
OUT=Path(__file__).resolve().parent
scores=json.loads((OUT/'scores.json').read_text(encoding='utf-8'))
data=json.loads((OUT/'workbook_data.json').read_text(encoding='utf-8'))
paired=json.loads((OUT/'paired_timing.json').read_text(encoding='utf-8'))
baseline,improved=scores['baseline'],scores['p3']
assert improved['correct']==284 and all(v['total']== 364 for v in scores.values())
def exact(stage):
    s=scores[stage]
    return f'{s["correct"]}/364 ({s["accuracy"]*100:.2f}%)'
def category(stage,kind):
    s=scores[stage]['categories'][kind]
    return f'{s["correct"]}/{s["total"]} ({s["correct"]/s["total"]*100:.2f}%)'
def records(stage): return {r['image_id']:r for r in data[stage]['records']}
def changes(a,b):
    left,right=records(a),records(b)
    return {'gained':[k for k in left if not left[k]['correct'] and right[k]['correct']],
            'lost':[k for k in left if left[k]['correct'] and not right[k]['correct']]}
comparisons={f'{a}_to_{b}':changes(a,b) for a,b in [('baseline','p3'),('baseline','baseline_replay'),('baseline_replay','p1_replay'),('p1_replay','p2_replay'),('p2_replay','p3_replay')]}
(OUT/'comparisons.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2),encoding='utf-8')
change=comparisons['baseline_to_p3']
delta=(improved['accuracy']-baseline['accuracy'])*100
ratio=improved['runtime']['loop_wall_seconds']/baseline['runtime']['loop_wall_seconds']
lines=[
'# 소비기한 OCR 364장 검증 결과 — 연도 하한 제거 기준으로 수정',
'',
f'연도 하한만 제거해 새로 실행한 기준군은 {exact("baseline")}, 기존 개선안은 {exact("p3")}다. 개선안의 정확도 차이는 {delta:+.2f}%p이며, 새 기준 대비 정답으로 바뀐 사례는 {len(change["gained"])}건, 오답으로 바뀐 사례는 {len(change["lost"])}건이다.',
'',
'기준군은 이번에 이미지 364장을 처음부터 다시 실행했다. 개선안의 예측값과 처리시간은 앞서 완료한 364장 실행 기록을 검증하여 재사용했으며 새로 실행한 수치가 아니다. 개선안 XLSX·CSV에는 새 기준 대비 개선/회귀/양쪽 정답/양쪽 오답을 비고에 반영했다.',
'',
'## 1. 이번에 변경한 기준',
'',
'- 기존 `date_extraction.MIN_YEAR=2024`만 실행 프로세스 안에서 `1`로 변경했다. 날짜 검증의 연도 하한을 없앤 것이며 상한 `MAX_YEAR=2035`는 유지했다.',
'- 검출·인식 모델, OCR 설정, ROI·CLAHE·복구·타일, 조기 종료, 날짜 파싱, 문맥 점수, 출력 형식은 변경하지 않았다. 부분 날짜 지원이나 MDY 해석 개선도 기준군에 추가하지 않았다.',
'- 날짜 쌍 선택 함수 안의 `year >= 2024` 후보 구분은 날짜 유효성 거부 설정과 다른 규칙이므로 그대로 유지했다. 두 자리 연도 해석과 기존 정규식의 표현 범위도 유지했다.',
'- 운영 소스·가중치·원본 정답 파일은 수정하지 않았다. 이미지 판독 프로세스는 정답이나 annotations를 읽지 않는다.',
'',
'## 2. 이미지 전수 실행 비교',
'',
'| 항목 | 새 기준군: 연도 하한만 제거 | 개선안 p3: 기존 실행 재사용 |',
'| --- | ---: | ---: |',
f'| 전체 완전일치 | {exact("baseline")} | {exact("p3")} |',
*[f'| {label} | {category("baseline",kind)} | {category("p3",kind)} |' for label,kind in [('완전 날짜','full'),('부분 날짜','partial'),('NONE','none')]],
f'| 이미지 처리 구간 | {baseline["runtime"]["loop_wall_seconds"]:.1f}초 | {improved["runtime"]["loop_wall_seconds"]:.1f}초 |',
f'| 초기화 포함 전체 측정 구간 | {baseline["runtime"]["total_wall_seconds"]:.1f}초 | {improved["runtime"]["total_wall_seconds"]:.1f}초 |',
f'| 이미지별 중앙값 | {baseline["median_image_seconds"]:.2f}초 | {improved["median_image_seconds"]:.2f}초 |',
f'| 이미지별 p95 | {baseline["p95_image_seconds"]:.2f}초 | {improved["p95_image_seconds"]:.2f}초 |',
f'| OCR 호출 수 | {sum(baseline["pass_counts"].values())} | {sum(improved["pass_counts"].values())} |',
f'| 복구 검출 실행 수 | {baseline["pass_counts"].get("recovery:original",0)} | {improved["pass_counts"].get("recovery:original",0)} |',
f'| 실행 오류 | {baseline["error_types"].get("실행 오류",0)} | {improved["error_types"].get("실행 오류",0)} |',
'',
f'관측된 개선안/기준군 이미지 처리시간 비는 {ratio:.3f}다(1 미만이면 개선안이 짧음). 서로 다른 시점의 단일 실행이므로 코드 변경만의 속도 효과로 단정하지 않는다. 첫 원본 OCR 입력은 364장 모두 동일했고 문자열 출력은 {paired["same_text_count"]}/364장, 좌표·신뢰도까지 포함한 출력은 {paired["same_full_ocr_lines_count"]}/364장이 같았다. 같은 첫 OCR 패스의 개선안/기준군 시간비 중앙값은 {paired["median_p3_over_baseline_ratio"]:.3f}였다.',
'',
f'이미지 처리시간은 관측값 기준 {(1-ratio)*100:.2f}% 줄었다. 따라서 이전의 약 2배 속도 개선 표현은 {(1-ratio)*100:.2f}% 단축으로 수정한다. p95는 두 실행에서 거의 같아, 전체 평균 시간 감소가 느린 이미지의 지연까지 줄였음을 뜻하지는 않는다.',
'',
f'500장 선형 환산(이미지 처리 구간)은 기준군 {baseline["runtime"]["loop_wall_seconds"]*500/364:.0f}초, 개선안 {improved["runtime"]["loop_wall_seconds"]*500/364:.0f}초다. 실제 500장이나 공식 4-vCPU 환경을 측정한 것이 아니다. 프로젝트의 2,400초 한도·1,800초 내부 목표 통과 여부를 이 값으로 확정하지 않는다.',
'',
'## 3. 새 기준 대비 정답 증감',
'',
'| 구분 | 새로 맞힌 건수 | 새로 틀린 건수 | 정답 수 순증감 |',
'| --- | ---: | ---: | ---: |']
a,b=records('baseline'),records('p3')
for label,kind in [('완전 날짜','full'),('부분 날짜','partial'),('NONE','none')]:
    gain=sum(k in change['gained'] for k in a if a[k]['kind']==kind)
    loss=sum(k in change['lost'] for k in a if a[k]['kind']==kind)
    lines.append(f'| {label} | {gain} | {loss} | {gain-loss:+d} |')
lines += ['',
'개선·회귀의 전체 이미지 ID는 audit의 comparisons.json에 저장했다. 개선안의 B열 예측값과 C열 정답은 이전 결과와 같고 H열 비교 설명만 새 기준에 맞춰 갱신했다.',
'',
'새 기준에서는 맞았으나 개선안에서 틀린 사례는 다음과 같다.',
'',
'| image_id | 정답 및 새 기준군 | 개선안 |',
'| --- | --- | --- |',
*[f'| {key} | {a[key]["truth"]} | {b[key]["prediction"]} |' for key in change['lost']],
'',
'## 4. 동일 OCR 출력에 대한 단계별 후처리 비교',
'',
'이번에 새로 실행한 기준군의 OCR 출력 전체를 고정하여 아래 네 단계를 다시 계산했다. 이전 연도 제한 기준군에서 얻은 OCR 캐시는 사용하지 않았다. 조기 종료나 추가 OCR 경로를 재현하는 실측이 아니며 후처리 시간은 전체 처리시간과 비교할 수 없다.',
'',
'| 단계 | 적용 규칙 | 완전일치 | 후처리 측정 구간 |',
'| --- | --- | ---: | ---: |']
for stage,label in [('baseline_replay','연도 하한만 제거한 기존 선택 규칙'),('p1_replay','기존 p1: 연도 2000–2099 및 부분 날짜 지원'),('p2_replay','p1 + 날짜 순서·영문 월 표기'),('p3_replay','p2 + 좌표계·근접 문맥 분리 및 전역 최후 날짜 선택 제거')]:
    lines.append(f'| {stage} | {label} | {exact(stage)} | {scores[stage]["runtime"]["parser_only_seconds"]:.3f}초 |')
lines += ['',
'기존 p1/p2/p3의 규칙은 수정하지 않았다. 따라서 p1에는 부분 날짜 지원뿐 아니라 기준군과 다른 연도 상한(2099)도 포함된다. 이 표를 부분 날짜 규칙 하나의 독립 기여도로 해석하지 않는다. p3 재평가와 개선안 실제 실행은 이용한 OCR 증거와 조기 종료 경로가 달라 직접적인 순수 후처리 비교가 아니다.',
'']
for key,values in comparisons.items():
    if key!='baseline_to_p3': lines.append(f'- {key}: 정답으로 개선 {len(values["gained"])}건, 정답을 잃은 사례 {len(values["lost"])}건.')
lines += ['', '## 5. 지정 사례', '', '| image_id | 정답 | 새 기준군 | 기존 개선안 |', '| --- | --- | --- | --- |']
for key in ('003493','003567','003411','003504','003534','003558',):
    lines.append(f'| {key} | {a[key]["truth"]} | {a[key]["prediction"]} | {b[key]["prediction"]} |')
lines += ['',
'## 6. 적용 판단과 한계',
'',
'- 기존의 10/364(2.59%)·초기화 포함 3,484.3초는 연도 제한이 켜진 과거 기록이다. 이제 주 비교 기준에서 제외했으며 이전 파일은 백업으로 보관했다. 이전에 제시했던 +70.98%p와 약 2배 속도 차이는 이번 기준군에 적용하지 않는다.',
f'- 개선안의 전체 정확도 차이는 새 기준 대비 {delta:+.2f}%p다. 유형별 정답 증감을 함께 판단해야 하며 총점 상승만으로 모든 규칙이 개선됐다고 볼 수 없다.',
f'- 적용 판단은 조건부다. 정답 순증은 {len(change["gained"])-len(change["lost"])}건이며 그중 부분 날짜 순증이 7건이다. 우선 위 회귀 3건과 낮은 신뢰도 날짜 쌍 실패를 수정한 뒤, 같은 설정의 전체 재실행과 공식 자원 조건의 속도 검증을 거쳐 운영 반영을 판단한다. 이번 작업에서는 해당 개선 코드를 수정하거나 배포하지 않았다.',
'- 새 기준군은 기존 단위 테스트 15개 중 14개를 통과했다. 실패한 1개는 2020년 날짜를 거부해야 한다는 이전 정책 기대값으로, 이번 요청에 따른 의도된 차이다. 미래 상한·달력 유효성·부분 날짜 미지원 유지 검사는 통과했다.',
'- 기존 개선안은 새 요구사항 테스트 13/13, 기존 테스트 13/15 기록을 유지한다. 과거 날짜 정책 차이 외에 낮은 신뢰도의 제조일/기한 쌍을 놓치는 실제 회귀가 남아 있다. 운영 코드에는 반영하지 않았다.',
'- 정답은 사용자 수정본 manual.xlsx의 C2:C365이며 문자열 전체가 같아야 정답이다. 부분 날짜는 NONE-MM-DD 또는 YYYY-MM-NONE, 유효 날짜 없음은 NONE으로 비교한다. 실행 예외는 정답이 NONE이어도 실패 처리한다.',
'- Windows 개발 PC(Intel Core Ultra 7 256V, 8코어)에서 OCR 스레드 4개를 사용했다. 모델·패키지·설정·이미지·코드·가중치의 일치를 확인했다. 다른 장비 활동과 OS 캐시를 통제하지 않았고 모델 초기화 및 로그 기록 오버헤드가 측정에 포함된다.',
'- 이미 알고 있는 개발 검증셋이며 독립 블라인드 테스트가 아니다. 앞선 주석 정보·시각 검토 방식의 99.48%를 재현한 점수도 아니다. 정답을 판독 입력이나 ID별 예외 규칙으로 사용하지 않았다.',
'',
'## 7. 저장과 보존',
'',
'기준·개선안 XLSX와 대응 CSV·inspect.ndjson, 단계별 CSV, 이 보고서는 기존 _20260910 파일명으로 갱신한다. 원본 manual.csv·manual.xlsx·manual.xlsx.inspect.ndjson은 수정하지 않는다.',
'',
'새 실행·채점·비교 근거는 labels/audit/validation_003355_003718_20260910_year_unrestricted에 저장한다. 그 아래 previous_results에 교체 전 결과 11개를 보관한다. 이전 audit 디렉터리의 원시 실행 기록은 역사 기록으로 남긴다.',
'',
'XLSX는 기존 8열·정답·비교 수식·서식을 유지한다. 생성 도구에서 빠지는 공유 수식 행은 원본과 동일하게 복원하고 글꼴·빈 테두리 메타데이터는 원본으로 보존한다. Artifact Tool 재계산과 별도 읽기 도구의 전수 검산을 실시하며 실제 Excel 앱 재계산은 시험하지 않는다.',
'']
target=OUT/'outputs/validation_003355_003718_report_20260910.md'
target.write_text('\n'.join(lines),encoding='utf-8')
print(target)
