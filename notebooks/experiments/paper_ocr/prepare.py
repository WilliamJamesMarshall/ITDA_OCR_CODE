"""Create a new, isolated candidate from the evaluated v15 sources."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
SOURCE = BASE / 'structural-development-20260914-v15/round_02/code'
DEST = BASE / 'paper-ocr-20260914'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    DEST.mkdir(exist_ok=False)
    before = {str(p): sha(p) for p in SOURCE.rglob('*') if p.is_file()
              and '__pycache__' not in p.parts}
    shutil.copytree(SOURCE, DEST / 'code', ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    record = dict(created_at=datetime.now(timezone.utc).isoformat(),
                  instruction='시작해.',
                  context='Apply the preceding paper-based OCR plan: field accuracy >=95%, complete 500-image notebook <=1600s.',
                  source_reference='Current user message in this task; 2026-09-14',
                  scope='Development, validation and applicable approved-data training; no future-round data or automatic group promotion.',
                  baseline=str(SOURCE), protected=before,
                  candidate=str(DEST / 'code'), accuracy_policy='date-fields-v1',
                  notebook_limit_seconds=1600, network_mode='online-local-models')
    (DEST / 'authorization.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(DEST)


if __name__ == '__main__':
    main()
