import json
import pickle
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

cv2.setNumThreads(1)
cv2.setRNGSeed(42)
ROOT = Path(r'C:\ITDA_OCR_CODE')
OUT = Path(__file__).parent


def features(entry):
    with Image.open(ROOT / entry['path']) as source:
        im = ImageOps.exif_transpose(source).convert('L')
        im.thumbnail((720, 720), Image.Resampling.LANCZOS)
        gray = np.asarray(im)
    kp, desc = cv2.SIFT_create(nfeatures=500).detectAndCompute(gray, None)
    return {'path': entry['path'], 'size': im.size,
            'points': np.float32([k.pt for k in kp]), 'desc': desc}


def verify(a, b):
    matches = cv2.BFMatcher().knnMatch(b['desc'], a['desc'], k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return None
    bp = np.float32([b['points'][m.queryIdx] for m in good])
    ap = np.float32([a['points'][m.trainIdx] for m in good])
    h, mask = cv2.findHomography(bp, ap, cv2.RANSAC, 4.0)
    if h is None:
        return None
    valid = mask.ravel().astype(bool)
    count = int(valid.sum())
    if count < 8:
        return None
    coverage = float(cv2.contourArea(cv2.convexHull(bp[valid])) / (b['size'][0] * b['size'][1]))
    return {'a': a['path'], 'b': b['path'], 'good_matches': len(good),
            'inliers': count, 'inlier_ratio': count / len(good),
            'coverage_b': coverage, 'homography_b_to_a': h.tolist()}


def main():
    inventory = json.loads((OUT / 'inventory.json').read_text(encoding='utf-8'))
    cache = OUT / 'sift_features.pkl'
    if cache.exists():
        data = pickle.loads(cache.read_bytes())
    else:
        data = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            for i, item in enumerate(pool.map(features, inventory), 1):
                data.append(item)
                if i % 250 == 0:
                    print(f'Features {i}/{len(inventory)}', flush=True)
        cache.write_bytes(pickle.dumps(data))
    a = [d for d in data if d['path'].startswith('상품사진입니다')]
    b = [d for d in data if d['path'].startswith('추가수집데이터')]
    descriptors = np.concatenate([d['desc'] for d in a])
    owners = np.concatenate([np.full(len(d['desc']), i, dtype=np.int32) for i, d in enumerate(a)])
    print(f'Building index: {len(descriptors)} features', flush=True)
    index = cv2.flann_Index(descriptors, dict(algorithm=1, trees=4))
    matches = []
    retrieval = []
    for bi, target in enumerate(b, 1):
        neighbors, distances = index.knnSearch(target['desc'], 4, params={'checks': 128})
        votes = Counter()
        for ids in owners[neighbors]:
            for owner in set(ids):
                votes[int(owner)] += 1
        top = votes.most_common(15)
        retrieval.append({'b': target['path'], 'candidates': [{'a': a[ai]['path'], 'votes': n} for ai, n in top]})
        for ai, n in top:
            verified = verify(a[ai], target)
            if verified:
                verified['retrieval_votes'] = n
                matches.append(verified)
        if bi % 25 == 0:
            print(f'Compared {bi}/{len(b)}; geometric candidates {len(matches)}', flush=True)
    matches.sort(key=lambda m: (-m['inliers'], -m['coverage_b']))
    (OUT / 'geometric_matches.json').write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'retrieval.json').write_text(json.dumps(retrieval, ensure_ascii=False, indent=2), encoding='utf-8')
    strong = [m for m in matches if m['inliers'] >= 15 and m['inlier_ratio'] >= .35 and m['coverage_b'] >= .1]
    print(f'Geometric candidates {len(matches)}; strong pairs {len(strong)}; additional images {len({m["b"] for m in strong})}', flush=True)


if __name__ == '__main__':
    main()
