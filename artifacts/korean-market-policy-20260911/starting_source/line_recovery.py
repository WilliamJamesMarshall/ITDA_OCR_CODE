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

from .date_extraction import OCRLine, _link_roles, _printed_month_day_token, parse_dates


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
    partial = _printed_month_day_token(text)
    if partial:
        return ((f'NONE-{int(partial[1]):02d}-{int(partial[2]):02d}', 'printed-month-day'),)
    parsed = parse_dates(text)
    if not parsed or any(p.repaired for p in parsed) or len({(p.start, p.end) for p in parsed}) != 1:
        return None
    return tuple(sorted((p.value.isoformat(), p.order) for p in parsed))


def _digit_evidence(text, scores):
    partial = _printed_month_day_token(text)
    if partial and len(scores) == len(text):
        values = [scores[i] for group in (1,2) for i in range(partial.start(group),partial.end(group))]
        return sum(values)/len(values), min(values)
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


def _apply_views(active, lines, linked, jobs, observations, *, strict=False):
    decisions = []
    for index in sorted({job[0] for job in jobs}):
        evidence = [obs for obs, job in zip(observations, jobs) if job[0] == index]
        def eligible(obs):
            return (_stable(obs) and (not strict or
                    (obs.date_digit_score is not None and obs.date_digit_score >= .95
                     and obs.date_digit_min_score >= .8)))
        votes = Counter(_signature(obs.text) for obs in evidence if eligible(obs) and _signature(obs.text))
        accepted = None
        if votes:
            signature, count = votes.most_common(1)[0]
            if count >= 2 and len(votes) == 1 and signature != _signature(lines[index].text):
                supporters = [obs for obs in evidence if eligible(obs) and _signature(obs.text) == signature]
                best = max(supporters, key=lambda obs: obs.score)
                # Multiple views of one region are not independent selector votes.
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
                              role_basis=linked[index].role_basis, recognizer='english' if strict else 'primary',
                              accepted_text=accepted, reason='same-model-view-stability' if accepted else 'keep-original'))
    return decisions


def recover_lines(image, lines, recognize_crops, fallback_recognize=None):
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
    decisions = _apply_views(active, lines, linked, jobs, observations)
    # A second recognizer may recover a still-unparsed/repaired token, never
    # override a successful primary recovery or a clear complete original date.
    pending = {d['line_index'] for d in decisions if not d['accepted_text']
               and not _signature(lines[d['line_index']].text)}
    if fallback_recognize is not None and pending:
        positions = [i for i, job in enumerate(jobs) if job[0] in pending]
        started = time.perf_counter()
        try:
            results = fallback_recognize([crops[i] for i in positions])
            if len(results) != len(positions):
                raise ValueError('Secondary recognition count does not match requested crops')
            extra = []
            for position, result in zip(positions, results):
                chars = tuple(result[2]) if len(result) > 2 else ()
                mean, minimum = _digit_evidence(result[0], chars)
                extra.append(replace(observations[position], text=result[0], score=result[1],
                                     variant=observations[position].variant+'-english', character_scores=chars,
                                     date_digit_score=mean, date_digit_min_score=minimum))
            decisions.extend(_apply_views(active, lines, linked, [jobs[i] for i in positions], extra, strict=True))
            observations.extend(extra)
        except Exception as exc:
            decisions.append(dict(line_index=-1, original_text='', original_box=None, accepted_text=None,
                                  reason='secondary-recognition-error', error=f'{type(exc).__name__}: {exc}'))
        seconds += time.perf_counter()-started
    return active, observations, decisions, seconds


def _flat_label_rows(image, label, *, masked=False):
    """Pixel rows in a bright panel left of one expiry label, in original coordinates.

    This is a narrow missing-detector fallback, not a general text detector.
    Long, shallow dark rows are eligible; more than two rows is ambiguous.
    """
    height, width = image.shape[:2]
    x1, y1, x2, y2 = label.box
    h = y2-y1
    left, top = max(0, int(x1-12*h)), max(0, int(y1-2*h))
    right, bottom = min(width, int(x1)), min(height, int(y2+h))
    if h < 8 or right-left < 8 or bottom-top < 8:
        return []
    gray = cv2.cvtColor(image[top:bottom,left:right], cv2.COLOR_BGR2GRAY)
    contours, _ = cv2.findContours(cv2.inRange(gray,170,255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    panels = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) > 1.5*h*h]
    if not panels:
        return []
    px, py, pw, ph = max(panels,key=lambda b:b[2]*b[3])
    inset = max(2,round(h*.14))
    if pw <= 2*inset or ph <= 2*inset:
        return []
    panel_mask = None
    if masked:
        import numpy as np
        contour = max((c for c in contours if cv2.contourArea(c) > 1.5*h*h),
                      key=lambda c: math.prod(cv2.boundingRect(c)[2:]))
        panel_mask = np.zeros_like(gray)
        cv2.drawContours(panel_mask,[contour],-1,255,-1)
        panel_mask = cv2.erode(panel_mask,cv2.getStructuringElement(cv2.MORPH_RECT,(2*inset+1,2*inset+1)))
        panel_mask = panel_mask[py+inset:py+ph-inset,px+inset:px+pw-inset]
    gray = gray[py+inset:py+ph-inset,px+inset:px+pw-inset]
    left += px+inset; top += py+inset
    binary = cv2.inRange(gray,0,120)
    if masked:
        binary = cv2.bitwise_and(binary,panel_mask)
        joined = cv2.morphologyEx(binary,cv2.MORPH_CLOSE,
                                 cv2.getStructuringElement(cv2.MORPH_RECT,(max(3,round(h*1.5)),1)))
        ys = np.flatnonzero(np.count_nonzero(joined,axis=1) >= 2*h)
        if not len(ys):
            return []
        rows = []
        # Dot gaps scale with the printed label, not fixed input pixels.
        gap_limit = max(2,round(h*.06))
        for run in np.split(ys,np.flatnonzero(np.diff(ys)>gap_limit+1)+1):
            a,b = int(run[0]),int(run[-1])+1
            xs = np.flatnonzero(np.any(binary[a:b],axis=0))
            if not len(xs):
                continue
            x,w,rh = int(xs[0]),int(xs[-1]-xs[0]+1),b-a
            if w >= 2*h and 8 <= rh <= 1.4*h and w/rh >= 4:
                rows.append((left+x,top+a,left+x+w,top+b))
        return rows if 1 <= len(rows) <= 2 else []
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT,(max(3,round(h*1.5)),3))
    joined = cv2.morphologyEx(binary,cv2.MORPH_CLOSE,kernel)
    contours, _ = cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    rows = []
    for contour in contours:
        x,y,w,rh = cv2.boundingRect(contour)
        if w >= 2*h and 8 <= rh <= 1.4*h and w/rh >= 8:
            rows.append((left+x,top+y,left+x+w,top+y+rh))
    return sorted(rows,key=lambda b:b[1]) if 1 <= len(rows) <= 2 else []


