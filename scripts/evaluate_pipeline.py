import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import PipelineConfig, discover_images
from src.date_extraction import submission_fields
from scripts.validation_runner import HARD_TIMEOUT_SECONDS, run_timed_pipeline

REFERENCE_IMAGES = 500
TIMEOUT_SECONDS_500 = HARD_TIMEOUT_SECONDS
DEFAULT_TARGET_SECONDS_500 = 1500.0
MISSING_DATE = 'NONE'
DATE_FIELDS = ('year', 'month', 'day')


def assess_targets(runtime, accuracy, *, target_seconds_500=DEFAULT_TARGET_SECONDS_500,
                   confirmed_labels_only=True):
    """Comparable local rates, never a claim about an unmeasured 500-image run."""
    images = runtime['images']
    elapsed = runtime['total_elapsed_seconds']
    if not isinstance(images, int) or isinstance(images, bool) or images <= 0:
        raise ValueError('images must be a positive integer')
    if not math.isfinite(elapsed) or elapsed <= 0:
        raise ValueError('total_elapsed_seconds must be finite and positive')
    if not math.isfinite(target_seconds_500) or not 0 < target_seconds_500 < TIMEOUT_SECONDS_500:
        raise ValueError('target_seconds_500 must be between 0 and 2400 (exclusive)')
    completed = runtime.get('completed_images', images)
    if not isinstance(completed, int) or isinstance(completed, bool) or not 0 <= completed <= images:
        raise ValueError('completed_images must be an integer between 0 and images')
    status = runtime.get('status', 'completed')
    run_complete = status == 'completed' and completed == images
    per_image = elapsed / completed if completed else None
    target_per_image = target_seconds_500 / REFERENCE_IMAGES
    backend_per_image = runtime.get('ocr_backend_seconds_per_completed_image', runtime.get('ocr_backend_seconds_per_image'))
    complete_labels = confirmed_labels_only and accuracy['evaluated_labels'] == images
    output_complete = not accuracy['labels_without_predictions'] and not accuracy['skipped'].get('unlabelled_predictions', 0)
    no_failures = not runtime['failures']
    format_met = accuracy.get('submission_format', {}).get('all_rows_compliant')
    speed_met = bool(run_complete and elapsed <= TIMEOUT_SECONDS_500
                     and per_image is not None and per_image <= target_per_image)
    joint_met = bool(complete_labels and output_complete and no_failures and format_met
                     and accuracy['accuracy_target_met'] and speed_met)
    return {
        'reference_images': REFERENCE_IMAGES,
        'accuracy_target': 0.95,
        'accuracy_metric': 'exact_match_rate',
        'submission_format_met': format_met,
        'internal_seconds_500': target_seconds_500,
        'timeout_seconds_500': TIMEOUT_SECONDS_500,
        'target_seconds_per_image': target_per_image,
        'ocr_backend_seconds_per_completed_image': backend_per_image,
        'ocr_backend_seconds_per_image_over_target': backend_per_image - target_per_image if backend_per_image is not None else None,
        'ocr_backend_timing_scope': 'Completed images only; recognize calls including lazy recovery initialization. '
                                    'Excludes image load, crop/preprocessing, date selection, trace/CSV writes and unfinished calls. '
                                    'Diagnostic only; joint acceptance still uses total elapsed time.',
        'timeout_reference_seconds_per_image': TIMEOUT_SECONDS_500 / REFERENCE_IMAGES,
        'run_status': status,
        'run_complete': run_complete,
        'completed_images': completed,
        'unprocessed_images': images - completed,
        'total_seconds_per_input_image': per_image if run_complete else None,
        'actual_seconds_per_completed_image': per_image,
        'seconds_per_image_over_target': per_image - target_per_image if per_image is not None else None,
        'actual_to_target_time_ratio': per_image / target_per_image if per_image is not None else None,
        'input_images_per_second': completed / elapsed,
        'relative_time_budget_seconds': images * target_per_image,
        'seconds_500_equivalent': per_image * REFERENCE_IMAGES if run_complete else None,
        'relative_speed_target_met': speed_met,
        'all_inputs_have_confirmed_labels': complete_labels,
        'output_complete': output_complete,
        'runtime_errors_zero': no_failures,
        'local_relative_joint_target_met': joint_met,
        'local_500_joint_target_met': joint_met if images == REFERENCE_IMAGES else None,
        'actual_500_timeout_met': bool(run_complete and elapsed <= TIMEOUT_SECONDS_500) if images == REFERENCE_IMAGES else None,
        'time_assessment': ('timeout' if status == 'timeout' or elapsed > TIMEOUT_SECONDS_500 else
                            'incomplete' if not run_complete else
                            'internal_target_met' if speed_met else 'internal_target_missed_within_hard_limit'),
        'scope': 'Local measured run; see runtime.timing_scope for included costs. '
                 '500-equivalent is normalization, not a measured 500-image result; '
                 'independent accuracy and official-environment acceptance are not established here.',
    }


