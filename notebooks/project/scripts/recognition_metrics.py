"""Approved recognition metrics and deterministic checkpoint selection."""

from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


def normalize_text(value: str) -> str:
    """Apply only the normalization allowed by execution policy v1.0."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = unicodedata.normalize("NFC", value).strip()
    return "".join(ch.upper() if "a" <= ch <= "z" else ch for ch in value)


def edit_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class RecognitionMetrics:
    sample_count: int
    exact_match_count: int
    string_exact_match_rate: float
    edit_error_count: int
    ground_truth_character_count: int
    micro_cer: float
    normalized_edit_similarity: float


def compute_metrics(pairs: Iterable[tuple[str, str]]) -> RecognitionMetrics:
    samples = 0
    exact = 0
    errors = 0
    truth_chars = 0
    similarities = 0.0
    for truth_raw, prediction_raw in pairs:
        truth = normalize_text(truth_raw)
        prediction = normalize_text(prediction_raw)
        distance = edit_distance(truth, prediction)
        samples += 1
        exact += truth == prediction
        errors += distance
        truth_chars += len(truth)
        longest = max(len(truth), len(prediction))
        similarities += 1.0 if longest == 0 else 1.0 - distance / longest
    if samples == 0:
        raise ValueError("at least one recognition sample is required")
    return RecognitionMetrics(
        sample_count=samples,
        exact_match_count=exact,
        string_exact_match_rate=exact / samples,
        edit_error_count=errors,
        ground_truth_character_count=truth_chars,
        micro_cer=0.0 if truth_chars == 0 and errors == 0 else errors / truth_chars,
        normalized_edit_similarity=similarities / samples,
    )


def selection_key(candidate: dict) -> tuple[float, float, float, int]:
    return (
        float(candidate["string_exact_match_rate"]),
        -float(candidate["micro_cer"]),
        float(candidate["normalized_edit_similarity"]),
        -int(candidate["epoch"]),
    )


def select_checkpoint(candidates: Iterable[dict], patience: int = 5) -> dict:
    ordered = sorted(candidates, key=lambda item: int(item["epoch"]))
    if not ordered:
        raise ValueError("at least one checkpoint metric is required")
    if patience < 1:
        raise ValueError("patience must be positive")
    best = ordered[0]
    stale_epochs = 0
    evaluated = [ordered[0]]
    for candidate in ordered[1:]:
        evaluated.append(candidate)
        if selection_key(candidate) > selection_key(best):
            best = candidate
            stale_epochs = 0
        else:
            stale_epochs += 1
        if stale_epochs >= patience:
            break
    result = dict(best)
    result["patience"] = patience
    result["selection_horizon_epoch"] = int(evaluated[-1]["epoch"])
    result["evaluated_checkpoint_count"] = len(evaluated)
    return result


def _score(input_path: Path, output_path: Path | None) -> dict:
    with input_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"ground_truth", "prediction"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("CSV must contain ground_truth and prediction columns")
    result = asdict(
        compute_metrics((row["ground_truth"], row["prediction"]) for row in rows)
    )
    if output_path:
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return result


def _select(input_path: Path, output_path: Path | None, patience: int) -> dict:
    candidates = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = select_checkpoint(candidates, patience=patience)
    if output_path:
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    score = subparsers.add_parser("score")
    score.add_argument("--input", type=Path, required=True)
    score.add_argument("--output", type=Path)
    select = subparsers.add_parser("select")
    select.add_argument("--input", type=Path, required=True)
    select.add_argument("--output", type=Path)
    select.add_argument("--patience", type=int, default=5)
    args = parser.parse_args()
    if args.command == "score":
        result = _score(args.input, args.output)
    else:
        result = _select(args.input, args.output, args.patience)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
