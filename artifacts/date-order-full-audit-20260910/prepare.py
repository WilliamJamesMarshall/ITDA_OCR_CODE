"""Inventory every source image and create date-focused sheets for exhaustive visual review."""
import json,re,hashlib
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw,ImageFont
BASE=Path(__file__).parent;ROOT=BASE.parent.parent
SOURCE=ROOT/'상품사진입니다'
OCR={r['image_id']:r for r in map(json.loads,(ROOT/'artifacts/country-date-report-20260909/ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines())}
PAT=re.compile(r'(?<!\d)(?:\d{1,4}[. /\-년월일]+\d{1,2}[. /\-년월일]+\d{1,4}|\d{1,2}[ /\-]?(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[ /\-]?\d{2,4}|\d{6,8})(?!\d)',re.I)
BAD=re.compile('품목|보고|전화|상담|사업자|등록|나트륨|탄수|단백|지방|칼로|kcal|mg|%',re.I)
manifest=[];folder=BASE/'sheets';folder.mkdir(exist_ok=True)
font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',21)
for p in sorted(SOURCE.iterdir()):
 if p.suffix.lower() not in ['.jpg','.jpeg','.png']:continue
 im=Image.open(p)
 manifest.append({'id':p.stem,'filename':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':list(im.size),'page':(int(p.stem)-1)//8+1})
 im.close()
assert [r['id'] for r in manifest]==[f'{i:06d}' for i in range(1,3353)]
(BASE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
for offset in range(0,len(manifest),8):
 canvas=Image.new('RGB',(1800,1520),'#eee');draw=ImageDraw.Draw(canvas)
 for j,r in enumerate(manifest[offset:offset+8]):
  x=j%2*900;y=j//2*380;draw.text((x+5,y+3),r['id'],font=font,fill='black')
  im=ImageOps.exif_transpose(Image.open(SOURCE/r['filename'])).convert('RGB');im.thumbnail((1600,1600))
  thumb=im.copy();thumb.thumbnail((235,335));canvas.paste(thumb,(x+5,y+35))
  lines=[l for l in OCR[r['id']]['lines'] if PAT.search(l['text']) and not BAD.search(l['text'])]
  if not lines:lines=[l for l in OCR[r['id']]['lines'] if re.search(r'\d[. /\-]\d',l['text']) and not BAD.search(l['text'])]
  lines.sort(key=lambda l:(bool(re.search('EXP|BEFORE|기한|까지|20\d{2}[. /-]',l['text'],re.I)),l['score']),reverse=True)
  if lines:
   for k,l in enumerate(lines[:3]):
    b=l['box'];crop=im.crop((max(0,b[0]-25),max(0,b[1]-20),min(im.width,b[2]+35),min(im.height,b[3]+25)))
    crop.thumbnail((635,100));canvas.paste(crop,(x+255,y+35+k*112))
  else:
   thumb=im.copy();thumb.thumbnail((635,335));canvas.paste(thumb,(x+255,y+35))
 canvas.save(folder/f'{offset//8+1:03d}.jpg',quality=93)
 if offset%160==0:print(offset+8,flush=True)
print('COMPLETE',len(manifest),flush=True)
