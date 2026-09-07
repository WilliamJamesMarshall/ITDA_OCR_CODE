import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import PipelineConfig, run_pipeline


def read_labels(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    return {row["image_id"].zfill(6): row for row in rows}


def read_predictions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run and score the local ITDA OCR validation slice."
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("labels_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--limit", type=int, default=352)
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
    runtime = run_pipeline(
        args.input_dir, args.output_csv, config=config, max_images=args.limit
    )
    labels = read_labels(args.labels_csv)
    predictions = read_predictions(args.output_csv)

    compared = []
    for prediction in predictions:
        label = labels.get(prediction["image_id"])
        if label is None:
            continue
        if not args.all_label_statuses and label["라벨 상태"] != "manual":
            continue
        compared.append((prediction, label))

    errors = []
    error_types: Counter[str] = Counter()
    for prediction, label in compared:
        expected = label["정답 날짜"]
        actual = prediction["final_date"]
        if actual != expected:
            errors.append(
                {
                    "image_id": prediction["image_id"],
                    "expected": expected,
                    "actual": actual,
                    "label_status": label["라벨 상태"],
                    "difficulty": label["난이도"],
                    "error_types": label["오류 유형"],
                }
            )
            for error_type in label["오류 유형"].split(";"):
                if error_type.strip():
                    error_types[error_type.strip()] += 1

    exact = len(compared) - len(errors)
    report = {
        "runtime": runtime,
        "evaluated_labels": len(compared),
        "exact_matches": exact,
        "exact_match_rate": round(exact / len(compared), 6) if compared else None,
        "errors": errors,
        "error_type_counts": dict(error_types.most_common()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
