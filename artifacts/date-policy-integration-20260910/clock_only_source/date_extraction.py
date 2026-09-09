from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date

MIN_YEAR = 1
MAX_YEAR = 2035

POSITIVE_CONTEXT = re.compile(
    r"소비\s*기한|유통\s*기한|품질\s*유지\s*기한|까지|"
    r"EXP(?:IRY|IRES|DATE)?|USE\s*BY|BEST\s*(?:BEFORE|BY)|BBE?\b|賞味|有效期?",
    re.IGNORECASE,
)
NEGATIVE_CONTEXT = re.compile(
    r"제조(?:일자|일)?|생산(?:일자|일)?|포장(?:일자|일)?|부터|"
    r"MFG|MFD|PROD(?:UCTION)?|PACK(?:ED)?\s*ON",
    re.IGNORECASE,
)
UNTIL_CONTEXT = re.compile(
    r"까지|EXP(?:IRY|IRES|DATE)?|USE\s*BY|BEST\s*(?:BEFORE|BY)", re.IGNORECASE
)
FROM_CONTEXT = re.compile(
    r"부터|제조(?:일자|일)?|생산(?:일자|일)?|MFG|MFD|PROD(?:UCTION)?", re.IGNORECASE
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
class OCRLine:
    text: str
    score: float
    box: tuple[float, float, float, float]
    source: str = "paddle-mobile"
    variant: str = "original"
    members: tuple[int, ...] = ()

    @property
    def width(self) -> float:
        return max(1.0, self.box[2] - self.box[0])

    @property
    def height(self) -> float:
        return max(1.0, self.box[3] - self.box[1])

    @property
    def center(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)


@dataclass(frozen=True)
class ParsedDate:
    value: date
    raw: str
    start: int
    end: int
    year_digits: int
    separator: str
    repaired: bool = False


@dataclass(frozen=True)
class DateCandidate:
    value: date
    raw: str
    score: float
    ocr_score: float
    year_digits: int
    repaired: bool
    separator: str
    source: str
    variant: str
    positive_hits: tuple[str, ...] = ()
    negative_hits: tuple[str, ...] = ()
    box: tuple[float, float, float, float] = (0, 0, 0, 0)
    members: tuple[int, ...] = ()
    explicit_positive: bool = False
    explicit_negative: bool = False

    @property
    def iso(self) -> str:
        return self.value.isoformat()


@dataclass(frozen=True)
class DateSelection:
    final_date: str | None
    score: float
    margin: float
    confident: bool
    reason: str
    candidates: tuple[DateCandidate, ...]

    @property
    def is_partial(self) -> bool:
        return self.final_date is not None and "NONE" in self.final_date


def _valid_date(year: int, month: int, day: int) -> date | None:
    if year < 100:
        year += 2000
    if not MIN_YEAR <= year <= MAX_YEAR:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _normalise_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = re.sub(r"[‐‑‒–—―−]", "-", value)
    return re.sub(r"\s+", " ", value).strip()


def _date_text(text: str) -> str:
    text = re.sub(r"월\s*[/.-]\s*일\s*[/.-]\s*년", "MM/DD/YY", text)
    text = re.sub(r"일\s*[/.-]\s*월\s*[/.-]\s*년", "DD/MM/YY", text)
    return (
        _normalise_text(text).replace("년", ".").replace("월", ".").replace("일", " ")
    )


def _repaired_text(text: str) -> str:
    return text.translate(
        str.maketrans(
            {
                "O": "0",
                "o": "0",
                "Q": "0",
                "I": "1",
                "l": "1",
                "|": "1",
                "Z": "2",
                "S": "5",
                "B": "8",
            }
        )
    )


def _emit_match(
    match: re.Match[str],
    order: str,
    year_digits: int,
    separator: str,
    repaired: bool,
) -> ParsedDate | None:
    groups = match.groups()
    if order == "ymd":
        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
    elif order == "dmy":
        day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
    elif order == "mdy":
        month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
    else:
        raise ValueError(f"Unknown date order: {order}")
    parsed = _valid_date(year, month, day)
    if parsed is None:
        return None
    return ParsedDate(
        parsed,
        match.group(0),
        match.start(),
        match.end(),
        year_digits,
        separator,
        repaired,
    )


def _iter_numeric_dates(text: str, repaired: bool) -> Iterable[ParsedDate]:
    separator = r"[./,:\-]"
    delimiter = r"(?:\s*[./,:\-]\s*|\s+)"
    # A printed order takes precedence over the fallback for ambiguous numbers.
    explicit = next((order for pattern, order in (
        (r"MM\s*[/.-]\s*DD\s*[/.-]\s*Y{2,4}", "mdy"),
        (r"DD\s*[/.-]\s*MM\s*[/.-]\s*Y{2,4}", "dmy"),
        (r"Y{2,4}\s*[/.-]\s*MM\s*[/.-]\s*DD", "ymd"),
    ) if re.search(pattern, text, re.IGNORECASE)), None)
    ordered_spans = []
    for match in re.finditer(
        r"(?<![\d./,:\-])(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(20\d{2}|\d{2})(?!\d|\s*:)", text
    ):
        first, second = int(match[1]), int(match[2])
        order = explicit
        if order is None and first <= 12 < second:
            order = "mdy"
        if order is not None:
            ordered_spans.append((match.start(), match.end()))
            year_digits = len(match[1] if order == "ymd" else match[3])
            parsed = _emit_match(match, order, year_digits, "separated", repaired)
            if parsed:
                yield parsed
    patterns: list[tuple[str, str, int, str]] = [
        (
            rf"(?<!\d)(20\d{{2}}){delimiter}(\d{{1,2}}){delimiter}(\d{{1,2}})",
            "ymd",
            4,
            "separated",
        ),
        (r"(?<!\d)(20\d{2})\s+(\d{1,2})\s+(\d{1,2})(?!\d)", "ymd", 4, "space"),
        (
            rf"(?<!\d)(20\d{{2}})\s*{separator}\s*(\d{{2}})(\d{{2}})(?!\d)",
            "ymd",
            4,
            "joined",
        ),
        (
            rf"(?<!\d)(20\d{{2}})(\d{{2}})\s*{separator}\s*(\d{{1,2}})(?!\d)",
            "ymd",
            4,
            "joined",
        ),
        (r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", "ymd", 4, "compact"),
        (
            rf"(?<!\d)(1[5-9]|2\d|3[0-5]){delimiter}(\d{{1,2}}){delimiter}(\d{{1,2}})",
            "ymd",
            2,
            "separated",
        ),
        (
            r"(?<!\d)(1[5-9]|2\d|3[0-5])\s+(\d{1,2})\s+(\d{1,2})(?!\d)",
            "ymd",
            2,
            "space",
        ),
        (r"(?<!\d)(1[5-9]|2\d|3[0-5])(\d{2})(\d{2})(?!\d)", "ymd", 2, "compact"),
        (
            rf"(?<!\d)(\d{{1,2}}){delimiter}(\d{{1,2}}){delimiter}(20\d{{2}})(?!\d)",
            "end_year",
            4,
            "separated",
        ),
        (r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", "end_year", 4, "compact"),
    ]
    for pattern, order, year_digits, sep_name in patterns:
        for match in re.finditer(pattern, text):
            if any(start <= match.start() and match.end() <= end for start, end in ordered_spans):
                continue
            # A day fragment followed by HH:MM is not YY MM:DD.
            if re.fullmatch(r"\d{1,2}\s+\d{1,2}:\d{2}", match.group(0)):
                continue
            actual_order = order
            if order == "end_year":
                first, second = int(match.group(1)), int(match.group(2))
                if first > 12 and second <= 12:
                    actual_order = "dmy"
                elif second > 12 and first <= 12:
                    actual_order = "mdy"
                elif explicit in {"mdy", "dmy"}:
                    actual_order = explicit
                else:
                    actual_order = "dmy"
            parsed = _emit_match(match, actual_order, year_digits, sep_name, repaired)
            if parsed:
                yield parsed

    # A frequent detector/recognizer error drops the leading 2 from 20YY.
    for match in re.finditer(
        rf"(?<!\d)0(2\d){delimiter}(\d{{1,2}}){delimiter}(\d{{1,2}})", text
    ):
        parsed = _valid_date(
            2000 + int(match.group(1)), int(match.group(2)), int(match.group(3))
        )
        if parsed:
            yield ParsedDate(
                parsed,
                match.group(0),
                match.start(),
                match.end(),
                4,
                "repaired-year",
                True,
            )

    # Dot-matrix print occasionally turns the leading "20" into one stray digit,
    # or recognizes a separator as an ASCII letter (for example 2027W3.02).
    for match in re.finditer(
        rf"(?<!\d)[01](1[5-9]|2\d|3[0-5]){delimiter}(\d{{1,2}}){delimiter}(\d{{1,2}})",
        text,
    ):
        parsed = _valid_date(
            2000 + int(match.group(1)), int(match.group(2)), int(match.group(3))
        )
        if parsed:
            yield ParsedDate(
                parsed,
                match.group(0),
                match.start(),
                match.end(),
                4,
                "repaired-year",
                True,
            )
    for match in re.finditer(
        rf"(?<!\d)(20\d{{2}})[A-Z](\d{{1,2}}){delimiter}(\d{{1,2}})",
        text,
        re.IGNORECASE,
    ):
        parsed = _valid_date(
            int(match.group(1)), int(match.group(2)), int(match.group(3))
        )
        if parsed:
            yield ParsedDate(
                parsed,
                match.group(0),
                match.start(),
                match.end(),
                4,
                "repaired-separator",
                True,
            )


def _iter_month_name_dates(text: str, repaired: bool) -> Iterable[ParsedDate]:
    month = r"JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"
    for match in re.finditer(
        rf"(?<!\d)(20\d{{2}})\s*[./-]?\s*({month})\s*[./-]?\s*(\d{{1,2}})(?!\d)",
        text, re.IGNORECASE,
    ):
        parsed = _valid_date(int(match[1]), MONTHS[match[2].upper()], int(match[3]))
        if parsed:
            yield ParsedDate(parsed, match[0], match.start(), match.end(), 4, "month-name", repaired)
    for match in re.finditer(
        rf"(?<!\w)(\d{{1,2}})\s*[./,\-]?\s*({month})\s*[./,\-]?\s*(\d{{2}}|20\d{{2}})(?!\d)",
        text,
        re.IGNORECASE,
    ):
        parsed = _valid_date(
            int(match.group(3)), MONTHS[match.group(2).upper()], int(match.group(1))
        )
        if parsed:
            yield ParsedDate(
                parsed,
                match.group(0),
                match.start(),
                match.end(),
                len(match.group(3)),
                "month-name",
                repaired,
            )
    for match in re.finditer(
        rf"(?<!\w)({month})\s*[./,\-]?\s*(\d{{1,2}})(?:\s*[./,\-]\s*|\s+)(\d{{2}}|20\d{{2}})(?!\d)",
        text,
        re.IGNORECASE,
    ):
        parsed = _valid_date(
            int(match.group(3)), MONTHS[match.group(1).upper()], int(match.group(2))
        )
        if parsed:
            yield ParsedDate(
                parsed,
                match.group(0),
                match.start(),
                match.end(),
                len(match.group(3)),
                "month-name",
                repaired,
            )


def parse_dates(text: str) -> list[ParsedDate]:
    original = _date_text(text)
    variants = [(original, False)]
    repaired = _repaired_text(original)
    if repaired != original:
        variants.append((repaired, True))

    best: dict[tuple[date, int, int], ParsedDate] = {}
    for value, was_repaired in variants:
        matches = list(_iter_numeric_dates(value, was_repaired))
        matches.extend(_iter_month_name_dates(value, was_repaired))
        for item in matches:
            key = (item.value, item.start, item.end)
            current = best.get(key)
            if current is None or (current.repaired and not item.repaired):
                best[key] = item
    return sorted(best.values(), key=lambda item: (item.start, item.end, item.value))


def _union_box(lines: Sequence[OCRLine]) -> tuple[float, float, float, float]:
    return (
        min(line.box[0] for line in lines),
        min(line.box[1] for line in lines),
        max(line.box[2] for line in lines),
        max(line.box[3] for line in lines),
    )


def merge_horizontal_lines(lines: Sequence[OCRLine]) -> list[OCRLine]:
    """Create short same-row windows so split strings such as ``2026.`` + ``05.29`` are parsed."""
    indexed = [replace(line, members=(index,)) for index, line in enumerate(lines)]
    ordered = sorted(indexed, key=lambda line: (line.center[1], line.box[0]))
    merged: list[OCRLine] = []
    for start, first in enumerate(ordered):
        group = [first]
        for other in ordered[start + 1 :]:
            if (first.source, first.variant) != (other.source, other.variant):
                continue
            previous = group[-1]
            height = max(previous.height, other.height)
            if abs(other.center[1] - first.center[1]) > 0.8 * max(
                first.height, other.height
            ):
                if other.box[1] > first.box[3] + height:
                    break
                continue
            gap = other.box[0] - previous.box[2]
            if gap < -0.35 * height or gap > 6.0 * height:
                continue
            group.append(other)
            text = " ".join(item.text for item in group)
            if len(text) <= 96 and len(group) <= 4:
                digit_count = sum(character.isdigit() for character in text)
                if digit_count >= 4:
                    merged.append(
                        OCRLine(
                            text=text,
                            score=min(item.score for item in group),
                            box=_union_box(group),
                            source=first.source,
                            variant=first.variant,
                            members=tuple(
                                member for item in group for member in item.members
                            ),
                        )
                    )
            if len(group) == 4:
                break
    return merged


def _box_gap(left: OCRLine, right: OCRLine) -> tuple[float, float]:
    horizontal = max(
        0.0, max(left.box[0], right.box[0]) - min(left.box[2], right.box[2])
    )
    vertical = max(0.0, max(left.box[1], right.box[1]) - min(left.box[3], right.box[3]))
    return horizontal, vertical


def _nearby_context(
    line: OCRLine, originals: Sequence[OCRLine]
) -> tuple[list[str], list[str], float]:
    positives: list[str] = []
    negatives: list[str] = []
    positive_adjustment = 0.0
    negative_adjustment = 0.0
    member_set = set(line.members)
    for index, other in enumerate(originals):
        if index in member_set or (line.source, line.variant) != (other.source, other.variant):
            continue
        positive = POSITIVE_CONTEXT.search(other.text)
        negative = NEGATIVE_CONTEXT.search(other.text)
        if not positive and not negative:
            continue
        horizontal, vertical = _box_gap(line, other)
        scale = max(12.0, line.height, other.height)
        same_row = (
            abs(line.center[1] - other.center[1]) <= 0.9 * scale
            and horizontal <= 9.0 * scale
        )
        close = math.hypot(horizontal, vertical) <= 5.0 * scale
        if not (same_row or close):
            continue
        if positive:
            token = positive.group(0)
            positives.append(token)
            if same_row:
                positive_adjustment = max(
                    positive_adjustment, 1.35 if UNTIL_CONTEXT.search(token) else 0.95
                )
            elif close:
                positive_adjustment = max(positive_adjustment, 0.30)
        if negative:
            token = negative.group(0)
            negatives.append(token)
            if same_row:
                negative_adjustment = max(
                    negative_adjustment, 0.75 if FROM_CONTEXT.search(token) else 0.55
                )
            elif close:
                negative_adjustment = max(negative_adjustment, 0.12)
    return positives, negatives, positive_adjustment - negative_adjustment


def _candidate_from_match(
    match: ParsedDate, line: OCRLine, originals: Sequence[OCRLine]
) -> DateCandidate:
    before = line.text[max(0, match.start - 24) : match.start]
    after = line.text[match.end : match.end + 24]
    local = f"{before} {match.raw} {after}"
    positive_hits = [item.group(0) for item in POSITIVE_CONTEXT.finditer(local)]
    negative_hits = [item.group(0) for item in NEGATIVE_CONTEXT.finditer(local)]

    score = 1.45 * max(0.0, min(1.0, line.score))
    score += 0.45 if match.year_digits == 4 else 0.15
    if match.separator in {"compact", "joined"}:
        score -= 0.18
    elif match.separator == "month-name":
        score += 0.15
    if match.repaired:
        score -= 0.55

    if positive_hits:
        score += 1.45
    if negative_hits:
        score -= 1.90
    if UNTIL_CONTEXT.search(after[:12]):
        score += 1.10
    if FROM_CONTEXT.search(after[:12]) or FROM_CONTEXT.search(before[-12:]):
        score -= 1.20

    nearby_positive, nearby_negative, nearby_adjustment = _nearby_context(
        line, originals
    )
    positive_hits.extend(nearby_positive)
    negative_hits.extend(nearby_negative)
    score += nearby_adjustment

    digits = re.sub(r"\D", "", line.text)
    if len(digits) >= 11 and match.separator == "compact":
        score -= 1.25
    if re.search(r"(?:TEL|전화|고객\s*센터|LOT\s*NO)", line.text, re.IGNORECASE):
        score -= 0.45

    return DateCandidate(
        value=match.value,
        raw=match.raw,
        score=score,
        ocr_score=line.score,
        year_digits=match.year_digits,
        repaired=match.repaired,
        separator=match.separator,
        source=line.source,
        variant=line.variant,
        positive_hits=tuple(dict.fromkeys(positive_hits)),
        negative_hits=tuple(dict.fromkeys(negative_hits)),
        box=line.box,
        members=line.members,
        explicit_positive=bool(POSITIVE_CONTEXT.search(local)),
        explicit_negative=bool(NEGATIVE_CONTEXT.search(local)),
    )


def extract_candidates(lines: Sequence[OCRLine]) -> list[DateCandidate]:
    originals = [
        replace(line, text=_normalise_text(line.text), members=line.members or (index,))
        for index, line in enumerate(lines)
    ]
    search_lines = originals + merge_horizontal_lines(originals)
    candidates: list[DateCandidate] = []
    for line in search_lines:
        for match in parse_dates(line.text):
            candidates.append(_candidate_from_match(match, line, originals))
    return candidates


def _nearer_role(candidate: DateCandidate, other: DateCandidate, lines: Sequence[OCRLine], pattern: re.Pattern[str]) -> bool:
    """A split role token must be near this date and nearer than to its partner."""
    for line in lines:
        if (line.source, line.variant) != (candidate.source, candidate.variant) or not pattern.search(line.text):
            continue
        scale = max(12.0, candidate.box[3] - candidate.box[1], line.height)
        horizontal = max(0.0, max(candidate.box[0], line.box[0]) - min(candidate.box[2], line.box[2]))
        distance = abs((candidate.box[1] + candidate.box[3]) / 2 - line.center[1])
        other_distance = abs((other.box[1] + other.box[3]) / 2 - line.center[1])
        if horizontal <= 9 * scale and distance <= 1.5 * scale and distance < other_distance:
            return True
    return False


def _interval_endpoint(candidates: Sequence[DateCandidate], ranked: Sequence[DateCandidate], lines: Sequence[OCRLine]) -> DateCandidate | None:
    """Prefer a local, supported endpoint; unrelated dates never form an interval."""
    endpoints = set()
    for first in candidates:
        for last in candidates:
            if (first.source, first.variant) != (last.source, last.variant):
                continue
            if not 1 <= (last.value - first.value).days <= 550:
                continue
            height = max(12.0, first.box[3] - first.box[1], last.box[3] - last.box[1])
            horizontal = max(0.0, max(first.box[0], last.box[0]) - min(first.box[2], last.box[2]))
            vertical = max(0.0, max(first.box[1], last.box[1]) - min(first.box[3], last.box[3]))
            if horizontal > 9 * height or vertical > 5 * height:
                continue
            # Ignore a window that accidentally joined separate date boxes.
            if set(first.members) & set(last.members) and first.members != last.members:
                continue
            paired_roles = (first.explicit_negative or _nearer_role(first, last, lines, FROM_CONTEXT)) and not last.explicit_negative
            explicit_end = (last.explicit_positive or _nearer_role(last, first, lines, UNTIL_CONTEXT)) and not last.explicit_negative
            equal_unlabelled = (
                not first.positive_hits and not first.negative_hits
                and not last.positive_hits and not last.negative_hits
                and abs(first.score - last.score) <= 0.15
                and min(first.ocr_score, last.ocr_score) >= 0.65
            )
            if (paired_roles or explicit_end or equal_unlabelled) and last.score >= ranked[0].score - (2.60 if paired_roles else 0.15):
                endpoints.add(last.iso)
    choices = [item for item in ranked if item.iso in endpoints]
    return max(choices, key=lambda item: (item.score, item.value), default=None)


def _select_full_date(lines: Sequence[OCRLine], *, final: bool = False) -> DateSelection:
    candidates = extract_candidates(lines)
    if not candidates:
        return DateSelection(
            None, float("-inf"), float("inf"), False, "no-valid-date", ()
        )

    grouped: dict[str, list[DateCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.iso, []).append(candidate)

    ranked: list[DateCandidate] = []
    for same_date in grouped.values():
        best = max(same_date, key=lambda item: item.score)
        independent_passes = {(item.source, item.variant) for item in same_date}
        agreement_bonus = min(0.60, 0.22 * (len(independent_passes) - 1))
        ranked.append(replace(best, score=best.score + agreement_bonus))
    ranked.sort(key=lambda item: (item.score, item.value), reverse=True)

    # Pair only dates supported by the same local OCR coordinate frame.
    interval_preferred = False
    endpoint = _interval_endpoint(candidates, ranked, lines)
    if endpoint is not None:
        best_score = ranked[0].score
        ranked.remove(endpoint)
        ranked.insert(0, replace(endpoint, score=max(endpoint.score, best_score + 0.05)))
        interval_preferred = True

    best = ranked[0]
    margin = best.score - ranked[1].score if len(ranked) > 1 else float("inf")
    has_positive = bool(best.positive_hits)
    has_negative = bool(best.negative_hits)

    if best.score < 1.05 and not interval_preferred:
        explicit_manufacturing = (
            has_negative and not has_positive and best.ocr_score >= 0.70
        )
        return DateSelection(
            None,
            best.score,
            margin,
            explicit_manufacturing,
            "negative-context" if explicit_manufacturing else "score-below-threshold",
            tuple(ranked),
        )

    confident = (
        (
            has_positive
            and best.score >= 2.15
            and margin >= 0.35
            and (
                not has_negative
                or interval_preferred
                or (len(ranked) == 1 and best.score >= 3.0)
            )
        )
        or (
            len(ranked) == 1
            and best.score >= 1.65
            and best.ocr_score >= 0.65
            and not best.repaired
            and not has_negative
        )
        or (
            best.score >= 2.35
            and margin >= 0.65
            and (
                not has_negative
                or interval_preferred
                or (len(ranked) == 1 and best.score >= 3.0)
            )
        )
    )
    if final:
        confident = True
    reason = "accepted" if confident else "ambiguous"
    return DateSelection(best.iso, best.score, margin, confident, reason, tuple(ranked))


def _partial_dates(text: str) -> Iterable[str]:
    """Parse missing fields without borrowing digits from a broken full date."""
    occupied = []
    for match in re.finditer(
        r"(?<![\d./-])(20\d{2})\s*[년./-]\s*(\d{1,2})(?:월)?(?!월|\d|\s*[./-]\s*\d|\s*\d{1,2}\s*일)", text
    ):
        occupied.append((match.start(), match.end()))
        if MIN_YEAR <= int(match[1]) <= MAX_YEAR and 1 <= int(match[2]) <= 12:
            yield f"{int(match[1]):04d}-{int(match[2]):02d}-NONE"
    months = "|".join(MONTHS)
    for match in re.finditer(rf"(?<!\w)({months})\s*[./-]?\s*(20\d{{2}})(?!\d)", text, re.IGNORECASE):
        if MIN_YEAR <= int(match[2]) <= MAX_YEAR:
            yield f"{int(match[2]):04d}-{MONTHS[match[1].upper()]:02d}-NONE"
    for match in re.finditer(
        r"(?<![\d./-])(\d{1,2})\s*[월./-]\s*(\d{1,2})(?:일)?(?!\d|\s*[./-]\s*\d)", text
    ):
        if re.search(r"\d\s*[년./-]\s*$", text[:match.start()]) or any(start <= match.start() < end for start, end in occupied):
            continue
        try:
            # Leap-year calendar checks month/day only; this year is never output.
            date(2000, int(match[1]), int(match[2]))
        except ValueError:
            continue
        yield f"NONE-{int(match[1]):02d}-{int(match[2]):02d}"


def select_date(lines: Sequence[OCRLine], *, final: bool = False) -> DateSelection:
    full = _select_full_date(lines, final=final)
    if full.final_date is not None:
        return full
    partials: dict[str, float] = {}
    for index, line in enumerate(lines):
        text = _normalise_text(line.text)
        if parse_dates(text) or line.score < 0.65:
            continue
        positive = bool(POSITIVE_CONTEXT.search(text))
        negative = bool(NEGATIVE_CONTEXT.search(text))
        if negative or re.search(r"보관|온도|℃|kg|mg|g\b|cm|%|TEL|전화|LOT\s*NO", text, re.IGNORECASE):
            continue
        _, near_negative, adjustment = _nearby_context(replace(line, members=(index,)), lines)
        if near_negative and not positive:
            continue
        for value in _partial_dates(text):
            score = 1.45 * line.score + (0.15 if value.startswith("NONE") else 0.30) + (1.45 if positive else 0) + adjustment
            if score >= 1.35:
                partials[value] = max(score, partials.get(value, -math.inf))
    if not partials:
        return full
    ordered = sorted(partials.items(), key=lambda item: item[1], reverse=True)
    value, score = ordered[0]
    margin = score - ordered[1][1] if len(ordered) > 1 else math.inf
    # Discovery is not confirmation: allow all existing recovery stages to finish.
    return DateSelection(value, score, margin, final, "partial-date", full.candidates)


def submission_fields(final_date: str | None) -> dict[str, str]:
    if final_date is None or final_date == "NONE":
        return {"year": "NONE", "month": "NONE", "day": "NONE", "final_date": "NONE"}
    if "NONE" in final_date:
        if not re.fullmatch(r"(?:NONE-\d{2}-\d{2}|\d{4}-\d{2}-NONE)", final_date):
            raise ValueError(f"Invalid partial date: {final_date}")
        year, month, day = final_date.split("-")
        if year == "NONE":
            date(2000, int(month), int(day))
        elif not MIN_YEAR <= int(year) <= MAX_YEAR or not 1 <= int(month) <= 12:
            raise ValueError(f"Invalid partial date: {final_date}")
        return {"year": year, "month": month, "day": day, "final_date": final_date}
    parsed = date.fromisoformat(final_date)
    return {
        "year": f"{parsed.year:04d}",
        "month": f"{parsed.month:02d}",
        "day": f"{parsed.day:02d}",
        "final_date": parsed.isoformat(),
    }
