"""Create cropped evidence contact sheets for visual review, preserving originals."""
import argparse
import json
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

p = argparse.ArgumentParser()
p.add_argument('ids', nargs='+')
p.add_argument('--pattern', default=r'원산|제조국|생산국|made|product of|제조원|제조사|제조업|제조회사|공장')
p.add_argument('--output', default='evidence_review.jpg')
a = p.parse_args()
base = Path(__file__).parent
rows = {r['image_id']: r for r in map(json.loads, base.joinpath('ocr_evidence.jsonl').read_text(encoding='utf-8').splitlines())}
canvas = Image.new('RGB', (1400, 360*((len(a.ids)+1)//2)), 'white')
font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 21)
draw = ImageDraw.Draw(canvas)
for n, number in enumerate(a.ids):
    image_id = number.zfill(6)
    row = rows[image_id]
    with Image.open(Path('C:/ITDA_OCR_CODE/상품사진입니다')/row['filename']) as source:
        picture = ImageOps.exif_transpose(source).convert('RGB')
    picture.thumbnail((1600,1600))
    hits = [line for line in row['lines'] if re.search(a.pattern,line['text'],re.I)]
    if hits:
        # Show the whole label width around the evidence, not only the word.
        x1=min(l['box'][0] for l in hits); y1=min(l['box'][1] for l in hits)
        x2=max(l['box'][2] for l in hits); y2=max(l['box'][3] for l in hits)
        picture=picture.crop((max(0,x1-130),max(0,y1-60),min(picture.width,x2+180),min(picture.height,y2+95)))
    picture.thumbnail((680,320))
    x=(n%2)*700; y=(n//2)*360
    draw.text((x+10,y+4),image_id,fill='black',font=font)
    canvas.paste(picture,(x+10,y+35))
canvas.save(base/a.output,quality=94)
print(base/a.output)
