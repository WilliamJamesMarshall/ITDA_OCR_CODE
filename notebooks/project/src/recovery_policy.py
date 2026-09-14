"""Validated, model-bound gain-per-second scheduling; no labels at inference."""
import hashlib
import json
import math
from pathlib import Path
from .date_extraction import submission_decision, submission_fields

VERSION = 'paper-recovery-v1'
FIELDS = ('year', 'month', 'day')


def binding(config):
    models = {p.relative_to(config.weights_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(Path(config.weights_dir).rglob('inference.*')) if p.is_file()}
    knobs = {k:getattr(config, k) for k in ('mobile_side_limit', 'recovery_side_limit',
        'recognition_minimum_width', 'recognition_batch_size', 'enable_width_batches', 'collect_ctc_candidates')}
    return hashlib.sha256(json.dumps(dict(version=VERSION, models=models, knobs=knobs),
                                    sort_keys=True).encode()).hexdigest()


def features(selection, lines, value=None):
    fields = submission_fields(value if value is not None else selection.final_date)
    valid = [c for c in selection.candidates if not c.explicit_negative and not c.repaired]
    confidences = {}
    for field in FIELDS:
        supporting = [c.ocr_score for c in valid if submission_fields(c.iso)[field] == fields[field]]
        # This is a feature, not a calibrated probability. Agreement views are
        # correlated: never multiply probabilities or count them as new samples.
        confidences[field] = max(supporting, default=0.) if fields[field] != 'NONE' else 0.
    decision = submission_decision(selection, base_partial=selection.is_partial)
    reason = decision.recovery_reason or ('partial' if selection.is_partial else 'selected')
    missing = sum(fields[k] == 'NONE' for k in FIELDS)
    score = min(confidences.values())
    bucket = min(4, max(0, int(score * 5)))
    key = '|'.join(map(str, (reason, missing, min(len(lines)//20, 3), bucket,
                            int(selection.role_resolved), int(selection.order_resolved))))
    return dict(key=key, confidence=confidences, missing_fields=missing, reason=reason)


class RecoveryPolicy:
    def __init__(self, path, expected_binding):
        self.path = Path(path)
        self.artifact = json.loads(self.path.read_text(encoding='utf-8'))
        a = self.artifact
        if (a.get('version') != VERSION or a.get('binding') != expected_binding
                or a.get('deployment_approved') is not True):
            raise ValueError('Recovery policy must be validated, approved and match the exact model/config')
        proof = a.get('validation', {})
        if (proof.get('group_disjoint') is not True or proof.get('passed') is not True
                or not proof.get('report_sha256') or not proof.get('source_reference')):
            raise ValueError('Independent validation evidence is required; fitted tables alone are not deployment proof')
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def estimate(self, state, action):
        table = self.artifact['actions'].get(state['key']+'|'+action)
        if not table or table.get('independent_images', 0) < 20:
            return None
        gain, seconds = table['mean_net_fields'], table['p80_seconds'] * 1.25
        if not all(math.isfinite(v) for v in (gain, seconds)) or not -3 <= gain <= 3 or seconds <= 0:
            raise ValueError('Invalid recovery utility table')
        return dict(expected_net_fields=gain, estimated_seconds=seconds, utility=gain/seconds)

    def field_probabilities(self, state):
        result = {}
        for field, score in state['confidence'].items():
            table = self.artifact['fields'].get(field+'|'+str(min(4, max(0, int(score*5)))))
            result[field] = (table['correct_probability'] if table and table.get('independent_images', 0) >= 20 else None)
        return result

    def pop(self, queue):
        # Unsupported strata receive a fair exploration slot every fourth turn;
        # an uncalibrated OCR score is never substituted for learned gain.
        self.turn = getattr(self, 'turn', 0) + 1
        if self.turn % 4 == 0:
            return queue.pop(0)
        scored = []
        for index, item in enumerate(queue):
            state = features(item['selection'], item['lines'], item['retained_output'].final_date)
            estimate = self.estimate(state, item['actions'][0])
            if estimate and estimate['expected_net_fields'] > 0:
                scored.append((estimate['utility'], -index, index))
        return queue.pop(max(scored)[2] if scored else 0)
