"""Development cache comparison; no images or OCR, no label mutation."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import date_extraction as current


def main():
    spec = importlib.util.spec_from_file_location('structural_before', OUT/'starting_source/date_extraction.py')
    before = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = before
    spec.loader.exec_module(before)
    manifest = json.loads((ROOT/'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))
    details = []
    for row in manifest['included']:
        result = dict(image_id=row['current_id'], expected=row['expected'])
        for key, module in [('before', before), ('after', current)]:
            lines = [module.OCRLine(**line) for event in row['evidence']['events'] for line in event['lines']]
            selected = module.select_date(lines, final=True)
            result[key] = selected.final_date or 'NONE'
            result[key+'_reason'] = selected.reason
        result['gained'] = result['before'] != result['expected'] == result['after']
        result['lost'] = result['before'] == result['expected'] != result['after']
        details.append(result)
    result = dict(scope='705 saved development OCR records; not live execution or independent accuracy.',
                  counts=dict(total=len(details), before=sum(r['before']==r['expected'] for r in details),
                              after=sum(r['after']==r['expected'] for r in details), gained=sum(r['gained'] for r in details),
                              lost=sum(r['lost'] for r in details)),
                  changes=[r for r in details if r['before'] != r['after']], details=details)
    (OUT/'replay.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='details'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
