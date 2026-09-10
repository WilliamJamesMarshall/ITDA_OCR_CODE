import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

cv2.setNumThreads(1)
ROOT = Path(r'C:\ITDA_OCR_CODE')
OUT = Path(__file__).parent


@lru_cache(maxsize=1200)
def gray(path):
    with Image.open(ROOT / path) as source:
        im = ImageOps.exif_transpose(source).convert('L')
        im.thumbnail((720, 720), Image.Resampling.LANCZOS)
        return np.asarray(im).copy()


def validate(match):
    a, b = gray(match['a']), gray(match['b'])
    h = np.asarray(match['homography_b_to_a'])
    try:
        inv = np.linalg.inv(h)
    except np.linalg.LinAlgError:
        return match
    size = (b.shape[1], b.shape[0])
    warped = cv2.warpPerspective(a, inv, size)
    mask = cv2.warpPerspective(np.full(a.shape, 255, np.uint8), inv, size) > 250
    mask &= (warped > 12) & (b > 12)
    mask = cv2.erode(mask.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    overlap = float(mask.mean())
    if mask.sum() < 100:
        return match
    aa = cv2.GaussianBlur(warped, (5, 5), 0)[mask].astype(float)
    bb = cv2.GaussianBlur(b, (5, 5), 0)[mask].astype(float)
    corr = float(np.corrcoef(aa, bb)[0, 1])
    match['aligned_pixel_correlation'] = round(corr, 6) if np.isfinite(corr) else None
    match['overlap_b'] = round(overlap, 6)
    match['automatic_same_photo'] = bool(corr >= .97 and overlap >= .6 and match['inliers'] >= 20 and match['inlier_ratio'] >= .5)
    return match


def main():
    matches = json.loads((OUT / 'geometric_matches.json').read_text(encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        checked = list(pool.map(validate, matches))
    (OUT / 'validated_matches.json').write_text(json.dumps(checked, ensure_ascii=False, indent=2), encoding='utf-8')
    confirmed = [m for m in checked if m.get('automatic_same_photo')]
    print('Confirmed pairs', len(confirmed), 'Original images', len({m['a'] for m in confirmed}), 'Additional images', len({m['b'] for m in confirmed}))
    other = [m for m in checked if not m.get('automatic_same_photo')]
    print('Other geometric candidates', len(other))
    for m in other[:30]:
        print(Path(m['a']).name, Path(m['b']).name, m['inliers'], m.get('aligned_pixel_correlation'), m.get('overlap_b'))


if __name__ == '__main__':
    main()
