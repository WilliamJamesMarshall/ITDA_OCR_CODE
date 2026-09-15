"""Base coverage first, then incremental evidence-directed recovery within a deadline."""
import json
import math
import os
import time
from contextlib import nullcontext
from dataclasses import replace
from itertools import zip_longest
from pathlib import Path

from .date_extraction import select_date, submission_fields, submission_decision
from .ocr_trace import ImageFrame, ImageTrace
from .pipeline import (PipelineConfig, PaddleOCRBackend, discover_images, _load_bgr,
                       _append_pass, _write_submission, _percentile)
from .line_recovery import recovery_targets, recover_lines
from .date_region_recovery import recover_geometric_rows
from .selective_recovery import needs_recovery, actions_for, remaining_actions, run_stage
from .recovery_policy import RecoveryPolicy, binding, features


class BudgetExhausted(RuntimeError):
    pass


class RecoveryGuard:
    """Cooperative call boundary only; does not claim to interrupt native inference."""
    def __init__(self, backend, deadline, clock, max_calls=None, max_crops=32):
        self.backend, self.deadline, self.clock = backend, deadline, clock
        self.calls, self.max_calls, self.max_crops = 0, max_calls, max_crops

    def check(self):
        if self.clock() >= self.deadline:
            raise BudgetExhausted('deadline_exhausted')
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise BudgetExhausted('call_allowance_exhausted')

    def crops(self, name, crops):
        self.check()
        if len(crops) > self.max_crops:
            raise BudgetExhausted('crop_allowance_exhausted')
        self.calls += 1
        return getattr(self.backend, name)(crops)

    def recognize_crops(self, crops):
        return self.crops('recognize_crops', crops)

    def recognize_date_crops(self, crops):
        return self.crops('recognize_date_crops', crops)


def atomic_csv(path, rows):
    temp = Path(str(path) + '.tmp')
    _write_submission(temp, rows)
    os.replace(temp, path)


def output_selection(selection, *, base_partial=False, previous=None):
    """Use the same evidence decision for CSV and diagnostics, never elapsed time."""
    from .date_extraction import field_evidence
    from .date_fields import serialize_fields
    fields = field_evidence(selection)
    retained_fields = []
    if previous is not None and previous.final_date:
        old = submission_fields(previous.final_date)
        names = ('year','month','day')
        compatible = all(fields[k] == 'NONE' or old[k] == 'NONE' or fields[k] == old[k] for k in names)
        anchored = all(fields[k] == 'NONE' for k in names) or any(
            fields[k] != 'NONE' and fields[k] == old[k] for k in names)
        retracted = selection.reason in {'negative-context', 'expiry-not-printed'} or any(
            c.explicit_negative and not c.explicit_positive and c.ocr_score >= .65
            and all(old[k] == 'NONE' or old[k] == submission_fields(c.iso)[k] for k in names)
            for c in selection.candidates)
        # Shared fields alone do not link two physical date tokens. When a new
        # explicit expiry is elsewhere, retain only its own supported fields.
        new_expiry = [c for c in selection.candidates if c.explicit_positive
                      and not c.explicit_negative and c.ocr_score >= .85 and not c.repaired]
        old_support = [c for c in previous.candidates if c.iso == previous.final_date]
        if (new_expiry and old_support and any(fields[k] != 'NONE' for k in names)
                and all(c.box[2] > c.box[0] and c.box[3] > c.box[1] for c in [*new_expiry, *old_support])):
            disjoint = all(min(a.box[2],b.box[2]) <= max(a.box[0],b.box[0])
                           or min(a.box[3],b.box[3]) <= max(a.box[1],b.box[1])
                           for a in new_expiry for b in old_support)
            retracted = retracted or disjoint
        if compatible and anchored and not retracted:
            combined = {k: fields[k] if fields[k] != 'NONE' else old[k] for k in names}
            try:
                combined = serialize_fields(combined)
            except ValueError:
                pass  # Individually valid fragments can form an impossible calendar date.
            else:
                retained_fields = [k for k in names if fields[k] == 'NONE' and combined[k] != 'NONE']
                fields = combined
    value = fields['final_date'] if fields['final_date'] != 'NONE' else None
    decision = submission_decision(selection, base_partial=base_partial)
    details = dict(selection.policy_details or {})
    details['retained_fields'] = retained_fields
    details.update(candidate_date=decision.candidate_date, expiration_date=value, output_fields=fields,
                   status=decision.status, recovery_reason=decision.recovery_reason,
                   confidence_level=details.get('confidence_level', 'REVIEW') if decision.status=='SELECTED' else 'REVIEW')
    details['status'] = 'SELECTED' if value and 'NONE' not in value else 'PARTIAL' if value else decision.status
    return replace(selection, final_date=value, output_fields=fields, policy_details=details)


