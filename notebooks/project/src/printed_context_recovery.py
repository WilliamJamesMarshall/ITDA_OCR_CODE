"""Bounded dot-stroke recovery on automatic full-image regions only."""
from dataclasses import replace
import time
import cv2
import numpy as np
from .date_extraction import OCRLine, _inline_role
from .date_region_recovery import numeric_region_proposals, rectified_crop
from .line_recovery import _apply_views, _digit_evidence, _supported_role


def stroke_views(image, polygon):
    crop = rectified_crop(image, polygon, .1)
    if crop is None:
        return []
    h, w = crop.shape[:2]
    crop = cv2.resize(crop, (round(w*96/h), 96))
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # Join separated dark dots at a fixed glyph scale, not in original pixels.
    joined = cv2.morphologyEx(gray, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    return [(f'stroke-{ratio}', cv2.cvtColor(cv2.resize(joined, (round(96*ratio),96)),
                                          cv2.COLOR_GRAY2BGR)) for ratio in (4.8,6.5)]


def recover_printed_context(image, lines, recognize_crops):
    started = time.perf_counter()
    # ROI/rotated local polygons cannot be applied to the original image.
    eligible = [line for line in lines if line.variant in ('original','clahe','geometric-rows')]
    polygons = numeric_region_proposals(image, eligible)
    anchors, crops, jobs, seen = [], [], [], set()
    for polygon in polygons:
        key = tuple(round(v) for p in polygon for v in p)
        if key in seen:
            continue
        seen.add(key)
        views = stroke_views(image, polygon)
        if len(views) != 2 or np.array_equal(views[0][1],views[1][1]):
            continue
        xs, ys = zip(*polygon)
        box = (min(xs), min(ys), max(xs), max(ys))
        index = len(anchors)
        anchors.append(OCRLine('',0.,box,source='paddle-stroke',variant='stroke-rows',
                               original_box=box,polygon=polygon))
        for name,crop in views:
            crops.append(crop); jobs.append((index,name,box))
    if not crops:
        return [], [], [], time.perf_counter()-started
    results = recognize_crops(crops)
    if len(results) != len(jobs):
        raise ValueError('Stroke recognition result count mismatch')
    observations = []
    for (index,name,_), result in zip(jobs,results):
        chars = tuple(result[2]) if len(result)>2 else ()
        mean, minimum = _digit_evidence(result[0],chars)
        observations.append(replace(anchors[index],text=result[0],score=result[1],variant=name,
                                    character_scores=chars,date_digit_score=mean,date_digit_min_score=minimum))
    active = list(anchors)
    decisions = _apply_views(active,anchors,anchors,jobs,observations,strict=True)
    added = []
    for decision in decisions:
        index = decision['line_index']
        views = observations[2*index:2*index+2]
        roles = [_inline_role(view.text) for view in views]
        if any(roles) and (len(set(roles)) != 1 or any(_supported_role(v) != roles[0] for v in views)):
            decision.update(accepted_text=None,decision_basis='unsupported-role-glyphs')
        if decision['accepted_text']:
            added.append(active[index])
        decision.update(stage='printed-stroke-context',recognizer='primary',line_index=len(lines)+index)
    return added, observations, decisions, time.perf_counter()-started
