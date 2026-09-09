"""Print auditable OCR candidates. Never changes source photographs."""
import argparse
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--start', type=int, default=1)
p.add_argument('--end', type=int, default=3352)
p.add_argument('--mode', choices=['country', 'maker', 'date', 'all'], default='country')
a = p.parse_args()
patterns = {
    'country': r'원산|제조국|생산국|made\s*in|product\s*of|대한민국|국내산|한국산|이탈리|폴란드|중국|일본|미국|캐나다|호주|오스트|말레이|태국|베트남|대만|스페인|독일|프랑스|벨기에|네덜란드|덴마크|뉴질랜드|튀르키|터키|인도네|필리핀|스위스|영국|italy|poland|china|japan|australia|malaysia|thailand|germany|france|canada|zealand|vietnam|turkey|belgium|taiwan|indonesia|spain|netherlands',
    'maker': r'제조원|제조업|제조사|제조회사|제조및|제조및판매|제조/|제조·|제조판매|공장|manufactur|produced|product of|made in',
    'date': r'(일[ /,.\-·]*(월)[ /,.\-·]*(년|연))|((년|연)[ /,.\-·]*월[ /,.\-·]*일)|월[ /,.\-·]*일[ /,.\-·]*(년|연)|dd[/ .-]*mm|yy[/ .-]*mm|mm[/ .-]*dd',
    'all': r'.',
}
rows = [json.loads(x) for x in Path(__file__).with_name('ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines()]
print('CACHED', len(rows))
for row in sorted(rows, key=lambda x: x['image_id']):
    if not a.start <= int(row['image_id']) <= a.end:
        continue
    lines = [x['text'] for x in row['lines']]
    indexes = {j for i,t in enumerate(lines) if re.search(patterns[a.mode], t, re.I)
               for j in range(max(0,i-1), min(len(lines),i+4))}
    if indexes:
        print(row['image_id'], '::', ' | '.join(lines[j] for j in sorted(indexes)))
