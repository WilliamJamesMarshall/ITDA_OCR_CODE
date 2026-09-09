"""Generate analytical contact sheets; never modify source photographs."""
import argparse,json,re
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw,ImageFont

BASE=Path(__file__).parent;ROOT=BASE.parent.parent
raw={r['image_id']:r for r in map(json.loads,(ROOT/'artifacts/country-date-report-20260909/ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines())}
candidates=json.loads((BASE/'candidates.json').read_text(encoding='utf-8'))
p=argparse.ArgumentParser();p.add_argument('--extra',action='store_true');p.add_argument('--ids',nargs='*');a=p.parse_args()
ids=[r['image_id'] for r in candidates]
hits={r['image_id']:r['hits'] for r in candidates}
if a.extra:
 previous=[json.loads(s) for s in (ROOT/'labels/validation_000001_003352_manual.xlsx.inspect.ndjson').read_text(encoding='utf-8').splitlines()]
 marked=[str(r['values'][0]).zfill(6) for r in previous if r.get('kind')=='row' and re.search('두 자리|두자리', ' '.join(str(x) for x in r['values']))]
 ids=sorted(set(marked)-set(ids))
 (BASE/'extra_queue.json').write_text(json.dumps(ids),encoding='utf-8')
if a.ids:ids=[s.zfill(6) for s in a.ids]
folder=BASE/('extra_sheets' if a.extra else 'review_sheets');folder.mkdir(exist_ok=True)
font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',22)
for page in range(0,len(ids),8):
 canvas=Image.new('RGB',(1800,1520),'#eeeeee');d=ImageDraw.Draw(canvas)
 for j,image_id in enumerate(ids[page:page+8]):
  r=raw[image_id];im=ImageOps.exif_transpose(Image.open(ROOT/'상품사진입니다'/r['filename'])).convert('RGB');im.thumbnail((1600,1600))
  x=(j%2)*900;y=(j//2)*380
  d.text((x+5,y+3),image_id,fill='black',font=font)
  thumb=im.copy();thumb.thumbnail((260,335));canvas.paste(thumb,(x+5,y+35))
  boxes=[h['box'] for h in hits.get(image_id,[])]
  if not boxes:
   boxes=[l['box'] for l in r['lines'] if re.search(r'\d[ ./\-년월일]*\d',l['text']) and not re.search('영양|나트륨|지방|탄수|단백|칼로|전화|상담|품목|신고|kcal|mg|%',l['text'],re.I)]
  if boxes:
   box=(max(0,min(b[0] for b in boxes)-40),max(0,min(b[1] for b in boxes)-60),min(im.width,max(b[2] for b in boxes)+50),min(im.height,max(b[3] for b in boxes)+70))
   crop=im.crop(box)
  else:crop=im.copy()
  crop.thumbnail((620,335));canvas.paste(crop,(x+275,y+35))
 canvas.save(folder/f'page_{page//8+1:03d}.jpg',quality=92)
 print(folder/f'page_{page//8+1:03d}.jpg')
print('REVIEW IMAGES',len(ids))
