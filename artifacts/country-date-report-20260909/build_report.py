"""Produce a readable report and a complete per-image evidence ledger."""
import json
from collections import Counter
from pathlib import Path

BASE=Path(__file__).parent
SOURCE=Path('C:/ITDA_OCR_CODE/상품사진입니다')
EU=set('이탈리아 폴란드 스페인 독일 프랑스 벨기에 네덜란드 덴마크 오스트리아 포르투갈 크로아티아 그리스 핀란드 아일랜드 리투아니아 루마니아'.split())
METHODS={
 'insufficient_evidence':'미확정: 이번 판독에서 근거 부족',
 'origin_text_ocr':'잠정: 원산지/제조국 문구 OCR',
 'manufacturer_address_inference':'잠정: 국내 제조주소 추정',
 'domestic_item_report_inference':'잠정: 국내 품목보고번호 추정',
 'visual_origin':'원본/확대 이미지에서 원산지 확인',
 'visual_manufacturer_country':'원본/확대 이미지에서 제조국 확인',
 'visual_manufacturer_address':'원본/확대 이미지에서 제조주소 확인',
 'ingredient_scope_excluded':'미확정: 원재료 등 다른 범위의 국가 제외',
 'conflicting_origin':'미확정: 국가 단서 상충',
}

def esc(value):return str(value).replace('|','／').replace('\n',' ')
def photo(r):return f"[{r['image_id']}]({(SOURCE/r['filename']).as_posix()})"