def read_labels(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    labels = {}
    for row in rows:
        key = row["image_id"].strip()
        key = key.zfill(6) if key.isdigit() else key
        if not key or key in labels:
            raise ValueError(f"Empty or duplicate label image_id: {key!r}")
        labels[key] = row
    return labels


def read_predictions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _evaluation_fields(value):
    """Only legacy all-missing spelling is normalized; malformed dates earn no credit."""
    if not isinstance(value, str) or not re.fullmatch(
        r'(?:NONE|NONE-NONE-NONE|[0-9]{4}-[0-9]{2}-[0-9]{2}|NONE-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9]{2}-NONE)', value
    ):
        raise ValueError(f'Invalid evaluation date: {value!r}')
    return submission_fields(value)


def _date_kind(value):
    return 'none' if value == MISSING_DATE else 'partial' if 'NONE' in value else 'full'


def score_predictions(labels, predictions, failures, *, all_label_statuses=False, expected_ids=None):
    if expected_ids is not None:
        scope = {key.zfill(6) if key.isdigit() else key for key in expected_ids}
        labels = {key: row for key, row in labels.items() if key in scope}
    failed = {item['image_id'].zfill(6) if item['image_id'].isdigit() else item['image_id']
              for item in failures}
    seen = set()
    errors = []
    counts = Counter()
    categories = {kind: {'total': 0, 'correct': 0} for kind in ('full', 'partial', 'none')}
    skipped = Counter()
    fields = {name: dict(total=0, matches=0, known_total=0, known_matches=0,
                         known_wrong=0, known_missing=0, known_unavailable=0,
                         absent_total=0, absent_matches=0, absent_spurious=0, absent_unavailable=0)
              for name in DATE_FIELDS}
    output_kinds = {kind: 0 for kind in ('full', 'partial', 'none', 'invalid')}
    format_counts = dict(rows=0, final_date_compliant=0, rows_compliant=0)

    def record_fields(expected, actual):
        for name, metric in fields.items():
            metric['total'] += 1
            known = expected[name] != 'NONE'
            prefix = 'known' if known else 'absent'
            metric[f'{prefix}_total'] += 1
            if actual is None:
                metric[f'{prefix}_unavailable'] += 1
            elif actual[name] == expected[name]:
                metric['matches'] += 1
                metric[f'{prefix}_matches'] += 1
            elif known:
                metric['known_missing' if actual[name] == 'NONE' else 'known_wrong'] += 1
            else:
                metric['absent_spurious'] += 1

    for prediction in predictions:
        raw_id = prediction['image_id']
        image_id = raw_id.zfill(6) if raw_id.isdigit() else raw_id
        if image_id in seen:
            raise ValueError(f'Duplicate prediction image_id: {image_id}')
        seen.add(image_id)
        raw_actual = prediction.get('final_date')
        try:
            actual_fields = _evaluation_fields(raw_actual)
        except ValueError:
            actual_fields = None
        actual = actual_fields['final_date'] if actual_fields else None
        output_kinds[_date_kind(actual) if actual is not None else 'invalid'] += 1
        format_counts['rows'] += 1
        date_compliant = actual_fields is not None and raw_actual == actual
        format_counts['final_date_compliant'] += int(date_compliant)
        format_counts['rows_compliant'] += int(date_compliant and
            list(prediction) == ['image_id', *DATE_FIELDS, 'final_date'] and
            all(prediction.get(name) == actual_fields[name] for name in DATE_FIELDS))
        label = labels.get(image_id)
        if label is None:
            skipped['unlabelled_predictions'] += 1
            continue
        if not all_label_statuses and label['라벨 상태'] not in ('manual', 'approved'):
            skipped['unconfirmed_labels'] += 1
            continue
        expected = label['정답 날짜'].strip()
        if not expected:
            raise ValueError(f'Empty ground truth: {image_id}')
        expected_fields = _evaluation_fields(expected)
        expected = expected_fields['final_date']
        kind = _date_kind(expected)
        is_failure = raw_id in failed or image_id in failed
        record_fields(expected_fields, None if is_failure else actual_fields)
        correct = actual == expected and not is_failure
        categories[kind]['total'] += 1
        categories[kind]['correct'] += int(correct)
        if not correct:
            error_type = ('실행 오류' if is_failure else '출력 형식 오류' if actual_fields is None else
                          '오검출' if expected == MISSING_DATE else '미검출' if actual == MISSING_DATE else '날짜 불일치')
            counts[error_type] += 1
            errors.append({'image_id':image_id,'expected':expected,'actual':raw_actual,
                           'label_status':label['라벨 상태'], 'difficulty':label.get('난이도',''),
                           'error_types':label.get('오류 유형',''), 'failure_type':error_type})
    eligible = {key for key,row in labels.items() if all_label_statuses or row['라벨 상태'] in ('manual', 'approved')}
    missing = sorted(eligible-seen)
    for image_id in missing:
        expected = labels[image_id]['정답 날짜'].strip()
        if not expected:
            raise ValueError(f'Empty ground truth: {image_id}')
        expected_fields = _evaluation_fields(expected)
        expected = expected_fields['final_date']
        kind = _date_kind(expected)
        record_fields(expected_fields, None)
        categories[kind]['total'] += 1
        counts['출력 누락'] += 1
        errors.append({'image_id': image_id, 'expected': expected, 'actual': None,
                       'failure_type': '출력 누락'})
    total = sum(item['total'] for item in categories.values())
    if not total:
        raise ValueError('No confirmed labels matched predictions; check IDs, label status and input range.')
    exact = sum(item['correct'] for item in categories.values())
    for metric in fields.values():
        metric['match_rate'] = metric['matches'] / metric['total']
        metric['known_match_rate'] = metric['known_matches'] / metric['known_total'] if metric['known_total'] else None
        metric['absent_match_rate'] = metric['absent_matches'] / metric['absent_total'] if metric['absent_total'] else None
    format_counts['all_rows_compliant'] = bool(format_counts['rows'] and
        format_counts['rows_compliant'] == format_counts['rows'])
    for key in ('final_date_compliant', 'rows_compliant'):
        format_counts[f'{key}_rate'] = format_counts[key] / format_counts['rows'] if format_counts['rows'] else None
    return {'evaluated_labels':total, 'exact_matches':exact, 'exact_match_rate':exact/total,
            'accuracy_target':0.95, 'accuracy_target_met':exact/total >= 0.95,
            'accuracy_metric':'exact_match_rate',
            'field_metrics':fields, 'prediction_categories':output_kinds,
            'submission_format':format_counts,
            'official_partial_score':None,
            'metric_scope':'Internal exact match target is 95%; field metrics are diagnostics, not official points. '
                           'Official field weights and NONE scoring are unknown. Legacy NONE-NONE-NONE is normalized only for semantic comparison. '
                           'Field denominators include all eligible labels; unavailable means failure, invalid output or missing row. '
                           'Submission format and prediction categories cover all returned rows.',
            'categories':categories, 'errors':errors, 'error_type_counts':dict(counts),
            'skipped':dict(skipped), 'labels_without_predictions':missing}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run and score the local ITDA OCR validation slice."
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("labels_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--limit", type=int, default=None, help="Optional image limit; default evaluates all input images.")
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--all-label-statuses", action="store_true")
    parser.add_argument("--mobile-only", action="store_true")
    parser.add_argument("--with-rotations", action="store_true")
    parser.add_argument("--target-seconds-500", type=float, default=DEFAULT_TARGET_SECONDS_500,
                        help="Internal relative time target for 500 images (default: 1500); timeout stays 2400.")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error('--limit must be positive')
    if not math.isfinite(args.target_seconds_500) or not 0 < args.target_seconds_500 < TIMEOUT_SECONDS_500:
        parser.error('--target-seconds-500 must be between 0 and 2400 (exclusive)')

    config = PipelineConfig(
        enable_clahe=not args.mobile_only,
        enable_recovery_fallback=not args.mobile_only,
        enable_rotation_fallback=args.with_rotations and not args.mobile_only,
        enable_tile_fallback=not args.mobile_only,
    )
    labels = read_labels(args.labels_csv)
    # Freeze evaluation scope before inference, not from whichever rows succeed.
    expected_images = discover_images(args.input_dir)
    if args.limit is not None:
        expected_images = expected_images[:args.limit]
    runtime = run_timed_pipeline(
        args.input_dir, args.output_csv, config=config, max_images=args.limit,
        expected_images=expected_images,
    )
    predictions = read_predictions(args.output_csv)
    report = {'runtime':runtime, **score_predictions(labels, predictions, runtime['failures'], all_label_statuses=args.all_label_statuses,
                                                     expected_ids=[path.stem for path in expected_images])}
    report['targets'] = assess_targets(runtime, report, target_seconds_500=args.target_seconds_500,
                                       confirmed_labels_only=not args.all_label_statuses)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if runtime['status'] == 'timeout':
        raise SystemExit(124)
    if runtime['status'] != 'completed':
        raise SystemExit(1)


if __name__ == "__main__":
    main()
