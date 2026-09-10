import hashlib
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy.fft import dctn

ROOT = Path(r'C:\ITDA_OCR_CODE')
OUT = Path(__file__).parent
FOLDERS = ['상품사진입니다', '추가수집데이터']
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.gif', '.heic'}


def inspect(path):
    entry = {'path': str(path.relative_to(ROOT)), 'folder': path.relative_to(ROOT).parts[0]}
    try:
        entry['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as source:
            im = ImageOps.exif_transpose(source).convert('RGB')
            entry['width'], entry['height'] = im.size
            digest = hashlib.sha256(str(im.size).encode())
            digest.update(im.tobytes())
            entry['pixel_sha256'] = digest.hexdigest()
            gray = np.asarray(im.convert('L').resize((32, 32), Image.Resampling.LANCZOS), dtype=float)
            low = dctn(gray, type=2, norm='ortho')[:8, :8].flatten()
            entry['phash'] = int.from_bytes(np.packbits(low > np.median(low[1:])).tobytes(), 'big')
            dh = np.asarray(im.convert('L').resize((9, 8), Image.Resampling.LANCZOS))
            entry['dhash'] = int.from_bytes(np.packbits(dh[:, 1:] > dh[:, :-1]).tobytes(), 'big')
        return entry
    except Exception as exc:
        entry['error'] = str(exc)
        return entry


def groups(entries, key, cross_only=True):
    index = defaultdict(list)
    for entry in entries:
        if key in entry:
            index[entry[key]].append(entry)
    return [[e['path'] for e in group] for group in index.values()
            if len(group) > 1 and (not cross_only or len({e['folder'] for e in group}) > 1)]


def main():
    paths = sorted(p for folder in FOLDERS for p in (ROOT / folder).rglob('*')
                   if p.is_file() and p.suffix.lower() in EXTENSIONS)
    entries = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for count, entry in enumerate(pool.map(inspect, paths), 1):
            entries.append(entry)
            if count % 250 == 0:
                print(f'Inspected {count}/{len(paths)}', flush=True)
    (OUT / 'inventory.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
    original = [e for e in entries if e['folder'] == FOLDERS[0] and 'error' not in e]
    additional = [e for e in entries if e['folder'] == FOLDERS[1] and 'error' not in e]
    candidates = []
    for b in additional:
        for a in original:
            if a['pixel_sha256'] == b['pixel_sha256']:
                continue
            ph = (a['phash'] ^ b['phash']).bit_count()
            dh = (a['dhash'] ^ b['dhash']).bit_count()
            if ph <= 10 or (dh <= 8 and ph <= 18):
                candidates.append({'a': a['path'], 'b': b['path'], 'phash_distance': ph, 'dhash_distance': dh})
    candidates.sort(key=lambda c: (c['phash_distance'], c['dhash_distance']))
    result = {
        'counts': {folder: sum(e['folder'] == folder for e in entries) for folder in FOLDERS},
        'errors': [e for e in entries if 'error' in e],
        'cross_file_identical': groups(entries, 'sha256'),
        'cross_pixel_identical': groups(entries, 'pixel_sha256'),
        'within_file_identical': {f: groups([e for e in entries if e['folder'] == f], 'sha256', False) for f in FOLDERS},
        'within_pixel_identical': {f: groups([e for e in entries if e['folder'] == f], 'pixel_sha256', False) for f in FOLDERS},
        'visual_candidates': candidates,
    }
    (OUT / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('cross_file_identical', 'cross_pixel_identical', 'within_file_identical', 'within_pixel_identical', 'visual_candidates')}, ensure_ascii=False), flush=True)
    print('Cross file groups:', len(result['cross_file_identical']))
    print('Cross pixel groups:', len(result['cross_pixel_identical']))
    print('Visual candidates:', len(candidates))
    print('Within file groups:', {f: len(g) for f, g in result['within_file_identical'].items()})


if __name__ == '__main__':
    main()