def recover_missing_rows(image, lines, recognize_crops, fallback_recognize=None):
    """At most two batches of four crops, two stable views per new row.

    Date digits must be supported by aligned character probabilities. No digit
    rewriting, date-order override, or model-agreement confidence bonus.
    """
    labels = [line for line in lines if line.geometry_valid and line.score >= .9
              and line.box[2]-line.box[0] >= line.height
              and re.fullmatch(r'까지|EXP|BBD|소비기한|유통기한',line.text.strip(),re.I)]
    if len(labels) != 1 or any(parse_dates(line.text) for line in lines):
        return [], [], [], 0.
    label = labels[0]
    boxes = _flat_label_rows(image,label)
    primary = _recover_missing_boxes(image,lines,label,boxes,recognize_crops)
    if primary[0] or fallback_recognize is None:
        return primary
    boxes = _flat_label_rows(image,label,masked=True)
    secondary = _recover_missing_boxes(image,lines,label,boxes,fallback_recognize,secondary=True,
                                       index_offset=len(primary[2]))
    return secondary[0],primary[1]+secondary[1],primary[2]+secondary[2],primary[3]+secondary[3]


def _recover_missing_boxes(image,lines,label,boxes,recognize_crops,*,secondary=False,index_offset=0):
    jobs, crops = [], []
    height,width = image.shape[:2]
    for index, (x1,y1,x2,y2) in enumerate(boxes):
        pad = max(3,round((y2-y1)*.3))
        bounds = (max(0,x1-pad),max(0,y1-pad),min(width,x2+pad),min(height,y2+pad))
        a,b,c,d = bounds
        ratio = (x2-x1)/(y2-y1)
        scales = (min(1.,4.8/ratio),min(1.08,5.2/ratio)) if secondary else (.4,.45)
        for scale in scales:
            crops.append(cv2.resize(image[b:d,a:c],None,fx=scale,fy=1,interpolation=cv2.INTER_AREA))
            jobs.append((index,scale,bounds))
    if not crops:
        return [], [], [], 0.
    started = time.perf_counter()
    results = recognize_crops(crops)
    seconds = time.perf_counter()-started
    if len(results) != len(jobs):
        raise ValueError('Missing-row recognition count does not match requested crops')
    observations = []
    for (index,scale,bounds), result in zip(jobs,results):
        text,score = result[:2]
        chars = tuple(result[2]) if len(result)>2 else ()
        mean,minimum = _digit_evidence(text,chars)
        observations.append(OCRLine(text,score,bounds,source=label.source,
                                    variant=f'line-{len(lines)+index_offset+index}-flat-{scale}'+('-english' if secondary else ''),original_box=bounds,
                                    character_scores=chars,date_digit_score=mean,date_digit_min_score=minimum))
    accepted, decisions = [], []
    for index, box in enumerate(boxes):
        views = observations[2*index:2*index+2]
        signatures = [_signature(view.text) for view in views]
        stable = (all(signatures) and signatures[0] == signatures[1]
                  and all(view.score >= .85 and view.date_digit_score is not None
                          and view.date_digit_score >= (.95 if secondary else .9)
                          and view.date_digit_min_score >= (.8 if secondary else .7) for view in views))
        best = max(views,key=lambda view:view.score)
        if stable:
            accepted.append(replace(best,score=min(view.score for view in views),box=box,original_box=box,
                                    variant=label.variant,date_digit_score=min(view.date_digit_score for view in views),
                                    date_digit_min_score=min(view.date_digit_min_score for view in views)))
        decisions.append(dict(line_index=len(lines)+index_offset+index,original_text='',original_box=box,
                              recognizer='english' if secondary else 'primary',
                              accepted_text=best.text if stable else None,
                              reason='flat-row-view-stability' if stable else 'unstable-flat-row'))
    # Do not expose only the manufacturing row or a half-read pair to selection.
    if len(accepted) != len(boxes):
        for decision in decisions:
            decision.update(accepted_text=None,reason='incomplete-flat-row-block')
        accepted = []
    return accepted, observations, decisions, seconds
