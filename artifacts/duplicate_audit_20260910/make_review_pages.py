import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(r'C:\ITDA_OCR_CODE')
OUT = Path(__file__).parent
matches = json.loads((OUT / 'validated_matches.json').read_text(encoding='utf-8'))
pairs = sorted([m for m in matches if (m.get('aligned_pixel_correlation') or 0) >= .8],
               key=lambda m: -m['aligned_pixel_correlation'])
extra = [m for m in matches if m['inliers'] >= 100 and (m.get('aligned_pixel_correlation') or 0) < .8]
pairs += extra
(OUT / 'review_order.json').write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding='utf-8')
for start in range(0, len(pairs), 6):
    chunk = pairs[start:start + 6]
    sheet = Image.new('RGB', (1000, 370 * len(chunk)), 'white')
    draw = ImageDraw.Draw(sheet)
    for row, pair in enumerate(chunk):
        for col, key in enumerate(('a', 'b')):
            with Image.open(ROOT / pair[key]) as source:
                im = ImageOps.exif_transpose(source).convert('RGB')
                im.thumbnail((490, 330))
                sheet.paste(im, (500 * col + (500 - im.width) // 2, row * 370 + 35))
            label = f"{start+row+1}. {'A' if col == 0 else 'B'} {Path(pair[key]).name}"
            if col == 1:
                label += f"  corr={pair.get('aligned_pixel_correlation')}"
            draw.text((col * 500 + 10, row * 370 + 8), label, fill='black')
    sheet.save(OUT / f'review_{start//6+1:02d}.jpg', quality=92)
print('Review pairs', len(pairs))
