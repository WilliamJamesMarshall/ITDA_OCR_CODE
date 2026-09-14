"""Small evidence-directed stages; the caller commits each completed stage."""
import cv2
from dataclasses import replace

from .date_extraction import _link_roles, parse_dates, submission_decision, POSITIVE_CONTEXT, NEGATIVE_CONTEXT
from .line_recovery import recovery_targets, recover_lines, recover_missing_rows
from .date_region_recovery import recover_geometric_rows
from .printed_context_recovery import recover_printed_context
from .thin_dot_recovery import recover_thin_dots
from .ocr_trace import ImageFrame


def needs_recovery(selection, lines):
    if selection.reason == 'explicit-partial-date':
        return False
    decision = submission_decision(selection, base_partial=selection.is_partial)
    if decision.status == 'NOT_FOUND':
        return False
    if decision.status == 'SELECTED' and not selection.is_partial:
        if selection.role_resolved and not selection.stop_ocr:
            return True  # Preserve the independent numeric check on new date pairs.
        return bool(recovery_targets(lines)) and any(c.iso == decision.output_date and c.ocr_score < .98
                                                    for c in selection.candidates)
    if selection.final_date is None or selection.is_partial:
        return not selection.stop_ocr or selection.reason.startswith('review_')
    if not selection.stop_ocr:
        return True
    # A complete but weakly recognized date also needs its existing row checked.
    return bool(recovery_targets(lines)) and any(c.iso == selection.final_date and c.ocr_score < .92
                                                for c in selection.candidates)


def actions_for(selection, lines):
    decision = submission_decision(selection, base_partial=selection.is_partial)
    if decision.recovery_reason in {'role', 'order'}:
        return ['context-roi', 'secondary']
    if recovery_targets(lines):
        if decision.status != 'SELECTED':
            return ['date-lines', 'fragment-roi', 'geometric', 'full-contrast', 'secondary', 'stroke', 'thin-dot']
        return ['date-lines', 'fragment-roi', 'contrast-roi', 'secondary', 'geometric', 'stroke', 'thin-dot']
    if not selection.candidates and not any(POSITIVE_CONTEXT.search(line.text) or NEGATIVE_CONTEXT.search(line.text)
                                            for line in lines):
        # No detected date or role region exists to crop. Discover it first.
        return ['secondary', 'geometric', 'stroke', 'thin-dot']
    return ['context-roi', 'geometric', 'secondary', 'stroke', 'thin-dot']


def run_stage(action, image, lines, backend, guard, config, trace, commit):
    # Lazy imports avoid the pipeline/budget module cycle.
    from .pipeline import _append_pass, _clahe, _label_crop_bounds, _date_fragment_lines, _fragment_bounds
    height, width = image.shape[:2]
    frame = ImageFrame(width, height)
    # All recovery crops are taken from the full original image, never a prior ROI.
    # Keep source/variant identity, but return crop-local geometry to original space.
    active = [replace(line, box=line.original_box, polygon=())
              if line.original_box and tuple(line.box)!=tuple(line.original_box) else line for line in lines]
    numeric = guard.recognize_date_crops if hasattr(backend, 'recognize_date_crops') else None
    observations, decisions, seconds = [], [], 0.
    if action in {'date-lines', 'geometric', 'stroke', 'thin-dot'}:
        if not hasattr(backend, 'recognize_crops'):
            return active, [], [], 0.
        if trace:
            trace.start_pass(frame, 'recognition-only', action)
        if action == 'date-lines':
            return recover_lines(image, active, guard.recognize_crops, numeric, on_progress=commit)
        function = {'geometric': recover_geometric_rows, 'stroke': recover_printed_context,
                    'thin-dot': recover_thin_dots}[action]
        if action == 'stroke':
            added, observations, decisions, seconds = function(image, active, guard.recognize_crops)
        else:
            added, observations, decisions, seconds = function(image, active, guard.recognize_crops, numeric)
        return [*active, *added], [*observations, *added], decisions, seconds
    bounds = None
    if action == 'context-roi':
        bounds = _label_crop_bounds(image, active)
        if bounds is None:
            return active, [], [], 0.
    elif action in {'fragment-roi', 'contrast-roi'}:
        fragments = _date_fragment_lines(active)
        if not fragments:
            return active, [], [], 0.
        bounds = _fragment_bounds(image, fragments[0])
    detector = 'recovery' if action == 'secondary' else 'mobile'
    if bounds:
        x1, y1, x2, y2 = bounds
        image = image[y1:y2, x1:x2]
        if action == 'context-roi':
            image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        frame = ImageFrame.crop(bounds, image.shape)
    if action in {'contrast-roi', 'full-contrast'}:
        image = _clahe(image)
    guard.check()
    guard.calls += 1
    _append_pass(active, [], backend, image, detector=detector, variant='selective-'+action,
                 product_rules=config.product_date_rules, context=config.date_context, frame=frame, trace=trace)
    return active, [], [], seconds
