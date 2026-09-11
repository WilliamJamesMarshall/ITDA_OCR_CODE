"""Diagnostic region identity and evidence, deliberately not a date selector."""
from dataclasses import asdict, dataclass
import math
import re

from .date_extraction import POSITIVE_CONTEXT, NEGATIVE_CONTEXT, parse_dates, _partial_dates


@dataclass(frozen=True)
class ImageFrame:
    """Affine map from continuous image-edge coordinates to EXIF-oriented input.

    Width/height are edge extents, not last pixel indices. Crop scale uses
    actual resized dimensions, not the requested floating-point resize factor.
    """
    width: int
    height: int
    to_original: tuple[float, ...] = (1., 0., 0., 0., 1., 0.)

    def map_polygon(self, polygon):
        a, b, c, d, e, f = self.to_original
        return tuple((a*x + b*y + c, d*x + e*y + f) for x, y in polygon)

    @classmethod
    def crop(cls, bounds, shape):
        left, top, right, bottom = bounds
        height, width = shape[:2]
        return cls(width, height, ((right-left)/width, 0., left, 0., (bottom-top)/height, top))

    @classmethod
    def rotated(cls, width, height, angle):
        transforms = {
            90: (height, width, (0., 1., 0., -1., 0., height)),
            180: (width, height, (-1., 0., width, 0., -1., height)),
            270: (height, width, (0., -1., width, 1., 0., 0.)),
        }
        return cls(*transforms[angle])


def box_polygon(box):
    left, top, right, bottom = box
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def _bounds(polygon):
    xs, ys = zip(*polygon)
    return min(xs), min(ys), max(xs), max(ys)


def _overlap(first, second):
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0, right-left) * max(0, bottom-top)
    area1 = (first[2]-first[0]) * (first[3]-first[1])
    area2 = (second[2]-second[0]) * (second[3]-second[1])
    return intersection / (area1 + area2 - intersection) if area1 + area2 else 0.


def _evidence(text):
    # These are lexical observations, never proof of the semantic date role.
    hints = []
    for role, pattern in (('expiry', POSITIVE_CONTEXT), ('manufacturing', NEGATIVE_CONTEXT),
                          ('quality', re.compile(r'\b(?:BBD|TETT)\b', re.I))):
        hints.extend(dict(role=role, text=m.group(), span=(m.start(), m.end()),
                          basis='lexical_only') for m in pattern.finditer(text))
    full = [dict(value=p.value.isoformat(), raw=p.raw, span=(p.start, p.end),
                 order=p.order, order_reason=p.order_reason, repaired=p.repaired)
            for p in parse_dates(text)]
    partial = list(dict.fromkeys(_partial_dates(text))) if not full else []
    digits = sum(c.isdigit() for c in text)
    separators = sum(text.count(s) for s in './-')
    date_like = bool(hints or full or partial or
                     (len(text) <= 40 and (digits >= 4 and separators >= 1 or digits >= 2 and separators >= 2)))
    return dict(role_hints=hints, full_parses=full, partial_parses=partial,
                date_like=date_like,
                parse_status='full' if full else 'partial' if partial else 'unparsed' if text.strip() else 'no_text')