rows=json.loads((BASE/'country_screening.json').read_text(encoding='utf-8'))
rules=json.loads((BASE/'country_rules.json').read_text(encoding='utf-8'))
files={p.stem:p for p in SOURCE.iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png'}}
expected={f'{i:06d}' for i in range(1,3353)}
assert set(files)==expected and len(rows)==3352 and {r['image_id'] for r in rows}==expected
assert all(files[r['image_id']].name==r['filename'] for r in rows)
counts=Counter(r['country'] for r in rows)
methods=Counter(r['method'] for r in rows)
reviewed=sum(r['visual_review'] for r in rows)
known=3352-counts['미확정']
country_names=sorted((x for x in counts if x!='미확정'),key=lambda x:(-counts[x],x))
def rule(c):
 return rules.get('EU' if c in EU else '호주' if c=='뉴질랜드' else c,
                  {'order':'추가확인 필요','note':'일괄 파싱 규칙을 설정하지 않음.','source':'','reference':''})

for r in rows:
 r['country_rule_hint']=rule(r['country'])['order'] if r['country']!='미확정' else '국가 기반 규칙 없음'
 r['country_rule_is_automatic_parse']=False
 r['review_status']='visual_checked' if r['visual_review'] else 'requires_review'
 r['source_path']=(SOURCE/r['filename']).as_posix()
summary={'as_of':'2026-09-09','source_path':str(SOURCE),'total_photos':3352,
 'provisionally_assigned':known,'unresolved':counts['미확정'],'visually_checked_classification_rows':reviewed,
 'counts_by_country':dict(counts),'counts_by_method':dict(methods),
 'warning':'전수 OCR 스크리닝의 잠정 결과. 확정 제조국 분포나 학습용 정답 라벨이 아님. 미확정은 이번 분석으로 미확정이라는 뜻.',
 'percent_denominator':3352,'counts_reconcile':sum(counts.values())==3352,
 'source_files_modified':False,'source_date_labels_modified':False}
(BASE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(BASE/'country_screening.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')

report=f'''# 상품사진 국가 분류와 기한 날짜 해석

기준일: 2026-09-09. 분석 폴더: `{SOURCE}`. 범위: 000001–003352, 사진 3,352장.

## 결론

생산국은 날짜 해석에 도움이 되는 보조 정보이지만, 생산국 하나로 YMD/DMY/MDY를 고정하면 안 됩니다. 같은 네덜란드산에서도 003172번은 DMY 해석의 근거가 강하고, 002560번은 라벨에 YMD라고 명시되어 있습니다. **제품에 적힌 날짜 순서 안내와 해당 숫자열의 의미가 국가의 일반 관행보다 우선**입니다.

## 분류 범위와 신뢰도

- 전체 3,352장을 로컬 OCR로 스크리닝했습니다. 기존 OCR 캐시 2,042건을 재사용하고 미처리 1,310건을 추가 처리했습니다. 중요·오인 위험 사례 {reviewed}건의 국가 분류는 원본 또는 확대 이미지로 확인했습니다. 3,352장을 모두 사람이 육안 검수한 결과는 아닙니다.
- 국가를 잠정 배정한 사진은 **{known:,}장({known/3352:.2%})**, 이번 분석에서 **미확정은 {counts['미확정']:,}장({counts['미확정']/3352:.2%})**입니다. 미확정에는 국가가 화면 밖에 있는 경우뿐 아니라 OCR 누락·작은 글씨·범위 혼동도 포함됩니다.
- 따라서 아래 표는 **현재 근거로 배정한 사진 수와 전체 대비 비율**입니다. 실제 전체 제조국 구성비가 확정됐다는 뜻이 아니며, 알려진 사진만을 모집단처럼 취급하지 않았습니다. 미확정 표본을 임의로 한국산으로 채우지 않았습니다.
- ‘국가’는 완제품의 원산지/제조국 표시를 우선했습니다. 국내 제조업체 주소 및 품목보고번호에 근거한 배정은 추정으로 구분했습니다. 국내 소분·포장 공정이 있으면 원재료 원산지와 최종 제조·포장국은 별도 확인해야 합니다.
- 집계 단위는 **사진 파일**입니다. 동일 제품의 반복 사진·회전본을 별개 사진으로 셌으므로 고유 상품 수나 SKU 비중이 아닙니다. 국가가 배정되지 않은 사진도 사진별 파일에 모두 들어 있습니다.
- 한글 표시, 수입업체 주소, 브랜드 국적, 바코드 앞자리만으로 제조국을 확정하지 않았습니다. GS1도 접두번호가 제품 원산지를 뜻하지 않는다고 설명합니다. [GS1 공식 설명](https://www.gs1.org/standards/id-keys/company-prefix)
- 치실·마스크·렌즈 등 비식품 후보도 일부 포함됩니다. 국가별 사진 집계에는 포함하되 아래 **식품** 표시 규정을 해당 비식품에 그대로 적용하면 안 됩니다.

## 국가별 잠정 집계

분모는 모두 3,352장입니다. ‘육안 확인’은 위 잠정 배정 수에 포함된 부분집합이며 별도로 더하지 않습니다.

| 국가 | 잠정 배정 사진 | 전체 대비 | 이 중 육안 확인 | 식품 날짜의 일반 기준/주의 |
|---|---:|---:|---:|---|
'''
for c in country_names:
 n=counts[c];v=sum(r['country']==c and r['visual_review'] for r in rows)
 report+=f'| {c} | {n:,} | {n/3352:.2%} | {v} | {rule(c)["order"]} |\n'
report+=f'| 미확정 | {counts["미확정"]:,} | {counts["미확정"]/3352:.2%} | 0 | 자동 결정하지 않음 |\n| 합계 | 3,352 | 100.00% | {reviewed} | 사진 수 기준 |\n'
report+='\n### 근거 유형별 집계\n\n| 근거 유형 | 사진 수 |\n|---|---:|\n'
for method,n in methods.most_common():report+=f'| {METHODS[method]} | {n:,} |\n'
report+='''
## 실제 사진에서 확인한 날짜 해석

다음 사례는 원본을 확인했습니다. ‘일반 기준과 다름’은 수출용/한국 유통용 라벨에서 실제로 확인되는 표기 차이라는 뜻이지 법 위반 판단이 아닙니다. 숫자 옆의 EXP, Best before, Sell by 등 기한 종류도 별도로 보존해야 합니다.

| 사진 | 국가/상품 | 날짜 원문 | 실제 적용 | 정규화 예시 | 판단 근거 |
|---|---|---|---|---|---|
'''
examples=[('003172','네덜란드 / Beemster 고다치즈','DMY (맥락상 유력)'),
 ('002560','네덜란드 / JUST CANDY 젤리빈','YMD (명시)'),
 ('002633','독일 / 트롤리 미니버거젤리','YMD (명시)'),
 ('002221','프랑스 / 레옹 청포도젤리','YMD (명시·국내 소분)'),
 ('001498','스위스 / 린트 초콜릿','YMD (명시)'),
 ('001496','태국 / 호올스 자몽향 캔디','YMD (명시)'),
 ('002072','중국 / 스키틀즈 사워','DMY (명시)'),
 ('000379','중국 / 이클립스 캔디','DMY (명시)'),
 ('001078','미국 / Kirkland 사과식초','YMD (명시·SELL BY)'),
 ('001487','스페인 / 포도씨유','DMY (명시)'),
 ('003010','필리핀 / Sucere 캔디','MDY (명시)'),
 ('002412','크로아티아 / 차','YMD (숫자 위치·유효성)')]
lookup={r['image_id']:r for r in rows}
for image_id,product,order in examples:
 r=lookup[image_id]
 report+=f'| {photo(r)} | {product} | `{r["example_raw_date"]}` | {order} | `{r["example_normalized_date"]}` | {esc(" / ".join(r["date_evidence"]) if r["date_evidence"] else "원산지·인쇄 날짜 직접 확인")} |\n'
report+='''
003172번에는 `Imported from Holland`, `CONO Kaasmakers`, `Middenbeemster, Holland`, `NL Z 0114 EG`가 있습니다. `Best before: see label`도 보입니다. EU Annex X의 일-월-년 기준과 함께 보면 **2021-06-20이 가장 타당한 해석**입니다. 다만 이 사진에 `DD-MM-YY`라는 순서 안내가 직접 적혀 있는 것은 아니므로 ‘명시 형식’과 ‘국가·규정으로 해소한 모호성’을 구분했습니다. `120917`은 별도의 숫자열이며 추가 확인 없이 기한 날짜로 바꾸지 않습니다.

001487번은 OCR이 ‘월일년순’으로 잘못 읽었지만 원본은 **‘일/월/년순’**입니다. 국가 추론뿐 아니라 순서 안내 자체의 OCR도 검수해야 합니다. 000779번 캐나다산 표시는 확인했으나 `03 06 2026`은 이 사진의 국가 정보만으로 월/일 순서를 확정하지 않았습니다.

### 국가 단어를 잘못 쓰기 쉬운 사례

- 000045: 식품 제조원은 부산의 라이온제과. 중국은 함께 판매하는 완구의 제조국입니다.
- 001127: 싱가포르는 별첨 분말스프의 원산지입니다. 과자 제조/판매원 표시는 한국 업체와 평택 주소입니다.
- 002461: `Tin made in China`는 틴 용기의 제조국입니다. 이 문구만으로 식품을 중국산으로 배정하지 않았습니다.
- 001078: 한국어 수입 스티커가 있어도 원산지는 미국입니다. 날짜 의미도 소비기한과 완전히 동일한 것으로 간주하지 않고 `SELL BY`로 보존합니다.

## 국가별 식품 표시 기준과 적용 한계

아래 기준은 해당 국가의 식품 판매 라벨 규정·공식 안내입니다. 제조국의 규정이 모든 수출 라벨을 결정한다는 의미가 아닙니다. 과거 촬영 사진은 촬영·제조 당시의 규정과 원표시를 확인해야 하며, 아래 자료만으로 2026년 각국 수출입 적법성을 판단하지 않습니다.

YMD=년-월-일, DMY=일-월-년, MDY=월-일-년. DM=일-월, MY=월-년. 생략된 일/년을 임의로 채우면 안 됩니다.

| 국가/지역 | 일반 기준 | 예외와 실무 해석 | 공식 근거 |
|---|---|---|---|
'''
for c,data in rules.items():
 if c!='EU' and c not in counts:continue
 label='EU: '+', '.join(c for c in country_names if c in EU) if c=='EU' else '호주·뉴질랜드' if c=='호주' else c
 report+=f'| {label} | {data["order"]} | {data["note"]} | [{data["reference"].split(";")[0]}]({data["source"]}) |\n'
report+='''
중국 GB 7718-2025의 강제 시행은 2027-03-16로 안내되어 있습니다. 과거 사진에 새 기준을 소급 적용하지 않았습니다. [중국 베이징 시장감독관리국 안내](https://scjgj.beijing.gov.cn/zwxx/scjgdt/202605/t20260507_4639154.html)

## OCR 시스템에 적용할 판단 순서

1. **기한 종류와 대상 영역**: EXP/소비기한/유통기한/Best before와 MFG/제조일, 포장일, LOT 번호를 먼저 분리합니다. 배경의 다른 상품 날짜도 제외합니다.
2. **제품에 적힌 순서 안내**: `년월일순`, `일월년순`, `DD/MM/YY`, `YYYY.MM.DD`가 있으면 해당 숫자열에 연결합니다. 한국 수입 스티커와 원포장 안내가 충돌하면 검수 대상으로 둡니다.
3. **달력으로 불가능한 후보 제거**: 월은 1–12, 일은 해당 월의 실제 날짜 범위, 윤년을 검사합니다. 월 이름이 있으면 월 위치를 직접 알 수 있습니다. 네 자리 연도의 위치도 강한 단서입니다.
4. **검증된 제품/제조사별 포맷**: 같은 브랜드라도 제조공장·판매시장·SKU에 따라 다를 수 있으므로 실제 확인된 범위에서만 재사용합니다.
5. **판매 라벨의 적용 국가와 제조국**: 원산지·제조업체 주소·수입 표시를 구분한 뒤 국가 규칙을 후보 간 우선순위로 사용합니다. 국가만으로 확정하지 않습니다.
6. **남은 모호성 보존**: `20-06-21`처럼 후보가 둘 남으면 후보 목록과 판단 근거를 남깁니다. 국가 미확정·순서 미확정은 별개 상태입니다. 최종 근거가 부족하면 검수를 요청합니다.

국가 필드와 별도로 `date_type`, `raw_date`, `explicit_date_order`, `normalized_date`, `decision_basis`, `review_status`를 두는 방식이 적절합니다. 국가가 없어도 날짜 순서가 명시되어 있으면 읽을 수 있고, 국가를 알아도 순서가 미확정일 수 있습니다. 기존 학습용 날짜 정답 파일은 이번 조사에서 수정하지 않았습니다.

### 사용자 예시 정정

- `23/02/2024`: 질문의 세 후보 형식 중 DMY만 달력상 유효하므로 **2024-02-23**.
- `26/12/24`: YMD면 **2026-12-24**, DMY면 **2024-12-26**. **2024-12-23은 이 숫자열에서 나오지 않습니다.**
- 두 자리 연도의 세기는 촬영 시기·제조일·제품 정보와 함께 판단합니다. 이 데이터에 과거 사진이 있으므로 현재 연도 근처의 날짜만 허용하면 안 됩니다.

## 확정 국가 비중을 얻기 위해 남은 작업

현재 결과는 완성된 국가 정답셋이 아닙니다. 미확정 사진과 잠정 분류를 원본으로 재검수하고, 라벨이 화면 밖인 경우 같은 제품의 뒷면 사진·공식 제조사 자료·수입신고 자료가 필요합니다. 표기된 원산지와 국내 소분국을 별도 필드로 분리한 뒤 재집계해야 합니다. 같은 제품/회전본의 연결은 확인된 경우에만 적용하고, 학습·검증 분할에서도 같은 원본이 양쪽에 섞이지 않도록 관리하는 편이 좋습니다.

사진별 근거와 원본 링크는 `사진별_국가분류.md`, 프로그램용 전체 결과는 `country_screening.json`에 있습니다. 미확정은 이번 증거의 한계를 나타냅니다.
'''
(BASE/'국가별_날짜해석_조사보고서.md').write_text(report,encoding='utf-8')
ledger='''# 사진별 국가 분류 근거 (잠정)

3,352장 전체 목록. 국가 미확정과 날짜 순서 미확정은 서로 다릅니다. ‘국가 일반기준’은 해당 사진에 자동 적용한 형식이 아닙니다. 육안 확인 표시가 없는 행은 OCR 후보/추정이며 학습용 정답으로 사용하기 전에 검수가 필요합니다.

| 사진 | 잠정 국가 | 분류 근거 유형 | 국가 근거 | 라벨 순서 후보 | 순서 근거 | 국가 일반기준 |
|---|---|---|---|---|---|---|
'''
for r in rows:
 ledger+=f'| {photo(r)} | {r["country"]} | {METHODS[r["method"]]} | {esc(" / ".join(r["evidence"])) or "미확인"} | {", ".join(r["date_order_explicit"]) or "미확인"} | {esc(" / ".join(r["date_evidence"])) or "미확인"} | {r["country_rule_hint"]} |\n'
(BASE/'사진별_국가분류.md').write_text(ledger,encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
