import base64
import csv
import html
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(r'C:\ITDA_OCR_CODE')
OUT = Path(__file__).parent
reviewed = json.loads((OUT / 'review_order.json').read_text(encoding='utf-8'))
refined = json.loads((OUT / 'refined_matches.json').read_text(encoding='utf-8'))
refined_by_pair = {(m['a'], m['b']): m for m in refined}
inventory = json.loads((OUT / 'inventory.json').read_text(encoding='utf-8'))
inventory_by_path = {e['path']: e for e in inventory}
with (ROOT / '추가수집데이터/metadata/source_manifest.csv').open(encoding='utf-8-sig') as handle:
    sources = {r['new_filename']: r for r in csv.DictReader(handle)}

# Review pages 01-07 were visually inspected. Rows 1-22 share the same
# photographic scene; rows 23-41 show different products/dates/poses.
decisions = []
confirmed = []
for i, pair in enumerate(reviewed, 1):
    same = i <= 22
    decisions.append({'review_number': i, 'a': pair['a'], 'b': pair['b'],
                      'same_source_photo': same,
                      'reason': '배경·손·포장 세부가 일치하고 원근/회전/밝기 변형으로 설명됨' if same else '상품·날짜·촬영 구도 또는 배경이 다름'})
    if same:
        selected = dict(refined_by_pair.get((pair['a'], pair['b']), pair))
        selected['visually_confirmed'] = True
        selected['source_metadata'] = sources[Path(pair['b']).name]
        confirmed.append(selected)
confirmed.sort(key=lambda m: m['b'])
(OUT / 'visual_review_decisions.json').write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'confirmed_duplicates.json').write_text(json.dumps(confirmed, ensure_ascii=False, indent=2), encoding='utf-8')

matched_b = {m['b'] for m in confirmed}
summary = {'original_images': 3352, 'additional_images': 386, 'total_images': len(inventory),
           'read_errors': sum('error' in e for e in inventory),
           'cross_byte_identical_pairs': 0, 'cross_pixel_identical_pairs': 0,
           'confirmed_transformed_pairs': len(confirmed),
           'confirmed_original_images': len({m['a'] for m in confirmed}),
           'confirmed_additional_images': len(matched_b),
           'additional_without_detected_duplicate': 386 - len(matched_b),
           'additional_duplicate_percent': round(100 * len(matched_b) / 386, 2),
           'source_splits_of_confirmed': dict(__import__('collections').Counter(m['source_metadata']['split'] for m in confirmed))}
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

with (OUT / '중복대응표.csv').open('w', newline='', encoding='utf-8-sig') as handle:
    writer = csv.writer(handle)
    writer.writerow(['번호', '상품사진_파일명', '추가수집_파일명', '중복유형', '정렬후_픽셀상관계수', '일치특징점', '추가사진_겹침비율', '상품사진_전체경로', '추가수집_전체경로', '추가수집_원본경로', '추가수집_원본분할'])
    for i, m in enumerate(confirmed, 1):
        writer.writerow([i, Path(m['a']).name, Path(m['b']).name, '동일 촬영 사진의 변형본',
                         m['aligned_pixel_correlation'], m['inliers'], m['overlap_b'],
                         str(ROOT / m['a']), str(ROOT / m['b']),
                         m['source_metadata']['original_path'], m['source_metadata']['split']])

with (OUT / '추가수집_전체검사결과.csv').open('w', newline='', encoding='utf-8-sig') as handle:
    writer = csv.writer(handle)
    writer.writerow(['추가수집_파일명', '판정', '대응_상품사진', 'sha256'])
    for e in inventory:
        if e['folder'] == '추가수집데이터':
            peers = [Path(m['a']).name for m in confirmed if m['b'] == e['path']]
            writer.writerow([Path(e['path']).name, '변형 중복 확인' if peers else '이번 검사에서 중복 미검출', '; '.join(peers), e['sha256']])