class ImageTrace:
    """Per-image trace. IDs are local, geometric hypotheses are not semantic merges."""
    def __init__(self, image_id, emit=None):
        self.image_id = image_id
        self.emit = emit
        self.frames = []
        self.observations = []
        self.regions = []
        self.outcomes = []
        self.original_size = None
        self.recovery_decisions = []

    def start(self, width, height):
        self.original_size = (width, height)
        self._emit(dict(kind='image_start', original_size=self.original_size,
                        coordinate_space='exif_oriented_image_edges', schema_version=1))

    def _emit(self, event):
        if self.emit is not None:
            self.emit(dict(image_id=self.image_id, **event))

    def start_pass(self, frame, detector, variant):
        self._emit(dict(kind='ocr_start', pass_id=f'p{len(self.frames)+1:03d}',
                        detector=detector, variant=variant, geometry=asdict(frame) if frame else None))

    def record_pass(self, lines, unrecognized, frame, detector, variant, seconds, selection=None, error=None):
        pass_id = f'p{len(self.frames)+1:03d}'
        frame_record = dict(pass_id=pass_id, detector=detector, variant=variant,
                            geometry=asdict(frame) if frame else None)
        self.frames.append(frame_record)
        added = []
        used = set()
        for index, line in enumerate([*lines, *unrecognized]):
            polygon = line.polygon or box_polygon(line.box)
            valid = (frame is not None and line.geometry_valid and len(polygon) >= 3 and
                     all(math.isfinite(v) for point in polygon for v in point))
            mapped = frame.map_polygon(polygon) if valid else None
            bounds = _bounds(mapped) if mapped else None
            if bounds and (bounds[2] <= bounds[0] or bounds[3] <= bounds[1]):
                mapped, bounds = None, None
            matches = []
            if bounds:
                matches = [region for region in self.regions
                           if region['anchor_box'] and _overlap(bounds, region['anchor_box']) >= .75]
            # No transitive expansion, no many-to-one matches within a pass.
            match = matches[0] if len(matches) == 1 and matches[0]['region_id'] not in used else None
            if match is None:
                match = dict(region_id=f'r{len(self.regions)+1:04d}', anchor_box=bounds,
                             observation_ids=[])
                self.regions.append(match)
                association = 'ambiguous_new' if matches else 'new'
            else:
                association = 'geometric_overlap_hypothesis'
            region_id = match['region_id']
            used.add(region_id)
            observation_id = f'{pass_id}:o{index+1:04d}'
            match['observation_ids'].append(observation_id)
            record = dict(observation_id=observation_id, region_id=region_id, pass_id=pass_id,
                          source=line.source, variant=line.variant, text=line.text,
                          character_scores=line.character_scores, date_digit_score=line.date_digit_score,
                          date_digit_min_score=line.date_digit_min_score,
                          score=None if line.geometry_source == 'detector_polygon' else line.score,
                          local_box=line.box, local_polygon=polygon, original_polygon=mapped,
                          original_box=bounds, geometry_source=line.geometry_source,
                          association=association, possible_region_ids=[r['region_id'] for r in matches],
                          recognition_state='recognized' if index < len(lines) else 'detected_without_text',
                          **_evidence(line.text))
            added.append(record)
            self.observations.append(record)
        outcome = dict(pass_id=pass_id, ocr_seconds=seconds, error=error,
                       selection=self._selection(selection) if selection else None)
        self.outcomes.append(outcome)
        self._emit(dict(kind='ocr_pass', frame=frame_record, observations=added, outcome=outcome))

    def _selection(self, selection):
        candidates = []
        for candidate in selection.candidates:
            # Keep all matching observation IDs; do not guess merged-line ancestry.
            ids = [o['observation_id'] for o in self.observations
                   if o['source'] == candidate.source and o['variant'] == candidate.variant
                   and tuple(o['local_box']) == tuple(candidate.box) and candidate.raw in o['text']]
            for decision in self.recovery_decisions:
                if (decision['accepted_text'] and candidate.raw in decision['accepted_text']
                        and tuple(decision.get('original_box') or ()) == tuple(candidate.box)):
                    ids.extend(o['observation_id'] for o in self.observations
                               if o['variant'].startswith(f"line-{decision['line_index']}-")
                               and any(p['value']==candidate.iso for p in o['full_parses']))
            candidates.append(dict(value=candidate.iso, raw=candidate.raw, box=candidate.box,
                                   source=candidate.source, variant=candidate.variant,
                                   observation_ids=ids, order_reason=candidate.order_reason,
                                   explicit_expiry=candidate.explicit_positive,
                                   explicit_manufacturing=candidate.explicit_negative))
        return dict(final_date=selection.final_date, reason=selection.reason,
                    stop_ocr=selection.stop_ocr, digits_confident=selection.digits_confident,
                    order_resolved=selection.order_resolved, candidates=candidates)

    def record_recovery(self, decisions):
        self.recovery_decisions.extend(decisions)
        self._emit(dict(kind='line_recovery', decisions=decisions))

    def finish(self, selection, error=None):
        self._emit(dict(kind='image_end', selection=self._selection(selection), error=error,
                        summary=self.summary()))

    def summary(self):
        return dict(passes=len(self.frames), regions=len(self.regions), observations=len(self.observations),
                    unparsed_date_like=sum(o['date_like'] and o['parse_status'] == 'unparsed' for o in self.observations),
                    detected_without_text=sum(o['recognition_state'] == 'detected_without_text' for o in self.observations),
                    unknown_geometry=sum(o['original_box'] is None for o in self.observations),
                    geometric_associations=sum(o['association'] == 'geometric_overlap_hypothesis' for o in self.observations),
                    failed_passes=sum(o['error'] is not None for o in self.outcomes),
                    line_recovery_changes=sum(d['accepted_text'] is not None for d in self.recovery_decisions),
                    ocr_seconds=sum(o['ocr_seconds'] for o in self.outcomes))
