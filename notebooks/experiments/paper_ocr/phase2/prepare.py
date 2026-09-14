"""Create an untested implementation snapshot; never run OCR or training."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/paper-ocr-20260914/code-monitor')
DEST = Path('C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/paper-plan-implementation-20260914')


def main():
    DEST.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SOURCE, DEST/'code', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    record = dict(created_at=datetime.now(timezone.utc).isoformat(), source=str(SOURCE),
        candidate=str(DEST/'code'), instruction='첨부한 계획 전체에 대한 적용을 시작하고, 테스트는 별도의 지시가 없으면 실행하지 마.',
        tests_authorized=False, optimizer_started=False, status='implementation_in_progress_unverified',
        protected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts},
        scope='Implement full plan in a new candidate; no tests, OCR, benchmark, replay, training, promotion or approval fabrication.')
    (DEST/'implementation.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(DEST)


if __name__ == '__main__':
    main()
