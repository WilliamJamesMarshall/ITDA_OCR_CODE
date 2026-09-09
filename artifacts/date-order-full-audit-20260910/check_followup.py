import json
from pathlib import Path
from PIL import Image,ImageOps
B=Path(__file__).parent;R=B.parent.parent
old={int(r['image_id']):r for r in json.loads((R/'artifacts/date-order-audit-20260909/reviewed.json').read_text(encoding='utf-8'))}
z=json.loads((B/'zoom_review_03.json').read_text(encoding='utf-8'))
for f in sorted(B.glob('batch_*.json')):
 b=json.loads(f.read_text(encoding='utf-8'))
 for i in b.get('ambiguous','').split():
  n=int(i)
  if n not in old and str(n) not in z:print(i,b.get('raw',{}).get(i),b.get('notes',{}).get(i))
for n in [2705]:
 p=next((R/'상품사진입니다').glob(f'{n:06d}.*'))
 im=ImageOps.exif_transpose(Image.open(p));im=im.rotate(180,expand=True);im.save(B/f'zoom_{n}.jpg')
