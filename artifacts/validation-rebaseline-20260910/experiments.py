"""Predefined validation-only ablations. No image IDs, labels or annotations used.

p1: historical years and partial date output.
p2: p1 plus explicit date order and missing textual date formats.
p3: p2 plus coordinate-frame isolation and local date-role selection.
"""
import math
import re
from dataclasses import replace
from datetime import date
from collections import defaultdict
from src import date_extraction as d

ORIGINAL_PARSE = d.parse_dates
ORIGINAL_NUMERIC = d._iter_numeric_dates
ORIGINAL_MONTH = d._iter_month_name_dates
ORIGINAL_MERGE = d.merge_horizontal_lines
ORIGINAL_SELECT = d.select_date


def numeric_dates(text, repaired):
    explicit = None
    if re.search(r'MM\s*[/.-]\s*DD\s*[/.-]\s*(?:YY|YYYY)|월\s*[/.-]\s*일\s*[/.-]\s*년', text, re.I):
        explicit = 'mdy'
    elif re.search(r'DD\s*[/.-]\s*MM\s*[/.-]\s*(?:YY|YYYY)|일\s*[/.-]\s*월\s*[/.-]\s*년', text, re.I):
        explicit = 'dmy'
    elif re.search(r'(?:YY|YYYY)\s*[/.-]\s*MM\s*[/.-]\s*DD', text, re.I):
        explicit = 'ymd'
    added = []
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(20\d{2}|\d{2})(?!\d)', text):
        a, b, c = map(int, m.groups())
        if explicit:
            order = explicit
        elif b > 12 and a <= 12:
            order = 'mdy'
        elif len(m.group(3)) == 4:
            order = 'dmy'
        elif a > 12 and b <= 12 and c > 31:
            order = 'dmy'
        else:
            continue  # Unresolved YY-MM-DD vs DD-MM-YY retains existing policy.
        parsed = d._emit_match(m, order, len(m.group(3)) if order != 'ymd' else len(m.group(1)), 'separated', repaired)
        if parsed:
            added.append(parsed)
    for item in ORIGINAL_NUMERIC(text, repaired):
        if not any(a.start == item.start and a.end == item.end for a in added):
            yield item
    yield from added


def month_dates(text, repaired):
    yield from ORIGINAL_MONTH(text, repaired)
    mon = '|'.join(d.MONTHS)
    for m in re.finditer(rf'(?<!\d)(20\d{{2}})\s*[./-]?\s*({mon})\s*[./-]?\s*(\d{{1,2}})(?!\d)', text, re.I):
        value = d._valid_date(int(m[1]), d.MONTHS[m[2].upper()], int(m[3]))
        if value:
            yield d.ParsedDate(value, m[0], m.start(), m.end(), 4, 'month-name', repaired)


def ordered_parse(text):
    # Preserve Korean order hints before the original normalizer removes 년/월/일.
    text = re.sub(r'월\s*[/.-]\s*일\s*[/.-]\s*년', 'MM/DD/YYYY', text)
    text = re.sub(r'일\s*[/.-]\s*월\s*[/.-]\s*년', 'DD/MM/YYYY', text)
    return ORIGINAL_PARSE(text)


def framed_merge(lines):
    groups = defaultdict(list)
    for i, line in enumerate(lines):
        groups[(line.source, line.variant)].append((i, line))
    output = []
    for group in groups.values():
        for line in ORIGINAL_MERGE([x[1] for x in group]):
            output.append(replace(line, members=tuple(group[i][0] for i in line.members)))
    return output


def local_context(line, originals):
    positives, negatives, pa, na = [], [], 0., 0.
    for i, other in enumerate(originals):
        if i in line.members or (line.source, line.variant) != (other.source, other.variant):
            continue
        horizontal, vertical = d._box_gap(line, other)
        scale = max(12., line.height, other.height)
        row = abs(line.center[1]-other.center[1]) <= .9*scale and horizontal <= 9*scale
        close = math.hypot(horizontal, vertical) <= 5*scale
        if not (row or close):
            continue
        pos, neg = d.POSITIVE_CONTEXT.search(other.text), d.NEGATIVE_CONTEXT.search(other.text)
        if pos:
            positives.append(pos[0])
            pa = max(pa, (1.35 if d.UNTIL_CONTEXT.search(pos[0]) else .95) if row else .30)
        if neg:
            negatives.append(neg[0])
            na = max(na, (.75 if d.FROM_CONTEXT.search(neg[0]) else .55) if row else .12)
    return positives, negatives, pa-na


