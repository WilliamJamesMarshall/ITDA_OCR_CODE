"""Replay all saved selector states, without reading images or using labels in selection."""
import argparse
import csv
import hashlib
import importlib.util
import json
import sys
import time
from dataclasses import fields as dataclass_fields
from pathlib import Path

BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
RUN = BASE / 'retest-stage2-field-accuracy-online-20260914-v15'
FIELDS = ('year', 'month', 'day')


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--last-only', action='store_true')
    parser.add_argument('--embedded', action='store_true')
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    sys.path.insert(0, str(args.code_root / 'notebooks/project'))
    from src.date_extraction import OCRLine, select_date, submission_fields
    from src.pipeline import PipelineConfig
    from src.budget_pipeline import output_selection
    if args.embedded:
        helper = BASE/'structural-development-20260914-v15/test_embedded.py'
        spec = importlib.util.spec_from_file_location('embedded_test_helper', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _, namespace = module.load(args.code_root/'predict.ipynb')
        embedded = namespace['_ITDA_NS']
        dates = embedded['date_extraction']
        OCRLine, select_date, submission_fields = dates.OCRLine, dates.select_date, dates.submission_fields
        PipelineConfig = embedded['pipeline'].PipelineConfig
        output_selection = embedded['budget_pipeline'].output_selection
    config = PipelineConfig()
    allowed = {f.name for f in dataclass_fields(OCRLine)}
    report = dict(scope='Saved selector-state replay, not fresh OCR or 500-image runtime',
                  chronology=not args.last_only, code_root=str(args.code_root), rounds=[],
                  embedded=args.embedded, external_imports_blocked=args.embedded,
                  notebook_sha256=hashlib.sha256((args.code_root/'predict.ipynb').read_bytes()).hexdigest(),
                  sources={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (args.code_root/'notebooks/project/src').glob('*.py')})
    started = time.perf_counter()
    for n in (2, 3):
        folder = RUN / f'execution/round_{n:02}'
        actual = {r['image_id']: r for r in csv_rows(folder/'submission.csv')}
        # Labels are used only AFTER every prediction has been produced.
        predictions, previous, partials, seen, last = {}, {}, {}, {}, {}
        def process(event):
            image_id = event['image_id']
            rows = event['lines']
            signature = json.dumps(rows, sort_keys=True)
            if seen.get(image_id) == signature:
                return
            seen[image_id] = signature
            lines = [OCRLine(**{k: v for k, v in r.items() if k in allowed}) for r in rows]
            selected = select_date(lines, final=False, context=config.date_context,
                                   product_rules=config.product_date_rules)
            partials.setdefault(image_id, selected.is_partial)
            output = output_selection(selected, base_partial=partials[image_id], previous=previous.get(image_id))
            previous[image_id] = output
            predictions[image_id] = dict(image_id=image_id, **submission_fields(output.final_date))
        with (folder/'submission.csv.trace.jsonl').open(encoding='utf-8') as stream:
            for raw in stream:
                event = json.loads(raw)
                if event['kind'] != 'selector_input':
                    continue
                if args.last_only:
                    last[event['image_id']] = event
                else:
                    process(event)
        for event in last.values():
            process(event)
        assert set(predictions) == set(actual) and len(actual) == 500
        labels = {r['image_id']: submission_fields(r['정답 날짜']) for r in csv_rows(
            BASE / f'stage2_initial_20260913/approved_labels_round_{n:02}.csv')}
        # v15 embeds the exact approved field labels in every erroneous row.
        errors = json.loads((folder/'report.json').read_text(encoding='utf-8'))['errors']
        for error in errors:
            if any(labels[error['image_id']][k] != error['expected'][k] for k in FIELDS):
                raise ValueError('Label version mismatch: '+error['image_id'])
        changes = []
        for image_id, prediction in predictions.items():
            old, truth = actual[image_id], labels[image_id]
            if any(old[k] != prediction[k] for k in FIELDS):
                changes.append(dict(image_id=image_id, old=old, new=prediction, expected=truth,
                    lost=[k for k in FIELDS if old[k] == truth[k] != prediction[k]],
                    gained=[k for k in FIELDS if old[k] != truth[k] == prediction[k]]))
        result = dict(round=n, images=500, correct=sum(r[k] == labels[i][k]
            for i, r in predictions.items() for k in FIELDS), changes=changes,
            lost=sum(len(c['lost']) for c in changes), gained=sum(len(c['gained']) for c in changes),
            predictions=list(predictions.values()))
        report['rounds'].append(result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('changes','predictions')}), flush=True)
    report['seconds'] = time.perf_counter()-started
    if args.compare:
        reference = json.loads(args.compare.read_text(encoding='utf-8'))
        report['comparison'] = dict(reference=str(args.compare), images=1000,
            identical=all(a['predictions'] == b['predictions'] for a,b in zip(report['rounds'], reference['rounds'])))
        if not report['comparison']['identical']:
            raise AssertionError('Embedded/source prediction mismatch')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
