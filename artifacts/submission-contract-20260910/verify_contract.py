"""Rescore frozen development outputs; never reads images or runs OCR."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_pipeline import score_predictions
from src.date_extraction import submission_fields


def main():
    source = ROOT / 'artifacts/date-recognition-repair-20260910'
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    comparison = json.loads((source / 'comparison.json').read_text(encoding='utf-8'))
    metadata = {item['current_id']: item for item in manifest['included']}
    labels, legacy, canonical, failures = {}, [], [], []
    previous_exact = 0
    for item in comparison['details']:
        key = item['current_id']
        assert key not in labels, key
        assert item['expected'] == metadata[key]['expected'], key
        labels[key] = {'정답 날짜': item['expected'], '라벨 상태': 'manual'}
        old_value = item['after']
        fields = submission_fields(old_value)
        canonical.append({'image_id': key, **fields})
        legacy.append({'image_id': key, **fields, 'final_date': old_value})
        failure = metadata[key]['evidence']['error']
        if failure:
            failures.append({'image_id': key, 'error': failure})
        previous_exact += int(old_value == item['expected'] and not failure)
    old_report = score_predictions(labels, legacy, failures)
    new_report = score_predictions(labels, canonical, failures)
    assert old_report['exact_matches'] == new_report['exact_matches'] == previous_exact
    assert old_report['field_metrics'] == new_report['field_metrics']
    assert new_report['submission_format']['all_rows_compliant']
    result = {
        'scope': 'Frozen 705-case development outputs; serialization/evaluator check only. '
                 'No images, OCR, independent holdout or OCR timing measured.',
        'previous_literal_exact_matches': previous_exact,
        'legacy_format': old_report['submission_format'],
        'canonical_report': new_report,
    }
    output = Path(__file__).with_name('verified.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'cases': new_report['evaluated_labels'], 'exact_before': previous_exact,
        'exact_after': new_report['exact_matches'],
        'field_metrics_unchanged': old_report['field_metrics'] == new_report['field_metrics'],
        'legacy_format': old_report['submission_format'],
        'canonical_format': new_report['submission_format'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
