"""Compare only this turn's change against the preserved incoming worktree."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import date_extraction as current


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_before():
    spec = importlib.util.spec_from_file_location('role_starting_policy', OUT / 'starting_source/date_extraction.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest():
    return json.loads((ROOT / 'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))['included']


def main():
    before = load_before()
    details = []
    for row in manifest():
        assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['sha256']
        result = {k: row[k] for k in ('historical_id', 'current_id', 'path', 'sha256', 'expected')}
        for key, module in (('before', before), ('after', current)):
            all_lines = []
            first_stop = None
            for i, event in enumerate(row['evidence']['events'], 1):
                all_lines.extend(module.OCRLine(**v) for v in event['lines'])
                selected = module.select_date(all_lines)
                if selected.stop_ocr and first_stop is None:
                    first_stop = dict(prediction=selected.final_date or 'NONE', passes=i, reason=selected.reason)
            selected = module.select_date(all_lines, final=True)
            result[key] = dict(full=selected.final_date or 'NONE', trace=first_stop or dict(
                prediction=selected.final_date or 'NONE', passes=len(row['evidence']['events']), reason=selected.reason))
        details.append(result)
    summary = {key: dict(full_correct=sum(r[key]['full'] == r['expected'] for r in details),
                         trace_correct=sum(r[key]['trace']['prediction'] == r['expected'] for r in details))
               for key in ('before', 'after')}
    changed = [r for r in details if r['before'] != r['after']]
    save('comparison.json', dict(scope='705 development records. Saved OCR replay is not fresh pipeline execution or a speed measurement.',
                                 summary=summary, changed=changed, details=details))
    print(summary, flush=True)
    for r in changed:
        print({k: v for k, v in r.items() if k not in ('path', 'sha256')}, flush=True)


if __name__ == '__main__':
    main()