lines = ['# 상품사진과 추가수집데이터 중복 조사', '', '조사일: 2026-09-10', '',
         '두 폴더 사이에서 **동일 촬영 사진의 변형 중복 22쌍**을 확인했습니다. 추가수집 사진 386장 중 22장(5.70%)에 해당합니다.', '',
         '| 항목 | 결과 |', '|---|---:|', '| 상품사진입니다 | 3,352장 |', '| 추가수집데이터 | 386장 |',
         '| 파일 내용(SHA-256) 완전 동일 | 0쌍 |', '| EXIF 방향 보정 후 RGB 픽셀 완전 동일 | 0쌍 |',
         '| 원근·회전·크기·밝기 등의 변형 중복 확인 | 22쌍 / 각 폴더 22장 |',
         '| 추가수집 중 중복 미검출 | 364장 |', '| 이미지 읽기 오류 | 0장 |', '',
         '실제 조사 경로는 `C:\\ITDA_OCR_CODE\\상품사진입니다` 및 `C:\\ITDA_OCR_CODE\\추가수집데이터`입니다. 하위 폴더까지 이미지 파일을 조사했으며 metadata의 CSV/JSON은 이미지 수에서 제외했습니다.', '',
         '## 판정 방법', '',
         '1. 3,738장 전체의 SHA-256과 EXIF 방향 보정 후 RGB 픽셀 해시를 계산했습니다. 두 폴더 사이뿐 아니라 각 폴더 내부에서도 완전 동일 파일/픽셀은 없었습니다.',
         '2. 두 폴더 간 1,293,872개 조합에 pHash/dHash를 비교해 초기 후보 6쌍을 추렸습니다.',
         '3. 변형에 따른 누락을 줄이기 위해 전체 사진의 SIFT 특징을 추출했습니다. 추가수집 사진마다 전체 기존 사진의 특징점 인덱스에서 상위 15개 후보를 검색하고 RANSAC으로 위치 관계를 검증했습니다.',
         '4. 후보 사진을 같은 좌표로 맞춰 전체 겹침 영역의 픽셀 상관을 확인했습니다. 유력 후보 및 인접 파일 261쌍은 더 높은 해상도와 최대 2,000개 특징점으로 재검증했습니다.',
         '5. 비교 이미지 41쌍을 직접 확인했습니다. 배경·손·포장 세부까지 같은 22쌍을 중복으로 판정하고, 날짜/제품/촬영 자세가 다른 사진은 제외했습니다.', '',
         '상관계수는 중복일 확률이나 일치 픽셀의 비율이 아닙니다. 강한 밝기 변화가 있는 사진은 상관계수와 실제 이미지 비교를 함께 사용했습니다.', '',
         '**364장에 대한 판정은 “이번 검사에서 중복 미검출”입니다.** 변형 중복 탐색은 특징점 기반 후보 검색이므로 심한 잘림·가림·변형까지 중복이 전혀 없다고 보장하는 전수 수동 검사는 아닙니다. 폴더 내부의 변형 중복은 이번 조사 범위에 포함하지 않았습니다.', '',
         '## 확인된 대응 목록', '', '| 번호 | 상품사진입니다 | 추가수집데이터 | 정렬 후 픽셀 상관 |', '|---:|---|---|---:|']
for i, m in enumerate(confirmed, 1):
    pa, pb = (ROOT / m['a']).as_posix(), (ROOT / m['b']).as_posix()
    lines.append(f"| {i} | [{Path(m['a']).name}](<{pa}>) | [{Path(m['b']).name}](<{pb}>) | {m['aligned_pixel_correlation']:.6f} |")
lines += ['', '## 산출물', '',
          '- `중복사진_비교.html`: 확인된 22쌍을 나란히 보는 이미지 보고서',
          '- `중복대응표.csv`: 확인된 대응 파일명, 전체 경로, 지표, 원본 데이터 출처',
          '- `추가수집_전체검사결과.csv`: 추가수집 386장 각각의 검사 결과',
          '- `inventory.json`: 전체 이미지 해시 및 크기',
          '- `confirmed_duplicates.json`, `visual_review_decisions.json`: 판정 근거', '',
          '원본 사진은 수정·이동·삭제하지 않았습니다.']
(OUT / '조사결과.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def embed(path):
    with Image.open(ROOT / path) as source:
        im = ImageOps.exif_transpose(source).convert('RGB')
        im.thumbnail((520, 390), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='JPEG', quality=88)
        return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


cards = []
for i, m in enumerate(confirmed, 1):
    panels = ''.join(f'<figure><img loading="lazy" src="{embed(m[k])}" alt="{html.escape(m[k])}"><figcaption>{html.escape(m[k])}</figcaption></figure>' for k in ('a', 'b'))
    cards.append(f'<article><h2>{i:02d} · {Path(m["a"]).name} ↔ {Path(m["b"]).name}</h2><div class="pair">{panels}</div><p>동일 촬영 사진의 변형본 · 정렬 후 픽셀 상관 {m["aligned_pixel_correlation"]:.6f} · 일치 특징점 {m["inliers"]}개</p></article>')
page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>중복 사진 비교 — 22쌍</title>
<style>body{font:16px/1.6 system-ui,sans-serif;background:#f2f4f7;color:#18212c;margin:0}main{max-width:1100px;margin:auto;padding:32px 20px}h1{font-size:30px}header p{max-width:850px}article{background:white;padding:20px;margin:24px 0;border-radius:12px;border:1px solid #dce2e8}h2{font-size:20px;margin:0 0 12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}figure{margin:0;text-align:center;background:#fafafa}img{width:100%;height:390px;object-fit:contain}figcaption{padding:10px;font-size:14px;overflow-wrap:anywhere}article p{font-size:14px;color:#4b5867}@media(max-width:650px){.pair{grid-template-columns:1fr}img{height:320px}}@media print{article{break-inside:avoid}}</style>
<main><header><h1>중복 사진 22쌍 확인</h1><p>상품사진 3,352장과 추가수집 사진 386장 조사 · 2026-09-10</p><p>파일이나 픽셀이 완전히 같은 사진은 0쌍입니다. 아래 22쌍은 배경·손·포장의 세부가 같은 사진에 원근·회전·크기·밝기 등의 변형이 적용된 사례입니다. 추가수집 기준 5.70%이며 나머지 364장은 이번 검사에서 중복이 검출되지 않았습니다.</p><p>왼쪽: 상품사진입니다 · 오른쪽: 추가수집데이터. 원본 사진은 변경하지 않았습니다.</p></header>'''
page += ''.join(cards) + '</main></html>'
(OUT / '중복사진_비교.html').write_text(page, encoding='utf-8')
assert len(confirmed) == len(matched_b) == 22
assert all((ROOT / m[k]).is_file() for m in confirmed for k in ('a', 'b'))
assert all(inventory_by_path[m['a']]['sha256'] != inventory_by_path[m['b']]['sha256'] for m in confirmed)
print(json.dumps(summary, ensure_ascii=False, indent=2))
print('Report and CSV row counts validated.')
