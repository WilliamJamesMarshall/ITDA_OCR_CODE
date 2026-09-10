from pathlib import Path
from PIL import Image
import hashlib
import json
import shutil

ROOT = Path(r'C:\ITDA_OCR_CODE')
DEST = ROOT / '학습대상데이터'
REPORT = ROOT / 'artifacts' / 'training_dataset_20260910'
SOURCES = [ROOT / '상품사진입니다', ROOT / '추가수집데이터']
EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}

def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

def snapshot():
    return {str(p.relative_to(ROOT)): (p.stat().st_size, p.stat().st_mtime_ns, digest(p))
            for source in SOURCES for p in source.rglob('*') if p.is_file()}

assert not DEST.exists(), 'Destination already exists; do not overwrite.'
before = snapshot()
groups = []
excluded = []
for group_index, source in enumerate(SOURCES):
    photos = sorted((p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in EXTS),
                    key=lambda p: (int(p.stem), str(p)))
    selected = []
    for p in photos:
        with Image.open(p) as im:
            size = im.size
        if group_index == 0 and size == (640, 640):
            excluded.append(str(p.relative_to(ROOT)))
        else:
            selected.append(p)
    groups.append(selected)

assert len(excluded) == 1106
assert [len(group) for group in groups] == [2246, 364]
DEST.mkdir()
mapping = []
for prefix, start, photos in [('AMLC', 1, groups[0]), ('BMLC', 2247, groups[1])]:
    for number, source in enumerate(photos, start):
        new_name = f'{prefix}{number:06d}{source.suffix}'
        target = DEST / new_name
        shutil.copy2(source, target)
        source_key = str(source.relative_to(ROOT))
        expected_hash = before[source_key][2]
        assert digest(target) == expected_hash, new_name
        mapping.append({'filename': new_name, 'source': source_key, 'sha256': expected_hash})

assert {p.name for p in DEST.iterdir()} == {row['filename'] for row in mapping}
assert snapshot() == before, 'Source files changed during operation.'
REPORT.mkdir(parents=True, exist_ok=True)
result = {
    'destination': str(DEST), 'total_images': len(mapping),
    'AMLC': {'count': 2246, 'first': 'AMLC000001', 'last': 'AMLC002246'},
    'BMLC': {'count': 364, 'first': 'BMLC002247', 'last': 'BMLC002610'},
    'excluded_640x640': len(excluded), 'source_files_unchanged': True,
    'all_copy_sha256_verified': True,
    'numbering_order': 'Original numeric filename ascending within each source',
    'requested_BMLC_end': 'BMLC002633',
    'count_note': 'Current additional source has 364 images; all included. Requested range has 387 positions.'
}
for name, data in [('verification.json', result), ('source_mapping.json', mapping), ('excluded_640x640.json', excluded)]:
    (REPORT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=True, indent=2))
