from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import json

B = Path(__file__).parent
S = B.parent.parent / '상품사진입니다'
ledger = json.loads((B.parent / 'date-order-full-audit-20260910' / 'inspection_ledger.json').read_text(encoding='utf-8'))
rows = {int(r['id']): r for r in ledger}
def picture(n):
    return ImageOps.exif_transpose(Image.open(S / rows[n]['filename'])).convert('RGB')

for n, box, angle in [
    (973,(.21,.73,.69,.92),0), (2828,(.24,.26,.70,.44),180),
    (2864,(.83,.54,1,.81),0), (3266,(.37,.17,1,.27),0),
    (628,(.29,.35,.73,.50),0), (1406,(.26,.35,.67,.66),0),
    (2941,(.85,.10,1,.42),270)]:
    im = picture(n)
    im = im.crop(tuple(int(v * (im.width if i % 2 == 0 else im.height)) for i,v in enumerate(box)))
    im = im.rotate(angle,expand=True)
    im.resize((im.width*2,im.height*2)).save(B / f'detail_{n:06d}.jpg')

variants=[945,974,1210,1290,1318,1407,1777,1811,1940,1962,2035,2037,2133,2270,2334,2367,2444,2494,2521,2650,2684,2724,2791,2829,2865,2912,2949]
for start in range(0,len(variants),6):
    canvas=Image.new('RGB',(1800,1500),'white'); d=ImageDraw.Draw(canvas)
    for i,n in enumerate(variants[start:start+6]):
        im=picture(n); im.thumbnail((596,710))
        x=(i%3)*600; y=(i//3)*750
        d.text((x+8,y+8),f'{n:06d}',fill='black',font_size=25)
        canvas.paste(im,(x+(600-im.width)//2,y+38))
    canvas.save(B / f'variants_{start//6+1}.jpg')
