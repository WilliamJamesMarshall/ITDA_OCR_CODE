from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(r"C:\ITDA_OCR_CODE")
IMAGES = (ROOT / "추가수집데이터").resolve()
METADATA = IMAGES / "metadata"
LABELS = (ROOT / "labels").resolve()
ARTIFACT = ROOT / "artifacts" / "renumber_additional_20260910"
ARTIFACT.mkdir(parents=True, exist_ok=True)

DELETED = {
    "003360", "003376", "003395", "003430", "003441", "003491",
    "003516", "003535", "003609", "003675", "003677", "003689",
    "003708", "003713", "003716", "003719", "003724", "003727",
    "003729", "003730", "003738", "003739",
}
OLD_IDS = [f"{number:06d}" for number in range(3355, 3741)]
SURVIVORS = [image_id for image_id in OLD_IDS if image_id not in DELETED]
MAPPING = {old: f"{3355 + index:06d}" for index, old in enumerate(SURVIVORS)}
FINAL_IDS = [f"{number:06d}" for number in range(3355, 3719)]
RANGE_TOKEN_OLD = "003355_003740"
RANGE_TOKEN_NEW = "003355_003718"
ID_PATTERN = re.compile(r"(?<!\d)(00(?:3[3-7]\d{2}|3740))(?!\d)")
DROP = object()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_id(value) -> str | None:
    if isinstance(value, int) and 3355 <= value <= 3740:
        return f"{value:06d}"
    if isinstance(value, str) and value.isascii() and value.isdigit() and 3355 <= int(value) <= 3740:
        return f"{int(value):06d}"
    return None


def mapped_value(value, new_id: str):
    if isinstance(value, int):
        return int(new_id)
    if isinstance(value, str) and len(value) < 6:
        return str(int(new_id))
    return new_id


def replace_ids_in_string(value: str):
    if value in DELETED or value.removesuffix(".jpg") in DELETED:
        return DROP

    def repl(match: re.Match[str]) -> str:
        old = match.group(1)
        return f"__DELETED_{old}__" if old in DELETED else MAPPING.get(old, old)

    updated = ID_PATTERN.sub(repl, value).replace(RANGE_TOKEN_OLD, RANGE_TOKEN_NEW)
    if "__DELETED_" in updated:
        return DROP
    return updated


def transform_json(value, parent_key: str | None = None):
    if isinstance(value, dict):
        own_id = normalize_id(value.get("image_id"))
        if own_id in DELETED:
            return DROP
        result = {}
        for key, item in value.items():
            key_id = normalize_id(key.removesuffix(".jpg")) if isinstance(key, str) else None
            if key_id in DELETED:
                continue
            if key_id in MAPPING:
                suffix = ".jpg" if str(key).endswith(".jpg") else ""
                new_key = MAPPING[key_id] + suffix
            elif isinstance(key, str):
                changed_key = replace_ids_in_string(key)
                if changed_key is DROP:
                    continue
                new_key = changed_key
            else:
                new_key = key
            if key == "image_id" and own_id in MAPPING:
                changed = mapped_value(item, MAPPING[own_id])
            elif key == "rows" and isinstance(item, list):
                changed_rows = []
                for row in item:
                    if not isinstance(row, list) or not row:
                        changed_rows.append(row)
                        continue
                    row_id = normalize_id(row[0])
                    if row_id in DELETED:
                        continue
                    new_row = list(row)
                    if row_id in MAPPING:
                        new_row[0] = mapped_value(row[0], MAPPING[row_id])
                    changed_rows.append(transform_json(new_row, "row"))
                changed = changed_rows
            else:
                changed = transform_json(item, str(key))
            if changed is not DROP:
                result[new_key] = changed
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            changed = transform_json(item, parent_key)
            if changed is not DROP:
                result.append(changed)
        return result
    if isinstance(value, str):
        exact = normalize_id(value)
        if exact in DELETED:
            return DROP
        if exact in MAPPING:
            return mapped_value(value, MAPPING[exact])
        return replace_ids_in_string(value)
    return value


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preflight() -> None:
    assert IMAGES == Path(r"C:\ITDA_OCR_CODE\추가수집데이터").resolve()
    files = sorted(path.name for path in IMAGES.glob("*.jpg"))
    assert files == [f"{image_id}.jpg" for image_id in OLD_IDS], (
        f"Expected 386 sequential JPGs, found {len(files)}"
    )
    assert len(DELETED) == 22 and DELETED <= set(OLD_IDS)
    assert len(SURVIVORS) == 364 and list(MAPPING.values()) == FINAL_IDS
    manifest_path = METADATA / "source_manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["new_filename"] for row in rows] == files
    for row in rows:
        assert sha256(IMAGES / row["new_filename"]) == row["sha256"]


