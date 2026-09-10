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
    order: str = "ymd"
    order_reason: str = "calendar_unique"


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
    span: tuple[int, int] = (0, 0)
    order: str = "ymd"
    order_reason: str = "calendar_unique"

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
    digits_confident: bool = False
    order_resolved: bool = False

    @property
    def stop_ocr(self) -> bool:
        """Execution decision, not a claim that date order is proven.

        `confident` remains the compatible legacy spelling. A clear-digit DMY
        fallback can stop OCR with order_resolved=False; forced final output
        can stop with digits_confident=False.
        """
        return self.confident

    @property
    def is_partial(self) -> bool:
        return self.final_date is not None and "NONE" in self.final_date


@dataclass(frozen=True)
class ProductDateRule:
    """Locally verified package rule, never an image-ID or country shortcut."""

    name: str
    required_text: tuple[str, ...]
    order: str
    evidence: str

    def __post_init__(self):
        if self.order not in {"ymd", "dmy", "mdy"}:
            raise ValueError("Invalid product date order")
        if not self.name.strip() or not self.evidence.strip() or not self.required_text or any(
            not token.strip() for token in self.required_text
        ):
            raise ValueError("Product rules require package identifiers and verification evidence")


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
    value = _normalise_text(text)
    # Mask format placeholders without moving date offsets (00일00월00년 is
    # a legend, not a preceding numeric date fragment).
    for start, end, _ in _format_hints(value):
        value = value[:start] + " " * (end - start) + value[end:]
    return value.replace("년", ".").replace("월", ".").replace("일", " ")


def _format_hints(text: str) -> list[tuple[int, int, str]]:
    gap = r"\s*[/.,\-]?\s*"
    hints = []
    for order, letters, korean in (
        ("ymd", ("Y{2,4}", "MM", "DD"), ("[년연]{1,2}", "월{1,2}", "일{1,2}")),
        ("dmy", ("DD", "MM", "Y{2,4}"), ("일{1,2}", "월{1,2}", "[년연]{1,2}")),
        ("mdy", ("MM", "DD", "Y{2,4}"), ("월{1,2}", "일{1,2}", "[년연]{1,2}")),
    ):
        patterns = (r"(?<![A-Z])" + gap.join(letters) + r"(?![A-Z])",
                    gap.join(r"(?:00)?" + part for part in korean))
        for pattern in patterns:
            hints.extend((m.start(), m.end(), order) for m in re.finditer(pattern, text, re.I))
    # A wrapped bottle may hide the last field, but doubled year/month
    # placeholders already exclude DMY and MDY. Never infer from a lone year.
    hints.extend((m.start(), m.end(), "ymd") for m in re.finditer(
        r"[년연]{2}\s*[./,\-]?\s*월{2}(?!\s*[./,\-]?\s*일)", text))
    return hints


def _span_gap(first: tuple[int, int], second: tuple[int, int]) -> int:
    return max(0, first[0] - second[1], second[0] - first[1])


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
        order,
    )


