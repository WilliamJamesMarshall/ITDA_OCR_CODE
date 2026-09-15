"""Replay stored selector snapshots without loading images or OCR models.

Each snapshot is independent. This is not an end-to-end run or a scored round:
recovery scheduling and prior-output retention are intentionally not replayed.
"""
import argparse
import hashlib
import json
import sys
from dataclasses import fields
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--image-id', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve previous replay evidence')
    sys.path.insert(0, str(args.code_root / 'notebooks/project'))
    from src.date_extraction import OCRLine, DateContext, select_date
    from src.budget_pipeline import output_selection
    from scripts.operating_environment import limit_cpu
    limit_cpu([4, 5, 6, 7])
    allowed = {f.name for f in fields(OCRLine)}
    wanted = set(args.image_id)
    snapshots = []
    digest = hashlib.sha256()
    with args.trace.open('rb') as stream:
        for number, raw in enumerate(stream, 1):
            digest.update(raw)
            row = json.loads(raw)
            if row.get('kind') != 'selector_input' or row.get('image_id') not in wanted:
                continue
            lines = []
            for value in row['lines']:
                value = {k: v for k, v in value.items() if k in allowed}
                for key in ('box', 'members', 'original_box', 'character_scores'):
                    if value.get(key) is not None:
                        value[key] = tuple(value[key])
                value['polygon'] = tuple(tuple(p) for p in value.get('polygon', ()))
                lines.append(OCRLine(**value))
            selection = select_date(lines, context=DateContext(), final=row.get('final', False))
            output = output_selection(selection)
            snapshots.append(dict(trace_line=number, image_id=row['image_id'], stage=row['stage'],
                final=row.get('final', False), output=output.final_date, reason=selection.reason,
                observed_lines=row['lines'], roles=[dict(text=line.text, role=line.role) for line in lines if line.role]))
    assert {r['image_id'] for r in snapshots} == wanted, 'Missing requested selector input'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(dict(scope=__doc__, trace_path=str(args.trace), trace_sha256=digest.hexdigest(),
                       code_root=str(args.code_root), source_sha256=hashlib.sha256((args.code_root / 'notebooks/project/src/date_extraction.py').read_bytes()).hexdigest(),
                       snapshots=snapshots), stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(snapshots=len(snapshots), images=len(wanted), output=str(args.output)), ensure_ascii=False))


if __name__ == '__main__':
    main()
