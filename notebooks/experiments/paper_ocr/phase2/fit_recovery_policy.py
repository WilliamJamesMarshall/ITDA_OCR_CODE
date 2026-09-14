"""Offline fitting only after a separate analysis instruction; no OCR/model calls.

JSONL rows: image_id, group_id, partition=calibration_fit, approved=true,
state (the inference feature object), action, seconds, before/after/expected
year/month/day dicts. All data must come from reviewed group-separated records.
Output is a NON-DEPLOYABLE draft until held-out evaluation and approval.
"""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

FIELDS = ('year', 'month', 'day')


def fit(rows, optimizer_groups, holdout_groups, binding):
    actions, fields, seen_actions, seen_images = defaultdict(list), defaultdict(list), set(), set()
    fitted_groups = set()
    for row in rows:
        group = row['group_id']
        if (not group or row.get('approved') is not True or row['partition'] != 'calibration_fit'
                or group in optimizer_groups or group in holdout_groups):
            raise ValueError('Reviewed calibration-only, group-disjoint data required')
        fitted_groups.add(group)
        key = (row['image_id'], row['state']['key'], row['action'])
        if key in seen_actions:
            raise ValueError('Repeated image/action/state is not independent evidence')
        seen_actions.add(key)
        before, after, truth = row['before'], row['after'], row['expected']
        gain = sum(after[f] == truth[f] for f in FIELDS) - sum(before[f] == truth[f] for f in FIELDS)
        if not math.isfinite(row['seconds']) or row['seconds'] <= 0:
            raise ValueError('Measured positive elapsed time required')
        actions[row['state']['key']+'|'+row['action']].append((row['image_id'], gain, row['seconds']))
        # Use only first state/image for reliability; multiple views do not add N.
        if row['image_id'] not in seen_images:
            for field in FIELDS:
                score = row['state']['confidence'][field]
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError('Invalid confidence feature')
                fields[field+'|'+str(min(4, int(score*5)))].append(before[field] == truth[field])
            seen_images.add(row['image_id'])
    if not fitted_groups:
        raise ValueError('Empty calibration pool')
    return dict(version='paper-recovery-v1', binding=binding, deployment_approved=False,
        validation=None, fit_groups=sorted(fitted_groups),
        actions={k:dict(independent_images=len({r[0] for r in v}),
            mean_net_fields=sum(r[1] for r in v)/len(v),
            p80_seconds=sorted(r[2] for r in v)[min(len(v)-1, int(.8*len(v)))]) for k,v in actions.items()},
        fields={k:dict(independent_images=len(v), correct_probability=(sum(v)+1)/(len(v)+2))
                for k,v in fields.items()})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--records', required=True, type=Path)
    p.add_argument('--groups', required=True, type=Path)
    p.add_argument('--binding', required=True)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--execute-analysis', action='store_true')
    a = p.parse_args()
    if not a.execute_analysis:
        p.error('Fitting is paused; separate user instruction and --execute-analysis required')
    groups = json.loads(a.groups.read_text(encoding='utf-8'))
    if groups.get('reviewed') is not True:
        raise ValueError('Reviewed group roles required')
    rows = [json.loads(line) for line in a.records.read_text(encoding='utf-8').splitlines() if line.strip()]
    result = fit(rows, set(groups['optimizer_groups']), set(groups['holdout_groups']), a.binding)
    result['sources'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.records,a.groups)}
    with a.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
