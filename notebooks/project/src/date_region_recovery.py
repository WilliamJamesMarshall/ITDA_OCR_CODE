"""Bounded pixel-based proposals for missed dot-matrix rows; no labels/IDs."""
import math
import re
import time
from dataclasses import replace
import cv2
import numpy as np


def rectified_crop(image, polygon, padding=0.):
    points=np.asarray(polygon,dtype=np.float32)
    if points.shape!=(4,2) or not np.isfinite(points).all():return None
    if not cv2.isContourConvex(points) or abs(cv2.contourArea(points))<64:return None
    width=max(np.linalg.norm(points[1]-points[0]),np.linalg.norm(points[2]-points[3]))
    height=max(np.linalg.norm(points[3]-points[0]),np.linalg.norm(points[2]-points[1]))
    if width<2*height or height<8:return None
    if padding:
        center=points.mean(axis=0)
        points=center+(points-center)*np.array([1+padding*height/width,1+padding],dtype=np.float32)
        width+=padding*height;height*=1+padding
    width,height=int(math.ceil(width)),int(math.ceil(height))
    if width>image.shape[1]*2 or height>image.shape[0]*2:return None
    target=np.float32([[0,0],[width-1,0],[width-1,height-1],[0,height-1]])
    return cv2.warpPerspective(image,cv2.getPerspectiveTransform(points,target),(width,height),
                               flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)


def recognition_views(image, polygon):
    """Two genuinely different views; normalize wide rows, never duplicate one.

    Fixed-width recognition squeezes long date/time rows. Bound their aspect
    ratio without rewriting pixels into digits. Short rows keep distinct margins.
    """
    padded = rectified_crop(image, polygon, .16)
    if padded is None:
        return []
    height, width = padded.shape[:2]
    if width / height > 5.2:
        return [(f'aspect-{ratio}', cv2.resize(padded, (round(height*ratio), height),
                                              interpolation=cv2.INTER_AREA)) for ratio in (4.8, 5.2)]
    plain = rectified_crop(image, polygon)
    return [('padding-0.0', plain), ('padding-0.16', padded)] if plain is not None else []


def split_row_polygon(image, polygon):
    """Separate two printed rows using an ink-free horizontal gap after deskew."""
    crop=rectified_crop(image,polygon)
    if crop is None:return []
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,15)
    height,width=gray.shape
    profile=np.count_nonzero(ink,axis=1)/width
    smooth=max(3,round(height*.04))
    occupied=np.flatnonzero(np.convolve(profile,np.ones(smooth)/smooth,mode='same')>=.035)
    if not len(occupied):return [polygon]
    gaps=np.flatnonzero(np.diff(occupied)>max(3,round(height*.05)))
    runs=np.split(occupied,gaps+1)
    runs=[run for run in runs if run[-1]-run[0]>=max(8,height*.2)]
    if len(runs)!=2:return [polygon]
    points=np.asarray(polygon,dtype=np.float32);result=[]
    for run in runs:
        a=max(0,(run[0]-height*.025)/height);b=min(1,(run[-1]+1+height*.025)/height)
        left=points[3]-points[0];right=points[2]-points[1]
        result.append(tuple(tuple(float(v) for v in p) for p in
                            [points[0]+a*left,points[1]+a*right,points[1]+b*right,points[0]+b*left]))
    return result