def _iter_numeric_dates(text: str, repaired: bool) -> Iterable[ParsedDate]:
    separator = r"[./,:\-]"
    delimiter = r"(?:\s*[./,:\-]\s*|\s+)"
    occupied = []
    for match in re.finditer(
        rf"(?<!\d)(20\d{{2}}|\d{{1,2}}){delimiter}(\d{{1,2}}){delimiter}((?:19|20)\d{{2}}|\d{{1,2}})", text
    ):
        occupied.append((match.start(), match.end()))
        # Do not borrow HH:MM from a partial date or split an embedded digit run.
        if re.fullmatch(r"\d{1,2}\s+\d{1,2}:\d{1,2}", match[0]):
            continue
        if re.fullmatch(r"\d{1,2}:\d{1,2}\s+\d{1,2}", match[0]):
            continue
        tail = text[match.end():]
        prefix = text[:match.start()]
        # A stray lot digit before MM.DD followed by HH:MM is not DD MM YY.
        if (re.fullmatch(r"\d\s+\d{1,2}[./-]\d{1,2}", match[0])
                and re.match(r"\s+\d{1,2}:\d{2}", tail)):
            continue
        long_year = len(match[1]) == 4
        attached_lot_digit = (len(match[1]) == 1 and prefix and prefix[-1].isalpha()
                              and not re.search(r"(?:EXP|BBE?)$", prefix, re.I))
        if not long_year and (re.search(r"\d[./,:\-]+\s*$", prefix) or attached_lot_digit):
            continue
        if re.match(r"\s*:", tail) or (not long_year and tail[:1].isdigit()
                and not re.match(r"(?:\d{1,2}[^\W\d_]|\d{2}:\d{2})", tail)):
            continue
        for order in ("ymd", "dmy", "mdy"):
            year_index = 1 if order == "ymd" else 3
            day_index = 3 if order == "ymd" else 1 if order == "dmy" else 2
            month_index = 1 if order == "mdy" else 2
            if len(match[year_index]) not in (2, 4) or len(match[day_index]) > 2 or len(match[month_index]) > 2:
                continue
            parsed = _emit_match(match, order, len(match[year_index]), "separated", repaired)
            if parsed:
                yield parsed
    patterns: list[tuple[str, str, int, str]] = [
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
        *((r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", order, 2, "compact") for order in ("ymd", "dmy", "mdy")),
        *((r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", order, 4, "compact") for order in ("dmy", "mdy")),
        *((r"(?<!\d)(\d{1,2})\s+(\d{2})(20\d{2})(?!\d)", order, 4, "joined") for order in ("dmy", "mdy")),
    ]
    for pattern, order, year_digits, sep_name in patterns:
        for match in re.finditer(pattern, text):
            if any(max(start, match.start()) < min(end, match.end()) for start, end in occupied):
                continue
            parsed = _emit_match(match, order, year_digits, sep_name, repaired)
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
    original = text
    # Repair digits without translating letters inside SEP/OCT/etc.
    text = re.sub(r"(?<=EXP)[OQ](?=\d(?:" + month + r"))", "0", text, flags=re.I)
    for match in re.finditer(
        rf"(?<!\d)(20\d{{2}})\s*[./-]?\s*({month})\s*[./-]?\s*(\d{{1,2}})(?!\d)",
        text, re.IGNORECASE,
    ):
        parsed = _valid_date(int(match[1]), MONTHS[match[2].upper()], int(match[3]))
        if parsed:
            yield ParsedDate(parsed, match[0], match.start(), match.end(), 4, "month-name", repaired)
    for match in re.finditer(
        rf"(?:(?<!\w)|(?<=EXP))(\d{{1,2}})\s*[./,\-]?\s*({month})\s*[./,\-]?\s*(\d{{2}}|20\d{{2}})(?!\d)",
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
                repaired or match[0] != original[match.start():match.end()],
                "dmy",
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
                "mdy",
            )


def parse_dates(text: str) -> list[ParsedDate]:
    text = _normalise_text(text)
    original = _date_text(text)
    variants = [(original, False)]
    repaired = _repaired_text(original)
    if repaired != original:
        variants.append((repaired, True))

    best: dict[tuple[date, int, int, str], ParsedDate] = {}
    for value, was_repaired in variants:
        matches = list(_iter_numeric_dates(value, was_repaired))
        matches.extend(_iter_month_name_dates(value, was_repaired))
        for item in matches:
            key = (item.value, item.start, item.end, item.order)
            current = best.get(key)
            if current is None or (current.repaired and not item.repaired):
                best[key] = item
    groups: dict[tuple[int, int], list[ParsedDate]] = {}
    for item in best.values():
        groups.setdefault((item.start, item.end), []).append(item)
    groups = {span: values for span, values in groups.items()
              if not any(other != span and other[0] <= span[0] and span[1] <= other[1] for other in groups)}
    hints = _format_hints(text)
    # Literal units name the fields, independently of the numeric fallback.
    hints.extend((m.start(), m.end(), "ymd") for m in re.finditer(
        r"\d{2,4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일", text))
    selected = []
    for span, values in groups.items():
        linked = {order for start, end, order in hints
                  if _span_gap(span, (start, end)) <= 64
                  and _span_gap(span, (start, end)) == min(_span_gap(s, (start, end)) for s in groups)}
        if len(linked) > 1:
            continue
        if linked:
            selected.extend(replace(v, order_reason="explicit_order") for v in values if v.order in linked)
        else:
            selected.extend(values)
    return sorted(selected, key=lambda item: (item.start, item.end, item.value, item.order))


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
    match: ParsedDate, line: OCRLine, originals: Sequence[OCRLine], role: str | None = None,
) -> DateCandidate:
    before = line.text[max(0, match.start - 24) : match.start]
    after = line.text[match.end : match.end + 24]
    local = f"{before} {match.raw} {after}"
    if role is not None:
        # A one-to-one block match is stronger than a slanted box's nearest
        # keyword. Use the same role scoring as an inline printed role.
        local = f"{match.raw} {'까지' if role == 'end' else '부터'}"
        before, after = "", "까지" if role == "end" else "부터"
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

    nearby_positive, nearby_negative, nearby_adjustment = (
        _nearby_context(line, originals) if role is None else ([], [], 0.0)
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
        span=(match.start, match.end),
        order=match.order,
        order_reason=match.order_reason,
    )


def _printed_pair_roles(originals: Sequence[OCRLine], parsed: Sequence[list[ParsedDate]]) -> dict[int, str]:
    """Align two standalone role labels to two date rows as a block.

    Matching vertical order tolerates perspective skew without assigning both
    labels to the same nearest date. Competing dates/labels invalidate the block.
    """
    date_rows = [(i, line) for i, (line, dates) in enumerate(zip(originals, parsed))
                 if dates and len({(d.start, d.end) for d in dates}) == 1]
    proposals: dict[int, set[str]] = {}
    for pos, (i, first) in enumerate(date_rows):
        for j, second in date_rows[pos + 1:]:
            if (first.source, first.variant) != (second.source, second.variant):
                continue
            scale = max(first.height, second.height)
            dx, dy = _box_gap(first, second)
            if dx > scale or dy > 2 * scale or abs(first.center[1] - second.center[1]) < .3 * scale:
                continue
            block = OCRLine("", 1., _union_box((first, second)), first.source, first.variant)
            if any(k not in (i, j) and (other.source, other.variant) == (first.source, first.variant)
                   and _box_gap(block, other)[0] <= scale and _box_gap(block, other)[1] < scale
                   for k, other in date_rows):
                continue
            labels = []
            for label in originals:
                if ((label.source, label.variant) != (first.source, first.variant) or label.score < .85
                        or math.hypot(*_box_gap(block, label)) > 9 * scale):
                    continue
                if re.fullmatch(r"부터|제조(?:일자|일)?|생산(?:일자|일)?|MFG|MFD", label.text, re.I):
                    labels.append(("start", label))
                elif re.fullmatch(r"까지|EXP(?:IRY|IRES|DATE)?|USE\s*BY|BEST\s*(?:BEFORE|BY)", label.text, re.I):
                    labels.append(("end", label))
            if len(labels) != 2 or {kind for kind, _ in labels} != {"start", "end"}:
                continue
            rows = sorted(((i, first), (j, second)), key=lambda item: item[1].center[1])
            labels.sort(key=lambda item: item[1].center[1])
            row_step = rows[1][1].center[1] - rows[0][1].center[1]
            label_step = labels[1][1].center[1] - labels[0][1].center[1]
            if not .35 * row_step <= label_step <= 3 * row_step:
                continue
            if any(abs(row.center[1] - label.center[1]) > 2 * scale
                   for (_, row), (_, label) in zip(rows, labels)):
                continue
            # Inline roles contradicting the proposed block mean two different
            # labels/products; do not overwrite their explicit text.
            if any((kind == "start" and UNTIL_CONTEXT.search(row.text))
                   or (kind == "end" and FROM_CONTEXT.search(row.text))
                   for (_, row), (kind, _) in zip(rows, labels)):
                continue
            for (index, _), (kind, _) in zip(rows, labels):
                proposals.setdefault(index, set()).add(kind)
    return {i: next(iter(kinds)) for i, kinds in proposals.items() if len(kinds) == 1}


def _paired_orders(originals: Sequence[OCRLine], parsed: Sequence[list[ParsedDate]],
                   roles: dict[int, str]) -> dict[int, str]:
    """Use chronology only for a close, explicitly labelled, same-format pair.

    Identical field widths/separators on one printed block are the bounded
    same-order assumption. Unlabelled pairs, repaired digits, other frames,
    conflicting pairs and multiple possible orders supply no order evidence.
    """
    groups = []
    for index, (line, dates) in enumerate(zip(originals, parsed)):
        if line.score < .85 or not dates or any(d.repaired for d in dates):
            continue
        if len({(d.start, d.end) for d in dates}) != 1:
            continue
        raw = dates[0].raw
        if not re.fullmatch(r"\d{2,4}([./-])\d{2}\1\d{2,4}", raw):
            continue
        signature = re.sub(r"\d", "#", raw)
        candidate = _candidate_from_match(dates[0], line, originals, roles.get(index))
        groups.append((index, line, dates, signature, candidate))
    proposed: dict[int, set[str]] = {}
    for index, line, dates, signature, candidate in groups:
        for other_index, other, other_dates, other_signature, other_candidate in groups:
            if index >= other_index or signature != other_signature:
                continue
            if (line.source, line.variant) != (other.source, other.variant):
                continue
            horizontal, vertical = _box_gap(line, other)
            scale = max(line.height, other.height)
            if horizontal > scale or vertical > 3 * scale:
                continue
            start = candidate.explicit_negative
            end = other_candidate.explicit_positive
            reverse_start = other_candidate.explicit_negative
            reverse_end = candidate.explicit_positive
            if start and end and not reverse_start and not reverse_end:
                first, last = dates, other_dates
            elif reverse_start and reverse_end and not start and not end:
                first, last = other_dates, dates
            else:
                continue
            orders = {a.order for a in first for b in last if a.order == b.order and a.value < b.value}
            if len(orders) == 1:
                proposed.setdefault(index, set()).update(orders)
                proposed.setdefault(other_index, set()).update(orders)
    return {index: next(iter(orders)) for index, orders in proposed.items() if len(orders) == 1}


def _resolve_orders(
    line: OCRLine, matches: list[ParsedDate], originals: Sequence[OCRLine],
    parsed_originals: Sequence[list[ParsedDate]], product_rules: Sequence[ProductDateRule],
    paired_orders: dict[int, str],
) -> list[ParsedDate]:
    """Resolve a printed token before OCR scores rank different printed dates."""
    if not matches:
        return []
    groups: dict[tuple[int, int], list[ParsedDate]] = {}
    for match in matches:
        groups.setdefault((match.start, match.end), []).append(match)
    nearby = set()
    for hint_line, hint_dates in zip(originals, parsed_originals):
        if hint_dates or (hint_line.source, hint_line.variant) != (line.source, line.variant):
            continue
        hints = _format_hints(hint_line.text)
        if not hints or hint_line.score < 0.65:
            continue
        gap = math.hypot(*_box_gap(line, hint_line))
        # A separate legend belongs only to the nearest date line, not every date.
        rivals = [other for other, dates in zip(originals, parsed_originals)
                  if dates and (other.source, other.variant) == (line.source, line.variant)
                  and not set(other.members) & set(line.members)]
        explicit_reference = (not rivals and len(groups) == 1
                              and POSITIVE_CONTEXT.search(hint_line.text)
                              and re.search(r"별도\s*표기|후면\s*표기|상단\s*표기", hint_line.text))
        if gap > 3 * max(line.height, hint_line.height) and not explicit_reference:
            continue
        if any(math.hypot(*_box_gap(other, hint_line)) <= gap for other in rivals):
            continue
        nearby.update(order for _, _, order in hints)
    frame_text = " ".join(other.text.casefold() for other in originals
                          if (other.source, other.variant) == (line.source, line.variant)
                          and math.hypot(*_box_gap(line, other)) <= 8 * max(line.height, other.height))
    matching_rules = [rule for rule in product_rules
                      if all(token.casefold() in frame_text for token in rule.required_text)]
    result = []
    for values in groups.values():
        explicit = {v.order for v in values if v.order_reason == "explicit_order"}
        if explicit:
            result.extend(values)
            continue
        if nearby:
            if len(nearby) == 1:
                result.extend(replace(v, order_reason="explicit_order") for v in values if v.order in nearby)
            continue
        if len({v.value for v in values}) == 1:
            result.append(values[0])
            continue
        # A nearby fully written expiry can disambiguate the SAME date value.
        counterparts = {v.value for other, dates in zip(originals, parsed_originals)
                        if (other.source, other.variant) == (line.source, line.variant)
                        and not set(other.members) & set(line.members)
                        and math.hypot(*_box_gap(line, other)) <= 5 * max(line.height, other.height)
                        and POSITIVE_CONTEXT.search(other.text) and not NEGATIVE_CONTEXT.search(other.text)
                        for v in dates if v.order_reason == "explicit_order" or v.separator == "month-name"}
        corresponding = [v for v in values if v.value in counterparts]
        if len({v.value for v in corresponding}) == 1:
            result.append(replace(corresponding[0], order_reason="corresponding_date"))
            continue
        pair = {paired_orders[index] for index in line.members if index in paired_orders}
        if len(pair) == 1:
            result.extend(replace(v, order_reason="labelled_date_pair") for v in values if v.order in pair)
            continue
        orders = {rule.order for rule in matching_rules}
        if orders:
            if len(orders) == 1:
                result.extend(replace(v, order_reason="product_rule:" + matching_rules[0].name)
                              for v in values if v.order in orders)
            continue
        dmy = next((v for v in values if v.order == "dmy"), None)
        if dmy:
            result.append(replace(dmy, order_reason="fallback_dmy"))
    return result


def extract_candidates(lines: Sequence[OCRLine], *, product_rules: Sequence[ProductDateRule] = ()) -> list[DateCandidate]:
    originals = [
        replace(line, text=_normalise_text(line.text), members=line.members or (index,))
        for index, line in enumerate(lines)
    ]
    search_lines = originals + merge_horizontal_lines(originals)
    parsed_originals = [parse_dates(line.text) for line in originals]
    roles = _printed_pair_roles(originals, parsed_originals)
    paired_orders = _paired_orders(originals, parsed_originals, roles)
    candidates: list[DateCandidate] = []
    for index, line in enumerate(search_lines):
        matches = parsed_originals[index] if index < len(originals) else parse_dates(line.text)
        member_roles = {roles[member] for member in line.members if member in roles}
        role = next(iter(member_roles)) if len(member_roles) == 1 else None
        for match in _resolve_orders(line, matches, originals, parsed_originals, product_rules, paired_orders):
            candidates.append(_candidate_from_match(match, line, originals, role))
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
    ranked_scores = {item.iso: item.score for item in ranked}
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
            # Alternative parses of overlapping digits are not two printed dates.
            if first.members == last.members and max(first.span[0], last.span[0]) < min(first.span[1], last.span[1]):
                continue
            paired_roles = (first.explicit_negative or _nearer_role(first, last, lines, FROM_CONTEXT)) and not last.explicit_negative
            explicit_end = (last.explicit_positive or _nearer_role(last, first, lines, UNTIL_CONTEXT)) and not last.explicit_negative
            equal_unlabelled = (
                not first.positive_hits and not first.negative_hits
                and not last.positive_hits and not last.negative_hits
                and abs(first.score - last.score) <= 0.15
                and min(first.ocr_score, last.ocr_score) >= 0.65
            )
            if (paired_roles or explicit_end or equal_unlabelled) and ranked_scores[last.iso] >= ranked[0].score - (2.60 if paired_roles or explicit_end else 0.15):
                endpoints.add(last.iso)
    choices = [item for item in ranked if item.iso in endpoints]
    return max(choices, key=lambda item: (item.score, item.value), default=None)


def _select_full_date(lines: Sequence[OCRLine], *, final: bool = False, product_rules: Sequence[ProductDateRule] = ()) -> DateSelection:
    candidates = extract_candidates(lines, product_rules=product_rules)
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
            best.explicit_negative and not has_positive and best.ocr_score >= 0.70
        )
        return DateSelection(
            None,
            best.score,
            margin,
            explicit_manufacturing,
            "negative-context" if explicit_manufacturing else "score-below-threshold",
            tuple(ranked),
            digits_confident=best.ocr_score >= .85 and not best.repaired,
            order_resolved=best.order_reason != "fallback_dmy",
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
    if (len(ranked) == 1 and best.ocr_score >= 0.85 and not best.repaired and not has_negative
            and (best.order_reason in {"explicit_order", "corresponding_date", "calendar_unique"}
                 or best.order_reason.startswith("product_rule:"))):
        confident = True
    reason = "accepted" if confident else "ambiguous"
    if best.order_reason == "fallback_dmy":
        # Clear digits with only order uncertainty must not trigger more OCR.
        if not final:
            confident = ((confident or len(ranked) == 1) and best.ocr_score >= 0.85
                         and not best.repaired and not has_negative)
        reason = "fallback_dmy" if confident else "low-confidence-digits"
    return DateSelection(best.iso, best.score, margin, confident, reason, tuple(ranked),
                         digits_confident=best.ocr_score >= .85 and not best.repaired,
                         order_resolved=best.order_reason != "fallback_dmy")


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


def select_date(lines: Sequence[OCRLine], *, final: bool = False, product_rules: Sequence[ProductDateRule] = ()) -> DateSelection:
    full = _select_full_date(lines, final=final, product_rules=product_rules)
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