def local_select(lines, *, final=False):
    groups = defaultdict(list)
    for c in d.extract_candidates(lines):
        groups[c.iso].append(c)
    ranked = []
    for cs in groups.values():
        best = max(cs, key=lambda c:c.score)
        bonus = min(.60, .22*(len({(c.source,c.variant) for c in cs})-1))
        ranked.append(replace(best, score=best.score+bonus))
    ranked.sort(key=lambda c:(c.score,c.value), reverse=True)
    if not ranked:
        return d.DateSelection(None, -math.inf, math.inf, False, 'no-valid-date', ())
    best = ranked[0]
    margin = best.score-ranked[1].score if len(ranked)>1 else math.inf
    pos, neg = bool(best.positive_hits), bool(best.negative_hits)
    if best.score < 1.05:
        negative = neg and not pos and best.ocr_score >= .70
        return d.DateSelection(None,best.score,margin,negative,'negative-context' if negative else 'score-below-threshold',tuple(ranked))
    allowed = not neg or (len(ranked)==1 and best.score>=3.)
    confident = (pos and best.score>=2.15 and margin>=.35 and allowed) or (len(ranked)==1 and best.score>=1.65 and best.ocr_score>=.65 and not best.repaired and not neg) or (best.score>=2.35 and margin>=.65 and allowed)
    # No global 'latest date within 550 days' override without a matched interval.
    return d.DateSelection(best.iso,best.score,margin,confident or final,'accepted' if confident or final else 'ambiguous',tuple(ranked))


def partial_candidates(lines):
    mon = '|'.join(d.MONTHS)
    for index, line in enumerate(lines):
        text = d._normalise_text(line.text)
        if d.parse_dates(text):
            continue
        matches = []
        for m in re.finditer(r'(?<![\d./-])(20\d{2})\s*[년./-]\s*(\d{1,2})(?:월)?(?!\d|\s*[./-]\s*\d)', text):
            if 1 <= int(m[2]) <= 12:
                matches.append((m, f'{int(m[1]):04d}-{int(m[2]):02d}-NONE'))
        for m in re.finditer(rf'(?<!\w)({mon})\s*[./-]?\s*(20\d{{2}})(?!\d)', text, re.I):
            matches.append((m, f'{int(m[2]):04d}-{d.MONTHS[m[1].upper()]:02d}-NONE'))
        for m in re.finditer(r'(?<![\d./-])(\d{1,2})\s*[월./-]\s*(\d{1,2})(?:일)?(?!\d|\s*[./-]\s*\d)', text):
            if re.search(r'\d\s*[./-]\s*$', text[:m.start()]) or any(x[0].start()<=m.start()<x[0].end() for x in matches):
                continue
            try:
                date(2000, int(m[1]), int(m[2]))  # Calendar validity only; output year remains NONE.
            except ValueError:
                continue
            matches.append((m, f'NONE-{int(m[1]):02d}-{int(m[2]):02d}'))
        for m, value in matches:
            local = text[max(0,m.start()-20):m.end()+20]
            pos = bool(d.POSITIVE_CONTEXT.search(local))
            neg = bool(d.NEGATIVE_CONTEXT.search(local))
            nearpos, nearneg, adjustment = d._nearby_context(replace(line,members=(index,)), lines)
            score = 1.45*line.score + (.15 if value.startswith('NONE') else .30) + (1.45 if pos else 0) - (1.90 if neg else 0) + adjustment
            if re.search(r'\d\s*[~～]\s*\d|보관|온도|℃|kg|mg|g\b|cm|%', local, re.I) and not pos:
                continue
            if neg and not pos:
                continue
            if score >= 1.35:
                yield value, score, line.score, pos or bool(nearpos)


def install(stage, pipeline):
    assert stage in ('p1', 'p2', 'p3')
    d.MIN_YEAR, d.MAX_YEAR = 2000, 2099
    if stage in ('p2','p3'):
        d._iter_numeric_dates = numeric_dates
        d._iter_month_name_dates = month_dates
        d.parse_dates = ordered_parse
    if stage == 'p3':
        d.merge_horizontal_lines = framed_merge
        d._nearby_context = local_context
    full_selector = local_select if stage == 'p3' else ORIGINAL_SELECT
    def select(lines, *, final=False):
        full = full_selector(lines, final=final)
        if full.final_date is not None:
            return full
        partials = sorted(partial_candidates(lines), key=lambda x:x[1], reverse=True)
        if not partials:
            return full
        value, score, ocr, context = partials[0]
        margin = score - next((x[1] for x in partials if x[0]!=value), -math.inf)
        confident = context and score >= 2.15 and margin >= .35 and ocr >= .65
        return d.DateSelection(value, score, margin, confident or final, 'partial-date', ())
    d.select_date = pipeline.select_date = select
    def fields(value):
        if value is None or value == 'NONE':
            return {'year':'NONE','month':'NONE','day':'NONE','final_date':'NONE'}
        year, month, day = value.split('-')
        return {'year':year,'month':month,'day':day,'final_date':value}
    d.submission_fields = pipeline.submission_fields = fields
