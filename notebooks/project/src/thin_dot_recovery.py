"""Recover disconnected print without merging the neighboring clock/lot row."""
from dataclasses import replace
import time
import cv2
import numpy as np
from .date_extraction import OCRLine, _inline_role
from .date_region_recovery import dot_row_proposals, rectified_crop
from .line_recovery import _apply_views, _digit_evidence, _signature, _supported_role


def thin_views(image, polygon, *, natural=False):
    crop = rectified_crop(image, polygon, .15 if natural else .35)
    if crop is None:
        return []
    h, w = crop.shape[:2]
    crop = cv2.resize(crop, (round(w*96/h), 96))
    plain = crop if natural else cv2.resize(crop, (624, 96))
    joined = cv2.morphologyEx(plain, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    if np.array_equal(plain, joined):
        return []
    return [('thin-plain', plain), ('thin-joined', joined)]


def recover_thin_dots(image, lines, primary, english=None, *, natural=False):
    started = time.perf_counter()
    anchors, jobs, crops = [], [], []
    # Fixed density ranking, not OCR answers; at most six physical rows.
    options = dict(limit=6, thin=True)
    if natural:
        options['contrast'] = 8
    stage = 'natural-dot-rows' if natural else 'thin-dot-rows'
    for polygon in dot_row_proposals(image, **options):
        views = thin_views(image, polygon, natural=natural)
        if len(views) != 2:
            continue
        xs, ys = zip(*polygon)
        box = (min(xs), min(ys), max(xs), max(ys))
        index = len(anchors)
        anchors.append(OCRLine('', 0., box, source='paddle-thin-dot', variant=stage,
                               original_box=box, polygon=polygon))
        for name, crop in views:
            jobs.append((index, name, box)); crops.append(crop)
    observations, decisions, choices = [], [], {}
    for name, recognize in [('primary', primary), ('english', english)]:
        if recognize is None or not crops:
            continue
        results = recognize(crops)
        if len(results) != len(jobs):
            raise ValueError('Thin-dot recognition result count mismatch')
        extra = []
        for (index, variant, _), result in zip(jobs, results):
            chars = tuple(result[2]) if len(result)>2 else ()
            mean, minimum = _digit_evidence(result[0], chars)
            extra.append(replace(anchors[index], text=result[0], score=result[1],
                                 variant=variant+'-'+name, character_scores=chars,
                                 date_digit_score=mean, date_digit_min_score=minimum))
        active = list(anchors)
        audit = _apply_views(active, anchors, anchors, jobs, extra, strict=True)
        for decision in audit:
            index = decision['line_index']
            views = extra[2*index:2*index+2]
            roles = [_inline_role(v.text) for v in views]
            if any(roles) and (len(set(roles)) != 1 or any(_supported_role(v) != roles[0] for v in views)):
                decision.update(accepted_text=None, decision_basis='unsupported-role-glyphs')
            if decision['accepted_text']:
                choices.setdefault(index, []).append(active[index])
            decision.update(stage=stage, recognizer=name, line_index=len(lines)+index)
        observations.extend(extra); decisions.extend(audit)
    accepted = []
    for index, values in choices.items():
        if len({_signature(v.text) for v in values}) > 1:
            for d in decisions:
                if d['line_index'] == len(lines)+index:
                    d.update(accepted_text=None, decision_basis='cross-recognizer-conflict')
            continue
        accepted.append(max(values, key=lambda v:v.score))
    discarded = set()
    for i, first in enumerate(accepted):
        for j, second in enumerate(accepted[:i]):
            a, b = first.box, second.box
            intersection = max(0., min(a[2],b[2])-max(a[0],b[0])) * max(0., min(a[3],b[3])-max(a[1],b[1]))
            if intersection / min(first.width*first.height, second.width*second.height) < .7:
                continue
            if _signature(first.text) != _signature(second.text):
                discarded.update((i,j))
            else:
                discarded.add(i if first.score <= second.score else j)
    kept = [v for i,v in enumerate(accepted) if i not in discarded]
    for d in decisions:
        if d.get('accepted_text') and not any(v.box == d['original_box'] and v.text == d['accepted_text'] for v in kept):
            d.update(accepted_text=None, decision_basis='overlapping-row-conflict-or-duplicate')
    return kept, observations, decisions, time.perf_counter()-started
