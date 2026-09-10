"""Exercise the deadline-enabled CLI on an existing frozen development slice."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PRIOR = ROOT / 'artifacts/date-target-role-1500-20260910'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((PRIOR / 'live_manifest.json').read_text(encoding='utf-8'))['images']
    inputs = PRIOR / 'live_inputs'
    images = {r['current_id']: inputs / (r['current_id'] + Path(r['path']).suffix) for r in manifest}
    assert len(list(inputs.iterdir())) == len(manifest)
    for row in manifest:
        assert digest(images[row['current_id']]) == row['sha256']
    files = ('src/pipeline.py', 'src/date_extraction.py', 'scripts/evaluate_pipeline.py', 'scripts/validation_runner.py')
    hashes = {f: digest(ROOT / f) for f in files}
    (OUT / 'manifest.json').write_text(json.dumps({'images': manifest, 'code_sha256': hashes,
        'scope': 'Existing targeted development cases; runner smoke test, not independent accuracy or a 500-image test'},
        ensure_ascii=False, indent=2), encoding='utf-8')
    with (OUT / 'labels.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['image_id', '정답 날짜', '라벨 상태'])
        writer.writeheader()
        writer.writerows({'image_id': r['current_id'], '정답 날짜': r['expected'], '라벨 상태': 'manual'} for r in manifest)
    command = [sys.executable, str(ROOT / 'scripts/evaluate_pipeline.py'), str(inputs), str(OUT / 'labels.csv'),
               str(OUT / 'predictions.csv'), '--report-json', str(OUT / 'report.json')]
    subprocess.run(command, cwd=ROOT, check=True)
    assert all(digest(ROOT / f) == h for f, h in hashes.items())
    assert all(digest(images[r['current_id']]) == r['sha256'] for r in manifest)
    result = json.loads((OUT / 'report.json').read_text(encoding='utf-8'))
    assert result['runtime']['status'] == 'completed'
    assert result['runtime']['completed_images'] == len(manifest)
    assert result['targets']['local_500_joint_target_met'] is None
    assert result['targets']['actual_500_timeout_met'] is None
    (OUT / 'verified.json').write_text(json.dumps({'hashes_verified': True, 'code_sha256': hashes,
        'images': len(manifest), 'exact_matches': result['exact_matches'], 'targets': result['targets']},
        ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