def recovery_queue(pending):
    """Give each evidence class a turn before taking another from one class."""
    groups = [sorted((item for item in pending if item['priority']==priority), key=lambda item:item['index'])
              for priority in sorted({item['priority'] for item in pending})]
    return [item for group in zip_longest(*groups) for item in group if item is not None]


def run_budget_pipeline(input_dir, output_path, *, config=None, backend=None, max_images=None,
                        on_image=None, budget_seconds=1470., reserve_seconds=30.,
                        recovery_image_seconds=12., clock=time.perf_counter, notebook_started=None):
    if not math.isfinite(budget_seconds) or not 0 <= reserve_seconds < budget_seconds:
        raise ValueError('A finite positive execution budget with output reserve is required')
    if not math.isfinite(recovery_image_seconds) or recovery_image_seconds <= 0:
        raise ValueError('Recovery allowance must be finite and positive')
    started = clock()
    deadline = (started if notebook_started is None else notebook_started) + budget_seconds
    config = config or PipelineConfig()
    policy = RecoveryPolicy(config.recovery_policy_path, binding(config)) if config.recovery_policy_path else None
    images = discover_images(input_dir)
    if max_images is not None:
        if max_images <= 0:
            raise ValueError('max_images must be positive')
        images = images[:max_images]
    output = Path(output_path)
    partial = Path(str(output) + '.partial.csv')
    journal = Path(str(output) + '.progress.jsonl')
    status_path = Path(str(output) + '.status.json')
    trace_path = Path(str(output) + '.trace.jsonl')
    if any(p.exists() for p in (output, partial, journal, status_path, trace_path,
                               Path(str(output)+'.tmp'), Path(str(partial)+'.tmp'))):
        raise FileExistsError('Use a new development output path; do not overwrite prior results')
    output.parent.mkdir(parents=True, exist_ok=True)

    def event(value):
        with journal.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')

    phase = 'base'

    def emit_trace(value):
        with trace_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(phase=phase, **value), ensure_ascii=False) + '\n')

    def stage(name):
        return backend.profile.measure(name) if hasattr(backend, 'profile') else nullcontext()

    event(dict(kind='run_start', expected_images=len(images), budget_seconds=budget_seconds,
               recovery_policy_sha256=policy.sha256 if policy else None,
               policy='base-first-v2', timing_scope='notebook non-CONFIG entry including imports' if notebook_started is not None
               else 'pipeline entry; notebook/import excluded'))
    init = clock()
    if backend is None:
        backend = PaddleOCRBackend(config)
    init_seconds = clock()-init
    rows, pending, timings, failures, recovery_errors = [], [], [], [], []
    completed = 0
    # Store observations only, never 500 full-resolution arrays.
    for path in images:
        if clock() >= deadline-reserve_seconds:
            event(dict(kind='base_budget_exhausted', next_image=path.stem))
            break
        image_started = clock()
        event(dict(kind='base_start', image_id=path.stem))
        if hasattr(backend, 'profile'):
            backend.profile.image_id = path.stem
        if hasattr(backend, 'begin_image'):
            backend.begin_image()
        try:
            with stage('image_load'):
                image = _load_bgr(path)
            height, width = image.shape[:2]
            trace = ImageTrace(path.stem, emit_trace) if config.collect_trace else None
            if trace:
                trace.start(width, height)
            lines, passes = [], []
            with stage('base_full_ocr_and_selection'):
                _append_pass(lines, passes, backend, image, detector='mobile', variant='original',
                             product_rules=config.product_date_rules, context=config.date_context,
                             frame=ImageFrame(width, height), trace=trace)
                selection = select_date(lines, final=False, product_rules=config.product_date_rules,
                                        context=config.date_context)
            if trace:
                trace.finish(selection)
            provisional = output_selection(selection, base_partial=selection.is_partial)
            rows.append(dict(image_id=path.stem, **submission_fields(provisional.final_date)))
            completed += 1
            if needs_recovery(selection, lines):
                priority = 0 if recovery_targets(lines) else 1 if selection.candidates else 2
                pending.append(dict(priority=priority, index=len(rows)-1, path=path, lines=lines,
                                    selection=selection, retained_output=provisional, base_partial=selection.is_partial, recovery_seconds=0.,
                                    actions=actions_for(selection, lines)))
            event(dict(kind='base_end', image_id=path.stem, row=rows[-1], error=None,
                       reason=selection.reason, seconds=clock()-image_started))
        except Exception as exc:
            error = dict(image_id=path.stem, error=repr(exc))
            failures.append(error)
            rows.append(dict(image_id=path.stem, **submission_fields(None)))
            event(dict(kind='base_end', **error, row=rows[-1], seconds=clock()-image_started))
        timings.append(clock()-image_started)
        with stage('checkpoint_write'):
            atomic_csv(partial, rows)
        if on_image:
            on_image(dict(row=rows[-1], seconds=timings[-1], phase='base',
                          error=failures[-1]['error'] if failures and failures[-1]['image_id']==path.stem else None))
        if config.progress_every and len(rows) % config.progress_every == 0:
            print(f'Base processed {completed}/{len(images)}; attempted {len(rows)}', flush=True)

    base_complete = completed == len(images) and not failures
    base_seconds = clock()-started
    if base_complete:
        atomic_csv(output, rows)
        event(dict(kind='base_complete', processed_images=completed, seconds=base_seconds))
    # Never spend recovery time while any input has not successfully received base OCR.
    queue = recovery_queue(pending) if base_complete else []
    costs = {}
    while queue:
        if clock() >= deadline-reserve_seconds:
            break
        item = policy.pop(queue) if policy else queue.pop(0)
        index, path, lines, selection = (item[k] for k in ('index', 'path', 'lines', 'selection'))
        action = item['actions'].pop(0)
        item.setdefault('attempted_actions', set()).add(action)
        state_before = features(selection, lines, item['retained_output'].final_date)
        learned = policy.estimate(state_before, action) if policy else None
        remaining = recovery_image_seconds - item['recovery_seconds']
        if remaining <= 0:
            event(dict(kind='recovery_skipped', image_id=path.stem, action=action,
                       reason='image_allowance_exhausted', remaining_actions=item['actions'],
                       recovery_seconds=item['recovery_seconds']))
            continue
        # Separate dense packages from sparse date crops; one slow package
        # must not price every later instance at the historical maximum.
        cost_key = (action, min(len(lines)//20, 3))
        samples = sorted(costs.get(cost_key, []))
        estimate = (samples[min(len(samples)-1, int(.8*len(samples)))] * 1.25
                    if samples else .8 if action in {'date-lines','fragment-roi','geometric','stroke','thin-dot'} else 2.5)
        if learned:
            estimate = max(estimate, learned['estimated_seconds'])
        if clock()+estimate >= deadline-reserve_seconds:
            event(dict(kind='recovery_skipped', image_id=path.stem, action=action,
                       reason='insufficient_estimated_stage_time', estimate_seconds=estimate))
            if item['actions']:
                queue.append(item)  # Try a cheaper remaining action, do not discard the image.
            continue
        if hasattr(backend, 'profile'):
            backend.profile.image_id = path.stem
        if hasattr(backend, 'begin_image'):
            backend.begin_image()
        guard = RecoveryGuard(backend, min(deadline-reserve_seconds, clock()+remaining), clock)
        phase = 'recovery'
        event(dict(kind='recovery_start', image_id=path.stem, reason=selection.reason, action=action,
                   state=state_before, row_before=rows[index], expected=learned,
                   calibrated_fields=policy.field_probabilities(state_before) if policy else None))
        action_started = clock()
        trace = None
        decisions = []
        def commit(active, observations, decisions, seconds):
            recovered = select_date(active, final=False, product_rules=config.product_date_rules,
                                    context=config.date_context)
            permitted = output_selection(recovered, base_partial=item['base_partial'], previous=item.get('retained_output'))
            item['lines'], item['selection'], item['retained_output'] = list(active), recovered, permitted
            previous_row = rows[index]
            rows[index] = dict(image_id=path.stem, **submission_fields(permitted.final_date))
            atomic_csv(output, rows)
            atomic_csv(partial, rows)
            if trace:
                trace.record_recovery(decisions)
                trace.record_selector_input(active, stage='incremental-'+action, final=False)
                trace.record_pass(observations, [], frame, 'recognition-only', action, seconds, recovered)
            event(dict(kind='recovery_checkpoint', image_id=path.stem, action=action, row=rows[index],
                       previous_row=previous_row, output_changed=previous_row!=rows[index],
                       field_changes={k:dict(before=previous_row[k], after=rows[index][k],
                                             selection_reason=recovered.reason,
                                             supporting_raw=[c.raw for c in recovered.candidates
                                                 if not c.explicit_negative and submission_fields(c.iso)[k] == rows[index][k]])
                                      for k in ('year','month','day') if previous_row[k] != rows[index][k]},
                       submission_decision=permitted.policy_details,
                       reason=recovered.reason, native_calls=guard.calls, decisions=decisions))
        try:
            with stage('recovery_image_load'):
                image = _load_bgr(path)
            guard.check()
            height, width = image.shape[:2]
            trace = ImageTrace(path.stem, emit_trace) if config.collect_trace else None
            frame = ImageFrame(width, height)
            if trace:
                trace.start(width, height)
            with stage('selected_recovery'):
                active, observations, decisions, seconds = run_stage(action, image, lines, backend, guard,
                                                                    config, trace, commit)
                commit(active, observations, decisions, seconds)
            if trace:
                trace.finish(item['selection'])
            event(dict(kind='recovery_end', image_id=path.stem, action=action, row=rows[index],
                       reason=item['selection'].reason, native_calls=guard.calls,
                       seconds=clock()-action_started, state_after=features(item['selection'], item['lines'],
                                                                          item['retained_output'].final_date)))
            if getattr(backend, 'last_ctc_candidates', None):
                event(dict(kind='ctc_diagnostics', image_id=path.stem, action=action,
                           candidates=backend.last_ctc_candidates, used_for_selection=False))
        except BudgetExhausted as exc:
            event(dict(kind='recovery_skipped', image_id=path.stem, reason=str(exc), native_calls=guard.calls))
        except Exception as exc:
            recovery_errors.append(dict(image_id=path.stem, error=repr(exc)))
            event(dict(kind='recovery_error', **recovery_errors[-1]))
        costs.setdefault(cost_key, []).append(clock()-action_started)
        item['recovery_seconds'] += clock()-action_started
        costs[cost_key] = costs[cost_key][-20:]
        item['actions'] = remaining_actions(item['selection'], item['lines'],
                                            item['actions'], item['attempted_actions'])
        verified_selection = submission_decision(item['selection'], base_partial=item['base_partial'])
        if (action == 'secondary' and recovery_targets(item['lines'])
                and not (item['selection'].digits_confident and verified_selection.recovery_reason in {'role', 'order'})
                and needs_recovery(item['selection'], item['lines'])):
            # Newly detected date rows did not exist when the queue was built.
            # Recheck their original pixels; do not relax the pair confidence gate.
            item['actions'].insert(0, 'date-lines')
        checked = any(d.get('decision_basis') in {'stable-aligned-date-digits','stable-role-recovery'}
                      for d in decisions)
        if (action == 'date-lines' and checked and verified_selection.status == 'SELECTED'
                and not item['selection'].is_partial and item['selection'].digits_confident):
            # One completed digit-check allowance is enough for an already admissible
            # date. Do not spend unrelated full-pass OCR to re-open the same field.
            event(dict(kind='recovery_stopped', image_id=path.stem, reason='selected_after_digit_check',
                       row=rows[index]))
        elif item['actions'] and needs_recovery(item['selection'], item['lines']):
            # Complete one bounded cheap follow-up while its image is active.
            # Larger chains return to the fair queue; no label or ID priority.
            if item['recovery_seconds'] < 2. and item['actions'][0] in {'date-lines','fragment-roi','geometric'}:
                queue.insert(0,item)
            else:
                queue.append(item)
    for item in queue:
        event(dict(kind='recovery_skipped', image_id=item['path'].stem, reason='global_deadline',
                   remaining_actions=item['actions']))
    if base_complete:
        for item in pending:
            final = output_selection(item['selection'], base_partial=item['base_partial'], previous=item.get('retained_output'))
            rows[item['index']] = dict(image_id=item['path'].stem, **submission_fields(final.final_date))
            event(dict(kind='final_selection', image_id=item['path'].stem, row=rows[item['index']], reason=final.reason))
        atomic_csv(output, rows)
        atomic_csv(partial, rows)
    elapsed = clock()-(started if notebook_started is None else notebook_started)
    summary = dict(status='completed' if base_complete and not recovery_errors and elapsed <= budget_seconds else
                   'failed' if failures or recovery_errors else 'timeout',
                   images=len(images), processed_images=completed, attempted_images=len(rows),
                   unprocessed_ids=[p.stem for p in images[len(rows):]],
                   output_complete=base_complete, output_path=str(output.resolve()) if base_complete else None,
                   partial_path=str(partial.resolve()), progress_path=str(journal.resolve()),
                   execution_policy='base-first-v2', budget_seconds=budget_seconds,
                   recovery_image_seconds=recovery_image_seconds,
                   total_elapsed_seconds=elapsed, elapsed_seconds=elapsed-init_seconds,
                   backend_init_seconds=init_seconds, base_seconds=base_seconds,
                   failures=[*failures, *recovery_errors], predicted_none=sum(r['final_date']=='NONE' for r in rows),
                   p50_image_seconds=_percentile(timings,.5) if timings else None,
                   p95_image_seconds=_percentile(timings,.95) if timings else None,
                   timing_scope='notebook non-CONFIG entry including imports' if notebook_started is not None else
                                'pipeline entry including initialization; caller/import startup excluded',
                   deadline_scope='cooperative native-call boundaries; no native interruption guarantee')
    status_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    event(dict(kind='run_end', **summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary
