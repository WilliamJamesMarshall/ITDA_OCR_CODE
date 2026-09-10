import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from geometry_audit import verify
from validate_matches import validate

ROOT = Path(r'C:\ITDA_OCR_CODE')
OUT = Path(__file__).parent
cv2.setNumThreads(1)


@lru_cache(maxsize=1200)
def features(path):
    with Image.open(ROOT / path) as source:
        im = ImageOps.exif_transpose(source).convert('L')
        im.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
        gray = np.asarray(im)
    points, desc = cv2.SIFT_create(nfeatures=2000).detectAndCompute(gray, None)
    # Coordinates are scaled to the 720px images used for aligned pixel checks.
    with Image.open(ROOT / path) as source:
        small = ImageOps.exif_transpose(source).convert('L')
        small.thumbnail((720, 720), Image.Resampling.LANCZOS)
    coords = np.float32([k.pt for k in points])
    coords *= np.float32([small.width / im.width, small.height / im.height])
    return {'path': path, 'size': small.size, 'points': coords, 'desc': desc}


def work(pair):
    result = verify(features(pair[0]), features(pair[1]))
    return validate(result) if result else None


def main():
    matches = json.loads((OUT / 'validated_matches.json').read_text(encoding='utf-8'))
    inventory = json.loads((OUT / 'inventory.json').read_text(encoding='utf-8'))
    originals = {int(Path(e['path']).stem): e['path'] for e in inventory if e['folder'] == '상품사진입니다'}
    # Refine plausible spatial matches and adjacent augmentation variants.
    pairs = {(m['a'], m['b']) for m in matches if m['inliers'] >= 15 and m['inlier_ratio'] >= .35 and m['coverage_b'] >= .1}
    for m in matches:
        if (m.get('aligned_pixel_correlation') or 0) >= .85:
            number = int(Path(m['a']).stem)
            for neighbor in range(number - 3, number + 4):
                if neighbor in originals:
                    pairs.add((originals[neighbor], m['b']))
    print('Refining pairs', len(pairs), flush=True)
    checked = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, result in enumerate(pool.map(work, sorted(pairs)), 1):
            if result:
                checked.append(result)
            if i % 50 == 0:
                print('Refined', i, flush=True)
    (OUT / 'refined_matches.json').write_text(json.dumps(checked, ensure_ascii=False, indent=2), encoding='utf-8')
    promising = sorted([m for m in checked if (m.get('aligned_pixel_correlation') or 0) >= .85 and m.get('overlap_b', 0) >= .5], key=lambda m: m['b'])
    print('Promising pairs', len(promising), 'additional images', len({m['b'] for m in promising}), flush=True)
    for m in promising:
        print(Path(m['a']).name, Path(m['b']).name, m['inliers'], m['aligned_pixel_correlation'], flush=True)


if __name__ == '__main__':
    main()