def write_operation_manifests() -> None:
    with (ARTIFACT / "번호변경표.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["기존_파일명", "새_파일명", "처리"])
        for old in OLD_IDS:
            writer.writerow([f"{old}.jpg", "" if old in DELETED else f"{MAPPING[old]}.jpg", "삭제" if old in DELETED else "유지·재번호"])
    (ARTIFACT / "삭제한_사진_22장.txt").write_text(
        "\n".join(f"{image_id}.jpg" for image_id in sorted(DELETED)) + "\n", encoding="utf-8"
    )


def mutate_images() -> None:
    for image_id in sorted(DELETED):
        target = (IMAGES / f"{image_id}.jpg").resolve()
        assert target.parent == IMAGES and target.is_file()
        target.unlink()
    temporary = []
    for old in SURVIVORS:
        source = (IMAGES / f"{old}.jpg").resolve()
        assert source.parent == IMAGES and source.is_file()
        temp = IMAGES / f".__renumber__{old}.jpg"
        source.rename(temp)
        temporary.append((temp, IMAGES / f"{MAPPING[old]}.jpg"))
    for temp, final in temporary:
        assert not final.exists()
        temp.rename(final)


def mutate_metadata() -> None:
    annotations_path = METADATA / "annotations.json"
    annotations = json.loads(annotations_path.read_text(encoding="utf-8-sig"))
    updated = {}
    for old in OLD_IDS:
        if old not in DELETED:
            updated[f"{MAPPING[old]}.jpg"] = annotations[f"{old}.jpg"]
    annotations_path.write_text(
        json.dumps(updated, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    manifest_path = METADATA / "source_manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    kept = []
    for row in rows:
        old = Path(row["new_filename"]).stem
        if old in DELETED:
            continue
        row["new_filename"] = f"{MAPPING[old]}.jpg"
        kept.append(row)
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(kept)


def dataset_paths(pattern: str):
    for path in LABELS.rglob(pattern):
        relative = path.relative_to(LABELS)
        parts = set(relative.parts)
        if "node_modules" in parts or "validation_000001_003352" in parts:
            continue
        if relative.name.startswith("validation_000001_003352"):
            continue
        yield path


def mutate_csv_files() -> None:
    for path in dataset_paths("*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows or not rows[0] or rows[0][0] != "image_id":
            continue
        output = [rows[0]]
        for row in rows[1:]:
            if not row:
                continue
            old = normalize_id(row[0])
            if old in DELETED:
                continue
            if old in MAPPING:
                row[0] = str(int(MAPPING[old]))
            output.append(row)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle, lineterminator="\n").writerows(output)


def mutate_json_lines() -> None:
    for pattern in ("*.jsonl", "*.ndjson"):
        for path in dataset_paths(pattern):
            if path.name.endswith(".xlsx.inspect.ndjson"):
                continue
            output = []
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if not line.strip():
                    continue
                value = transform_json(json.loads(line))
                if value is not DROP:
                    output.append(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            path.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")


def mutate_json_files() -> None:
    for path in dataset_paths("*.json"):
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        changed = transform_json(value)
        if changed is not DROP:
            write_json(path, changed)


def score_audit(directory: Path):
    truth_path = directory / "ground_truth.json"
    score_path = directory / "scores.json"
    if not truth_path.exists() or not score_path.exists():
        return {}
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    expected = {row["image_id"]: row["truth"] for row in truth}
    old_scores = json.loads(score_path.read_text(encoding="utf-8"))
    new_scores = {}
    records_by_stage = {}
    for stage, old_score in old_scores.items():
        log_path = directory / f"{stage}.jsonl"
        if not log_path.exists():
            continue
        logs = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if {row["image_id"] for row in logs} != set(expected):
            continue
        groups = {key: Counter() for key in ("full", "partial", "none")}
        errors = Counter()
        records = []
        for row in logs:
            image_id = row["image_id"]
            truth_value = expected[image_id]
            prediction = row["prediction"]
            correct = prediction == truth_value and not row.get("error")
            kind = "none" if truth_value == "NONE" else "partial" if "NONE" in truth_value else "full"
            error_type = "" if correct else "실행 오류" if row.get("error") else "오검출" if truth_value == "NONE" else "미검출" if prediction == "NONE" else "부분 날짜 불일치" if kind == "partial" else "날짜 불일치"
            groups[kind]["total"] += 1
            groups[kind]["correct"] += int(correct)
            if error_type:
                errors[error_type] += 1
            records.append({"image_id": image_id, "truth": truth_value, "prediction": prediction,
                            "correct": correct, "kind": kind, "error_type": error_type,
                            "seconds": row.get("elapsed_seconds", 0), "reason": row.get("reason"),
                            "passes": row.get("passes", [])})
        times = sorted(row["seconds"] for row in records)
        n = len(records)
        correct_count = sum(row["correct"] for row in records)
        new_score = dict(old_score)
        new_score.update({
            "total": n,
            "correct": correct_count,
            "incorrect": n - correct_count,
            "accuracy": correct_count / n,
            "categories": {key: dict(value) for key, value in groups.items()},
            "error_types": dict(errors),
            "sum_image_seconds": sum(times),
            "median_image_seconds": median(times),
            "p95_image_seconds": times[math.ceil(n * .95) - 1],
            "pass_counts": dict(Counter(item for row in records for item in row["passes"])),
        })
        if "wilson_95" in new_score:
            rate = correct_count / n
            z = 1.96
            center = (rate + z*z/(2*n)) / (1 + z*z/n)
            half = z * ((rate*(1-rate)/n + z*z/(4*n*n)) ** .5) / (1 + z*z/n)
            new_score["wilson_95"] = [center-half, center+half]
        if "ocr_call_and_input_hash_seconds" in new_score:
            ocr_seconds = sum(event.get("ocr_seconds", 0) for row in logs for event in row.get("events", []))
            new_score["ocr_call_and_input_hash_seconds"] = ocr_seconds
            new_score["other_image_work_seconds"] = sum(times) - ocr_seconds
        new_scores[stage] = new_score
        records_by_stage[stage] = records
    write_json(score_path, new_scores)
    workbook_path = directory / "workbook_data.json"
    if workbook_path.exists():
        workbook = json.loads(workbook_path.read_text(encoding="utf-8"))
        for stage, content in workbook.items():
            if stage in records_by_stage:
                content["records"] = records_by_stage[stage]
        write_json(workbook_path, workbook)
    comparisons_path = directory / "comparisons.json"
    if comparisons_path.exists():
        pairs = []
        for name in json.loads(comparisons_path.read_text(encoding="utf-8")):
            if "_to_" in name:
                left, right = name.split("_to_", 1)
                pairs.append((name, left, right))
        comparisons = {}
        for name, left, right in pairs:
            if left not in records_by_stage or right not in records_by_stage:
                continue
            a = {row["image_id"]: row for row in records_by_stage[left]}
            b = {row["image_id"]: row for row in records_by_stage[right]}
            comparisons[name] = {
                "gained": [key for key in a if not a[key]["correct"] and b[key]["correct"]],
                "lost": [key for key in a if a[key]["correct"] and not b[key]["correct"]],
            }
        write_json(comparisons_path, comparisons)
    return {"old": old_scores, "new": new_scores}


def metric_replacements(metrics):
    replacements = {}
    for stage, old in metrics.get("old", {}).items():
        new = metrics.get("new", {}).get(stage)
        if not new:
            continue
        old_overall = f'{old["correct"]}/{old["total"]} ({100*old["accuracy"]:.2f}%)'
        new_overall = f'{new["correct"]}/{new["total"]} ({100*new["accuracy"]:.2f}%)'
        replacements[old_overall] = new_overall
        for kind in ("full", "partial", "none"):
            oa, na = old["categories"][kind], new["categories"][kind]
            if oa["total"]:
                old_value = f'{oa["correct"]}/{oa["total"]} ({100*oa["correct"]/oa["total"]:.2f}%)'
                new_value = f'{na["correct"]}/{na["total"]} ({100*na["correct"]/na["total"]:.2f}%)'
                replacements[old_value] = new_value
    return replacements


def remap_text(text: str, remove_deleted_lines: bool, replacements: dict[str, str] | None = None) -> str:
    if remove_deleted_lines:
        text = "\n".join(
            line for line in text.splitlines()
            if not any(re.search(rf"(?<!\d){re.escape(image_id)}(?!\d)", line) for image_id in DELETED)
        ) + "\n"
    for old, new in (replacements or {}).items():
        text = text.replace(old, new)

    placeholders = {}
    def repl(match: re.Match[str]) -> str:
        old = match.group(1)
        if old in DELETED:
            token = f"__DELETED_{old}__"
            placeholders[token] = old
            return token
        return MAPPING.get(old, old)
    text = ID_PATTERN.sub(repl, text)
    if placeholders:
        text = re.sub(r"['\"]__DELETED_\d{6}__['\"]\s*,?", "", text)
        text = re.sub(r"^.*__DELETED_\d{6}__.*(?:\n|$)", "", text, flags=re.MULTILINE)
    text = text.replace(RANGE_TOKEN_OLD, RANGE_TOKEN_NEW)
    text = text.replace("386장", "364장").replace("386행", "364행")
    text = text.replace("C2:C387", "C2:C365")
    return text


def mutate_text_files(metrics_by_dir) -> None:
    for path in dataset_paths("*.md"):
        metrics = None
        for directory, values in metrics_by_dir.items():
            if directory in path.parents:
                metrics = values
                break
        if metrics is None and path.parent == LABELS:
            candidates = [value for directory, value in metrics_by_dir.items() if "year_unrestricted" in directory.name]
            metrics = candidates[0] if candidates else None
        text = remap_text(path.read_text(encoding="utf-8-sig"), True, metric_replacements(metrics or {}))
        path.write_text(text, encoding="utf-8")
    for path in dataset_paths("*.txt"):
        path.write_text(remap_text(path.read_text(encoding="utf-8-sig"), True), encoding="utf-8")
    for pattern in ("*.py", "*.mjs"):
        for path in dataset_paths(pattern):
            text = remap_text(path.read_text(encoding="utf-8-sig"), False)
            text = re.sub(r"range\(3355,\s*3741\)", "range(3355, 3719)", text)
            text = re.sub(r"(?<!\d)([=!]=)\s*386(?!\d)", r"\1 364", text)
            text = text.replace("/386", "/364")
            path.write_text(text, encoding="utf-8")


def rename_label_paths() -> None:
    paths = sorted(
        [path for path in LABELS.rglob("*") if RANGE_TOKEN_OLD in path.name],
        key=lambda path: len(path.parts), reverse=True,
    )
    for path in paths:
        target = path.with_name(path.name.replace(RANGE_TOKEN_OLD, RANGE_TOKEN_NEW))
        assert not target.exists(), f"Rename collision: {target}"
        path.rename(target)


def main() -> None:
    current_images = sorted(path.name for path in IMAGES.glob("*.jpg"))
    if current_images == [f"{image_id}.jpg" for image_id in OLD_IDS]:
        preflight()
        write_operation_manifests()
        mutate_images()
        mutate_metadata()
        mutate_csv_files()
    else:
        assert current_images == [f"{image_id}.jpg" for image_id in FINAL_IDS], (
            f"Unexpected resume state: {len(current_images)} JPG files"
        )
        manual = LABELS / "validation_003355_003740_manual.csv"
        assert sum(1 for _ in manual.open(encoding="utf-8-sig")) == 365
    mutate_json_lines()
    mutate_json_files()
    metrics_by_dir = {}
    for directory in sorted(dataset_paths("scores.json")):
        metrics_by_dir[directory.parent] = score_audit(directory.parent)
    mutate_text_files(metrics_by_dir)
    rename_label_paths()
    print(json.dumps({
        "deleted_images": len(DELETED),
        "remaining_images": len(list(IMAGES.glob("*.jpg"))),
        "first": min(path.stem for path in IMAGES.glob("*.jpg")),
        "last": max(path.stem for path in IMAGES.glob("*.jpg")),
        "mapping_rows": len(MAPPING),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
