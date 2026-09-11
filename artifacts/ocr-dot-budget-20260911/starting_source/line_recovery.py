"""Bounded re-recognition of existing date boxes; no detector or digit rewriting.

Agreement between views of one recognizer is a stability check, NOT independent
evidence or calibrated confidence. Original and rejected observations are logged.
"""
from collections import Counter
from dataclasses import replace
import math
import re
import time

import cv2

from .date_extraction import _link_roles, parse_dates


def recovery_targets(lines):
    targets = []
    for index, line in enumerate(lines):
        text = line.text.strip()
        digits = sum(c.isdigit() for c in text)
        if (not line.geometry_valid or len(text) > 40 or digits < 3
                or digits / max(1, len(text)) < .25
                or re.search(r'%|kcal|mg|ml|brix|영양|전화|고객|품목|인증|허가|등록|\b(?:TEL|LOT)\b', text, re.I)
                or re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', text)):
            continue
        if not (parse_dates(text) or sum(text.count(s) for s in './-') >= 2
                or (digits >= 4 and any(s in text for s in './-'))):
            continue
        targets.append(index)
    return targets[:2]


def _signature(text):
    parsed = parse_dates(text)
    if not parsed or any(p.repaired for p in parsed) or len({(p.start, p.end) for p in parsed}) != 1:
        return None
    return tuple(sorted((p.value.isoformat(), p.order) for p in parsed))


def _digit_evidence(text, scores):
    parsed = parse_dates(text)
    if len(scores) != len(text) or not _signature(text):
        return None, None
    token = parsed[0]
    if text[token.start:token.end] != token.raw:
        return None, None
    values = [scores[i] for i in range(token.start,token.end) if text[i].isdigit()]
    return (sum(values)/len(values), min(values)) if values else (None, None)


def _stable(obs):
    if obs.date_digit_min_score is not None and obs.date_digit_min_score < .5:
        return False
    return obs.score >= .85 or (obs.score >= .65 and obs.date_digit_score is not None and obs.date_digit_score >= .90)


def recover_lines(image, lines, recognize_crops):
    """Return active lines, raw view observations, and decisions for audit."""
    active = list(lines)
    linked = _link_roles(lines)
    observations, decisions, jobs, crops = [], [], [], []
    height, width = image.shape[:2]
    for index in recovery_targets(lines):
        line = lines[index]
        if not all(math.isfinite(v) for v in line.box):
            continue
        pad = min(12, max(4, round(line.height*.08)))
        for view, margin, enhance in [('contrast', 0, True), ('padded', pad, False), ('padded-contrast', pad, True)]:
            left, top, right, bottom = line.box
            bounds = (max(0, int(left)-margin), max(0, int(top)-margin),
                      min(width, math.ceil(right)+margin), min(height, math.ceil(bottom)+margin))
            x1, y1, x2, y2 = bounds
            if x2-x1 < 8 or y2-y1 < 8:
                continue
            crop = image[y1:y2, x1:x2]
            if enhance:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                crop = cv2.cvtColor(cv2.createCLAHE(clipLimit=2., tileGridSize=(4,4)).apply(gray), cv2.COLOR_GRAY2BGR)
            crops.append(crop)
            jobs.append((index, view, bounds))
    if not crops:
        return active, observations, decisions, 0.
    started = time.perf_counter()
    results = recognize_crops(crops)
    seconds = time.perf_counter()-started
    if len(results) != len(jobs):
        raise ValueError('Recognition-only result count does not match requested crops')
    for (index, view, bounds), result in zip(jobs, results):
        text, score = result[:2]
        character_scores = tuple(result[2]) if len(result) > 2 else ()
        mean_digit, min_digit = _digit_evidence(text,character_scores)
        observations.append(replace(lines[index], text=text, score=score, box=bounds,
                                    polygon=(), variant=f'line-{index}-{view}', members=(),
                                    character_scores=character_scores, date_digit_score=mean_digit,
                                    date_digit_min_score=min_digit))
    for index in sorted({job[0] for job in jobs}):
        evidence = [obs for obs, job in zip(observations, jobs) if job[0] == index]
        votes = Counter(_signature(obs.text) for obs in evidence if _stable(obs) and _signature(obs.text))
        accepted = None
        if votes:
            signature, count = votes.most_common(1)[0]
            if count >= 2 and len(votes) == 1 and signature != _signature(lines[index].text):
                supporters = [obs for obs in evidence if _stable(obs) and _signature(obs.text) == signature]
                best = max(supporters, key=lambda obs: obs.score)
                # Keep the original frame and semantic anchor; do not count
                # augmented views as extra independent selector votes.
                active[index] = replace(linked[index], text=best.text, score=min(obs.score for obs in supporters),
                                        role_basis='recovery_anchor' if linked[index].role else None,
                                        character_scores=best.character_scores,
                                        date_digit_score=min(obs.date_digit_score for obs in supporters)
                                        if all(obs.date_digit_score is not None for obs in supporters) else None,
                                        date_digit_min_score=min(obs.date_digit_min_score for obs in supporters)
                                        if all(obs.date_digit_min_score is not None for obs in supporters) else None)
                accepted = best.text
        decisions.append(dict(line_index=index, original_text=lines[index].text,
                              original_box=lines[index].original_box, role=linked[index].role,
                              role_basis=linked[index].role_basis,
                              accepted_text=accepted, reason='same-model-view-stability' if accepted else 'keep-original'))
    return active, observations, decisions, seconds
