"""Compare incoming selector with current selector and trace saved development OCR."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import date_extraction as current
from src.ocr_trace import ImageTrace


def main():
    spec = importlib.util.spec_from_file_location('incoming_trace_policy', OUT/'starting_source/date_extraction.py')
    before = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = before
    spec.loader.exec_module(before)
    manifest = json.loads((ROOT/'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))
    counts = Counter()
    details = []
    trace_seconds = 0.
    for row in manifest['included']:
        old_lines, lines = [], []
        trace = ImageTrace(row['current_id'])
        first_old = first_new = None
        for index, event in enumerate(row['evidence']['events'], 1):
            old_lines.extend(before.OCRLine(**raw) for raw in event['lines'])
            batch = [current.OCRLine(**raw) for raw in event['lines']]
            lines.extend(batch)
            old = before.select_date(old_lines)
            new = current.select_date(lines)
            state_old = (old.final_date, old.reason, old.stop_ocr)
            state_new = (new.final_date, new.reason, new.stop_ocr)
            assert state_old == state_new, (row['current_id'], index)
            if first_old is None and old.stop_ocr:
                first_old = (old.final_date, index)
            if first_new is None and new.stop_ocr:
                first_new = (new.final_date, index)
            started = time.perf_counter()
            # Historical cache has no crop/rotation transforms. Never invent them.
            trace.record_pass(batch, [], None, event['detector'], event['variant'], 0., new)
            trace_seconds += time.perf_counter()-started
        old = before.select_date(old_lines, final=True)
        new = current.select_date(lines, final=True)
        assert (old.final_date, old.reason, first_old) == (new.final_date, new.reason, first_new), row['current_id']
        counts['cases'] += 1
        counts['full_cache_correct'] += int((new.final_date or 'NONE') == row['expected'] and not row['evidence']['error'])
        counts['unchanged'] += 1
        summary = trace.summary()
        counts.update({key: value for key, value in summary.items() if key != 'ocr_seconds'})
        unresolved = [o for o in trace.observations if o['date_like'] and o['parse_status'] == 'unparsed']
        details.append(dict(image_id=row['current_id'], expected=row['expected'], final_cache=new.final_date,
                            first_stop=first_new, summary=summary,
                            unresolved=[dict(text=o['text'], source=o['source'], variant=o['variant'],
                                             local_box=o['local_box'], role_hints=o['role_hints']) for o in unresolved]))
    result = dict(scope='Saved 705-case development OCR replay, not fresh OCR or an independent test. '
                        'Historical transforms and filtered detections are unavailable. Unparsed/date-like is a diagnostic hint, not a root-cause label.',
                  counts=dict(counts), trace_build_seconds=trace_seconds,
                  trace_build_seconds_per_image=trace_seconds/counts['cases'], details=details)
    (OUT/'verified.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'details'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
