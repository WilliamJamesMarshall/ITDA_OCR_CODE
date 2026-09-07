import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


FIELDNAMES = ["image_id", "정답 날짜", "라벨 상태", "난이도", "오류 유형", "비고"]
CONSUMPTION_WORDS = re.compile(
    r"소비|유통|까지|EXP(?:IRY|IRES|DATE)?|BEST\s*BEFORE|BEST\s*BY|USE\s*BY|"
    r"BBE?|ED\b|賞味|保質|有效|有效期",
    re.IGNORECASE,
)
PRODUCTION_WORDS = re.compile(
    r"제조|생산|포장|MFG|MFD|PROD(?:UCTION)?|PD\b|제조일자",
    re.IGNORECASE,
)
MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


@dataclass(frozen=True)
class DateCandidate:
    value: date
    raw: str
    score: float
    line_index: int
    year_digits: int
    separator: str
    repaired: bool = False

    @property
    def iso(self):
        return self.value.isoformat()


def compact_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def make_date(year, month, day):
    if year < 100:
        year += 2000
    if not 2015 <= year <= 2030:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def iter_date_parts(text):
    normalized = text.replace("년", ".").replace("월", ".").replace("일", " ")

    patterns = [
        (r"(?<!\d)(20\d{2})\s*([./,:\-])\s*(\d{1,2})\s*\2\s*(\d{1,2})", "ymd", 4),
        (r"(?<!\d)(20\d{2})\s*([./,:\-])\s*(\d{1,2})\s*[./,:\-]\s*(\d{1,2})", "ymd", 4),
        (r"(?<!\d)(20\d{2})\s*([./,:\-])\s*(\d{2})(\d{2})", "ymd_joined", 4),
        (r"(?<!\d)(20\d{2})(\d{2})\s*([./,:\-])\s*(\d{1,2})", "ymd_compact_month", 4),
        (r"(?<!\d)(20\d{2})\s+(\d{1,2})\s+(\d{1,2})(?!\d)", "ymd_space", 4),
        (r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", "ymd_compact", 4),
        (r"(?<!\d)(2[0-9]|30)\s*([./,:\-])\s*(\d{1,2})\s*\2\s*(\d{1,2})(?!\d{2})", "ymd", 2),
        (r"(?<!\d)(\d{1,2})\s*([./,:\-])\s*(\d{1,2})\s*\2\s*(20\d{2})(?!\d)", "dmy", 4),
        (r"(?<!\d)([01]?\d)\s*([./,:\-])\s*(\d{1,2})\s*\2\s*(1[5-9]|2\d|30)(?!\d)", "dmy_short", 2),
        (r"(?<!\d)(\d{1,2})\s+([01]?\d)\s+(20\d{2})(?!\d)", "dmy_space", 4),
        (r"(?<!\d)(20\d{2})[\s./,:\-]+(\d{1,2})[\s./,:\-]+(\d{1,2})", "ymd_space", 4),
    ]
    for pattern, order, year_digits in patterns:
        for match in re.finditer(pattern, normalized):
            groups = match.groups()
            if order == "ymd":
                year, sep, month, day = int(groups[0]), groups[1], int(groups[2]), int(groups[3])
            elif order == "ymd_space":
                year, month, day = map(int, groups)
                sep = "space"
            elif order == "ymd_compact":
                year, month, day = map(int, groups)
                sep = "compact"
            elif order == "ymd_joined":
                year, sep, month, day = int(groups[0]), groups[1], int(groups[2]), int(groups[3])
            elif order == "ymd_compact_month":
                year, month, sep, day = int(groups[0]), int(groups[1]), groups[2], int(groups[3])
            elif order == "dmy":
                day, sep, month, year = int(groups[0]), groups[1], int(groups[2]), int(groups[3])
            elif order == "dmy_short":
                day, sep, month, year = int(groups[0]), groups[1], int(groups[2]), int(groups[3])
            else:
                day, month, year = map(int, groups)
                sep = "space"
            parsed = make_date(year, month, day)
            if parsed:
                yield parsed, match.group(0), year_digits, sep, False

    # Common OCR loss: a leading digit before an otherwise complete YYYY.MM.DD.
    for match in re.finditer(r"(?<!\d)\d(20\d{2})\s*([./,:\-])\s*(\d{1,2})\s*[./,:\-]\s*(\d{1,2})(?!\d)", normalized):
        parsed = make_date(int(match.group(1)), int(match.group(3)), int(match.group(4)))
        if parsed:
            yield parsed, match.group(0), 4, match.group(2), True

    # Common OCR substitutions in a four-digit year and a dropped leading "2".
    for match in re.finditer(r"(?<!\d)2[9OQ]2([4-9])\s*([./,:\-])\s*(\d{1,2})\s*[./,:\-]\s*(\d{1,2})", normalized, re.IGNORECASE):
        parsed = make_date(2020 + int(match.group(1)), int(match.group(3)), int(match.group(4)))
        if parsed:
            yield parsed, match.group(0), 4, match.group(2), True
    for match in re.finditer(r"(?<!\d)0(0\d|1\d|2\d|30)\s*([./,:\-])\s*(\d{1,2})\s*[./,:\-]\s*(\d{1,2})", normalized):
        parsed = make_date(2000 + int(match.group(1)), int(match.group(3)), int(match.group(4)))
        if parsed:
            yield parsed, match.group(0), 4, match.group(2), True

    for match in re.finditer(
        r"(?<!\d)(2[0-9]|30)\s*([./,:\-])\s*[89](\d)\s*[./,:\-]\s*(\d{1,2})",
        normalized,
    ):
        parsed = make_date(int(match.group(1)), int(match.group(3)), int(match.group(4)))
        if parsed:
            yield parsed, match.group(0), 2, match.group(2), True

    month_token = r"JAN|FEB|MAR|[AB]PR|MAY|JUN|JUL|AUG|[S9]EP|[O0]CT|NOV|DEC"
    for match in re.finditer(
        rf"(?<!\d)(\d{{1,2}})\s*[./,:\-]?\s*({month_token})\s*[./,:\-]?\s*(\d{{2}}|20\d{{2}})(?!\d)",
        normalized,
        re.IGNORECASE,
    ):
        token = match.group(2).upper().replace("9", "S").replace("0", "O").replace("BPR", "APR")
        parsed = make_date(int(match.group(3)), MONTHS[token], int(match.group(1)))
        if parsed:
            yield parsed, match.group(0), 4 if len(match.group(3)) == 4 else 2, "month_name", "9" in match.group(2)
    for match in re.finditer(
        rf"(?<![A-Z])({month_token})\s*[./,:\-]?\s*(\d{{1,2}})\s*[./,:\-]?\s*(\d{{2}}|20\d{{2}})(?!\d)",
        normalized,
        re.IGNORECASE,
    ):
        token = match.group(1).upper().replace("9", "S").replace("0", "O").replace("BPR", "APR")
        parsed = make_date(int(match.group(3)), MONTHS[token], int(match.group(2)))
        if parsed:
            yield parsed, match.group(0), 4 if len(match.group(3)) == 4 else 2, "month_name", "9" in match.group(1)

    for match in re.finditer(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", normalized):
        parsed = make_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if parsed:
            yield parsed, match.group(0), 4, "compact", False

    for match in re.finditer(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", normalized):
        first, second, third = map(int, match.groups())
        if 20 <= first <= 30:
            parsed = make_date(first, second, third)
        else:
            parsed = make_date(third, second, first)
        if parsed:
            yield parsed, match.group(0), 2, "compact", True

    for match in re.finditer(r"(?<!\d)([01]\d)(\d{2})[./,:\-](1[5-9]|2\d|30)(?!\d)", normalized):
        parsed = make_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if parsed:
            yield parsed, match.group(0), 2, "compact", True
    for match in re.finditer(r"(?<!\d)(0?[1-9]|1[0-2])[./,:\-](\d{2})(1[5-9]|2\d|30)(?!\d)", normalized):
        parsed = make_date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
        if parsed:
            yield parsed, match.group(0), 2, "compact", True


def extract_candidates(lines):
    candidates = []
    for index, line in enumerate(lines):
        text = compact_text(line.get("text", ""))
        ocr_score = float(line.get("score", 0.0))
        for value, raw, year_digits, separator, repaired in iter_date_parts(text):
            nearby_context = " ".join(
                compact_text(lines[pos].get("text", ""))
                for pos in range(max(0, index - 2), min(len(lines), index + 3))
                if pos != index
            )
            score = ocr_score
            if CONSUMPTION_WORDS.search(text):
                score += 0.60
            elif CONSUMPTION_WORDS.search(nearby_context):
                score += 0.08
            if PRODUCTION_WORDS.search(text):
                score -= 0.40
            elif PRODUCTION_WORDS.search(nearby_context):
                score -= 0.05
            if year_digits == 4:
                score += 0.05
            if repaired:
                score -= 0.15
            candidates.append(
                DateCandidate(value, raw, score, index, year_digits, separator, repaired)
            )

    unique = {}
    for candidate in candidates:
        current = unique.get(candidate.iso)
        if current is None or candidate.score > current.score:
            unique[candidate.iso] = candidate
    return sorted(unique.values(), key=lambda item: (item.value, item.score))


def select_candidate(candidates):
    if not candidates:
        return None
    keyword_candidates = [candidate for candidate in candidates if candidate.score >= 1.35]
    if keyword_candidates:
        return max(keyword_candidates, key=lambda item: (item.score, item.value))
    latest = max(candidates, key=lambda item: item.value)
    same_year = [candidate for candidate in candidates if candidate.value.year == latest.value.year]
    if len(same_year) > 1:
        span = (max(item.value for item in same_year) - min(item.value for item in same_year)).days
        if span <= 31:
            return max(same_year, key=lambda item: item.score)
    # Consumption dates are normally later than manufacturing/packing dates.
    return latest


def classify(row):
    lines = []
    for pass_item in row.get("passes", []):
        lines.extend(pass_item.get("lines", []))
    if not lines:
        lines = row.get("lines", [])

    candidates = extract_candidates(lines)
    selected = select_candidate(candidates)
    if selected is None:
        return {
            "image_id": row["image_id"],
            "정답 날짜": "NONE",
            "라벨 상태": "needs_review",
            "난이도": "hard",
            "오류 유형": "날짜 없음; 반사·흐림·저대비",
            "비고": "RapidOCR에서 유효한 날짜 후보를 찾지 못함",
        }

    errors = []
    if len(candidates) > 1:
        errors.append("제조일자·소비기한 동시")
    if selected.year_digits == 2:
        errors.append("두 자리 연도")
    if selected.separator not in {".", "-"}:
        errors.append("다양한 구분자")
    if selected.score < 0.85 or selected.repaired:
        errors.append("반사·흐림·저대비")
    if not errors:
        errors.append("정상")

    ambiguous = selected.score < 0.75 or selected.repaired
    if len(candidates) > 1:
        same_year = [item for item in candidates if item.value.year == selected.value.year]
        if len(same_year) > 1:
            span = (max(item.value for item in same_year) - min(item.value for item in same_year)).days
            if span <= 31:
                ambiguous = True

    note = ""
    if ambiguous:
        options = ", ".join(candidate.iso for candidate in candidates[-4:])
        note = f"RapidOCR 후보 {options} 중 {selected.iso} 잠정 선택"

    return {
        "image_id": row["image_id"],
        "정답 날짜": selected.iso,
        "라벨 상태": "needs_review" if ambiguous else "rapidocr",
        "난이도": "hard" if ambiguous else "medium" if errors != ["정상"] else "easy",
        "오류 유형": "; ".join(errors),
        "비고": note,
    }


def read_jsonl(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def merge_candidate_rows(primary_rows, supplemental_paths):
    merged = {row["image_id"].zfill(6): {**row, "image_id": row["image_id"].zfill(6)} for row in primary_rows}
    for path in supplemental_paths:
        for supplemental in read_jsonl(path):
            image_id = supplemental["image_id"].zfill(6)
            if image_id not in merged:
                raise ValueError(f"Supplemental OCR row has no primary row: {image_id}")
            extra_lines = []
            for pass_item in supplemental.get("passes", []):
                extra_lines.extend(pass_item.get("lines", []))
            extra_lines.extend(supplemental.get("lines", []))
            merged[image_id].setdefault("lines", []).extend(extra_lines)
    return [merged[key] for key in sorted(merged)]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        row["image_id"] = row["image_id"].zfill(6)
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def validate_rows(rows, start, end):
    expected = [f"{number:06d}" for number in range(start, end + 1)]
    actual = [row["image_id"] for row in rows]
    if actual != expected:
        counts = Counter(actual)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        missing = sorted(set(expected) - set(actual))
        raise ValueError(f"IDs are not sequential; missing={missing[:5]}, duplicates={duplicates[:5]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("existing_csv", type=Path)
    parser.add_argument("candidates_jsonl", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--supplemental-jsonl", type=Path, action="append", default=[])
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=3352)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    existing = read_csv(args.existing_csv)
    candidate_rows = merge_candidate_rows(read_jsonl(args.candidates_jsonl), args.supplemental_jsonl)
    generated = [classify(row) for row in candidate_rows]
    rows = sorted(existing + generated, key=lambda row: row["image_id"])
    validate_rows(rows, args.start, args.end)

    counts = Counter(row["라벨 상태"] for row in rows)
    none_count = sum(row["정답 날짜"] == "NONE" for row in rows)
    print(f"rows={len(rows)} statuses={dict(counts)} none={none_count}")
    if not args.report_only:
        write_csv(args.output_csv, rows)


if __name__ == "__main__":
    main()
