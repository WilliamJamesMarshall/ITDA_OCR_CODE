import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import PipelineConfig, discover_images, run_pipeline


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
    args = parser.parse_args()

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
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
