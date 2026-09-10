import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import PipelineConfig, discover_images, run_pipeline

REFERENCE_IMAGES = 500
TIMEOUT_SECONDS_500 = 2400.0
DEFAULT_TARGET_SECONDS_500 = 1600.0


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
    per_image = elapsed / images
    target_per_image = target_seconds_500 / REFERENCE_IMAGES
    complete_labels = confirmed_labels_only and accuracy['evaluated_labels'] == images
    output_complete = not accuracy['labels_without_predictions'] and not accuracy['skipped'].get('unlabelled_predictions', 0)
    no_failures = not runtime['failures']
    speed_met = per_image <= target_per_image
    joint_met = bool(complete_labels and output_complete and no_failures
                     and accuracy['accuracy_target_met'] and speed_met)
    return {
        'reference_images': REFERENCE_IMAGES,
        'accuracy_target': 0.95,
        'internal_seconds_500': target_seconds_500,
        'timeout_seconds_500': TIMEOUT_SECONDS_500,
        'target_seconds_per_image': target_per_image,
        'timeout_reference_seconds_per_image': TIMEOUT_SECONDS_500 / REFERENCE_IMAGES,
        'total_seconds_per_input_image': per_image,
        'input_images_per_second': images / elapsed,
        'relative_time_budget_seconds': images * target_per_image,
        'seconds_500_equivalent': per_image * REFERENCE_IMAGES,
        'relative_speed_target_met': speed_met,
        'all_inputs_have_confirmed_labels': complete_labels,
        'output_complete': output_complete,
        'runtime_errors_zero': no_failures,
        'local_relative_joint_target_met': joint_met,
        'local_500_joint_target_met': joint_met if images == REFERENCE_IMAGES else None,
        'actual_500_timeout_met': elapsed <= TIMEOUT_SECONDS_500 if images == REFERENCE_IMAGES else None,
        'scope': 'Local measured run, including backend initialization and input/output. '
                 'Python/import startup excluded. 500-equivalent is normalization, not a measured 500-image result; '
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
    for prediction in predictions:
        raw_id = prediction['image_id']
        image_id = raw_id.zfill(6) if raw_id.isdigit() else raw_id
        if image_id in seen:
            raise ValueError(f'Duplicate prediction image_id: {image_id}')
        seen.add(image_id)
        label = labels.get(image_id)
        if label is None:
            skipped['unlabelled_predictions'] += 1
            continue
        if not all_label_statuses and label['라벨 상태'] != 'manual':
            skipped['unconfirmed_labels'] += 1
            continue
        expected, actual = label['정답 날짜'].strip(), prediction['final_date']
        if not expected:
            raise ValueError(f'Empty ground truth: {image_id}')
        kind = 'none' if expected == 'NONE' else 'partial' if 'NONE' in expected else 'full'
        is_failure = raw_id in failed or image_id in failed
        correct = actual == expected and not is_failure
        categories[kind]['total'] += 1
        categories[kind]['correct'] += int(correct)
        if not correct:
            error_type = '실행 오류' if is_failure else '오검출' if expected == 'NONE' else '미검출' if actual == 'NONE' else '날짜 불일치'
            counts[error_type] += 1
            errors.append({'image_id':image_id,'expected':expected,'actual':actual,
                           'label_status':label['라벨 상태'], 'difficulty':label.get('난이도',''),
                           'error_types':label.get('오류 유형',''), 'failure_type':error_type})
    eligible = {key for key,row in labels.items() if all_label_statuses or row['라벨 상태']=='manual'}
    missing = sorted(eligible-seen)
    for image_id in missing:
        expected = labels[image_id]['정답 날짜'].strip()
        if not expected:
            raise ValueError(f'Empty ground truth: {image_id}')
        kind = 'none' if expected == 'NONE' else 'partial' if 'NONE' in expected else 'full'
        categories[kind]['total'] += 1
        counts['출력 누락'] += 1
        errors.append({'image_id': image_id, 'expected': expected, 'actual': None,
                       'failure_type': '출력 누락'})
    total = sum(item['total'] for item in categories.values())
    if not total:
        raise ValueError('No confirmed labels matched predictions; check IDs, label status and input range.')
    exact = sum(item['correct'] for item in categories.values())
    return {'evaluated_labels':total, 'exact_matches':exact, 'exact_match_rate':exact/total,
            'accuracy_target':0.95, 'accuracy_target_met':exact/total >= 0.95,
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
                        help="Internal relative time target for 500 images (default: 1600); timeout stays 2400.")
    args = parser.parse_args()
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
    runtime = run_pipeline(
        args.input_dir, args.output_csv, config=config, max_images=args.limit
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


if __name__ == "__main__":
    main()