def numeric_region_proposals(image, lines, limit=4):
    """Bounded original detector proposals, including weak numeric fragments."""
    candidates=[]
    for line in lines:
        text=line.text.strip()
        if (not line.geometry_valid or len(line.polygon)!=4 or len(text)>40
                or not any(c.isdigit() for c in text)
                or re.search(r'%|kcal|\b(?:mg|ml|TEL|LOT)\b|\d\s*g\b|원|가격|영양|전화|품목|보고번호|'
                             r'(?<!\d)0\d{1,2}[- )]\d{2,4}-\d{3,4}',text,re.I)
                or re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?',text)):
            continue
        numeric=sum(c.isdigit() for c in text)
        if numeric<3 and not (line.score<.85 and line.width*line.height>=image.shape[0]*image.shape[1]*.002):continue
        candidates.append((numeric>=6,line.width*line.height,line.polygon))
    rows=[]
    for _,__,polygon in sorted(candidates,key=lambda x:(x[0],x[1]),reverse=True)[:limit]:
        rows.extend(split_row_polygon(image,polygon))
    return rows[:limit]


def dot_row_proposals(image, limit=4):
    """Small, disconnected dark components grouped into long shallow rows.

    Geometry is only a proposal, never a statement that the row is a date.
    Work at a bounded resolution and return at most four original-space quads.
    """
    scale=min(1.,1800/max(image.shape[:2]))
    small=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA) if scale<1 else image
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,15)
    count,labels,stats,centers=cv2.connectedComponentsWithStats(ink,8)
    max_dot=max(4,round(max(gray.shape)*.006))
    valid=np.flatnonzero((stats[:,cv2.CC_STAT_AREA]>=2)&(stats[:,cv2.CC_STAT_AREA]<=max_dot**2*.7)
                         &(stats[:,cv2.CC_STAT_WIDTH]<=max_dot)&(stats[:,cv2.CC_STAT_HEIGHT]<=max_dot))
    valid=valid[valid!=0]
    if len(valid)<25:return []
    lookup=np.zeros(count,dtype=np.uint8);lookup[valid]=255
    dots=lookup[labels]
    merged=cv2.morphologyEx(dots,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(max_dot*6,max_dot)))
    contours,_=cv2.findContours(merged,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    proposals=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if w<80 or h<10 or not 3.5<=w/h<=35 or w>gray.shape[1]*.85:continue
        selected=valid[(centers[valid,0]>=x)&(centers[valid,0]<x+w)&(centers[valid,1]>=y)&(centers[valid,1]<y+h)]
        if len(selected)<25:continue
        rectangle=cv2.minAreaRect(contour)
        points=cv2.boxPoints(rectangle)
        # Order around the quadrilateral from its top-left corner.
        ordered=points[np.argsort(np.arctan2(points[:,1]-points[:,1].mean(),points[:,0]-points[:,0].mean()))]
        ordered=np.roll(ordered,-np.argmin(ordered.sum(axis=1)),axis=0)
        if np.linalg.norm(ordered[1]-ordered[0])<np.linalg.norm(ordered[3]-ordered[0]):continue
        polygon=tuple(tuple(float(v/scale) for v in p) for p in ordered)
        proposals.append((len(selected),polygon))
    result=[]
    for _,polygon in sorted(proposals,key=lambda p:p[0],reverse=True)[:limit]:
        result.extend(split_row_polygon(image,polygon))
    return result[:limit]


def recover_geometric_rows(image, lines, recognize_crops, fallback_recognize=None):
    """Try up to eight automatic rows, two deskewed views per recognizer.

    Used only after normal selection abstains. No annotation/answer lookup;
    one row remains one selector observation, not multiple votes. Both views
    must pass the existing strict character-evidence gate without digit repair.
    """
    from .date_extraction import OCRLine
    from .line_recovery import _apply_views, _digit_evidence, _signature

    started = time.perf_counter()
    polygons = numeric_region_proposals(image, lines) + dot_row_proposals(image)
    anchors, jobs, crops = [], [], []
    for polygon in polygons:
        views = recognition_views(image, polygon)
        if len(views) != 2:
            continue
        xs, ys = zip(*polygon)
        bounds = (min(xs), min(ys), max(xs), max(ys))
        index = len(anchors)
        anchors.append(OCRLine('', 0., bounds, source='paddle-geometric', variant='geometric-rows',
                               polygon=polygon, original_box=bounds))
        for padding, crop in views:
            crops.append(crop)
            jobs.append((index, padding, bounds))
    if not crops:
        return [], [], [], time.perf_counter()-started
    observations, decisions, choices = [], [], {}
    for name, recognizer in [('primary', recognize_crops), ('english', fallback_recognize)]:
        if recognizer is None:
            continue
        try:
            results = recognizer(crops)
            if len(results) != len(jobs):
                raise ValueError('Geometric recognition count does not match requested crops')
            extra = []
            for (index, padding, bounds), result in zip(jobs, results):
                chars = tuple(result[2]) if len(result) > 2 else ()
                mean, minimum = _digit_evidence(result[0], chars)
                extra.append(replace(anchors[index], text=result[0], score=result[1],
                                     variant=f'geometry-{index}-{padding}-{name}',
                                     character_scores=chars, date_digit_score=mean, date_digit_min_score=minimum))
            active = list(anchors)
            audit = _apply_views(active, anchors, anchors, jobs, extra, strict=True)
            for decision in audit:
                index = decision['line_index']
                decision.update(recognizer=name, stage='automatic-geometric-rows',
                                line_index=len(lines)+index)
                if decision['accepted_text']:
                    choices.setdefault(index, []).append(active[index])
            decisions.extend(audit)
            observations.extend(extra)
        except Exception as exc:
            decisions.append(dict(line_index=-1, original_text='', original_box=None, accepted_text=None,
                                  reason='geometric-recognition-error', recognizer=name,
                                  error=f'{type(exc).__name__}: {exc}'))
    accepted = []
    for index, values in choices.items():
        if len({_signature(value.text) for value in values}) > 1:
            for decision in decisions:
                if decision['line_index'] == len(lines)+index:
                    decision.update(accepted_text=None, decision_basis='cross-recognizer-conflict')
            continue
        # Highest score chooses the transcription, never increases confidence.
        accepted.append(max(values, key=lambda value: value.score))
    # Overlapping proposals are one physical row. Conflicting stable readings
    # of that row veto both; matching readings retain just one observation.
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
    kept = [value for i, value in enumerate(accepted) if i not in discarded]
    for decision in decisions:
        if decision.get('accepted_text') and not any(
                value.box == decision['original_box'] and value.text == decision['accepted_text'] for value in kept):
            decision.update(accepted_text=None, decision_basis='overlapping-row-conflict-or-duplicate')
    return kept, observations, decisions, time.perf_counter()-started
