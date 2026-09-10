import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(r'C:\ITDA_OCR_CODE')
OUT = Path(__file__).parent
result = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))
pairs = result['visual_candidates']
sheet = Image.new('RGB', (1000, 380 * len(pairs)), 'white')
draw = ImageDraw.Draw(sheet)
for i, pair in enumerate(pairs):
    for j, key in enumerate(('a', 'b')):
        with Image.open(ROOT / pair[key]) as source:
            im = ImageOps.exif_transpose(source).convert('RGB')
            im.thumbnail((488, 330))
            sheet.paste(im, (j * 500 + (500 - im.width) // 2, i * 380 + 35))
        label = f"{i+1} {'Original' if j == 0 else 'Additional'}: {Path(pair[key]).name}"
        draw.text((j * 500 + 10, i * 380 + 8), label, fill='black')
sheet.save(OUT / 'candidate_pairs.jpg', quality=92)
print(str(OUT / 'candidate_pairs.jpg'))
