"""Scorer-only gate: fixed labels never enter submission inference."""
from pathlib import Path
from scripts.prepare_sequential_rounds import csv_read
from scripts.grouped_plan import PREVIOUS_BASE as BASE


def check_samples(folder, samples):
    labels, previous = {}, {}
    for n in (2,3):
        labels.update({r['image_id']:r['정답 날짜'].strip().replace('NONE-NONE-NONE','NONE')
                       for r in csv_read(BASE/f'stage2_initial_20260913/approved_labels_round_{n:02d}.csv')})
        previous.update({r['image_id']:r['final_date'] for r in csv_read(
            BASE/f'retest-stage2-20260913/execution/round_{n:02d}/submission.csv')})
    required = {'AMLT000353','AMLT000375','AMLT000378','BMLT003522'}
    protected = {i for i in samples if previous[i] == labels[i]}
    if not required <= set(samples):
        raise ValueError('Missing correction regression samples')
    result = []
    for n in (2,3):
        actual = {r['image_id']:r['final_date'] for r in csv_read(Path(folder)/f'round_{n:02d}/submission.csv')}
        failed = [i for i in sorted(required | protected) if actual.get(i) != labels[i]]
        result.append(dict(slot=n, required=sorted(required), protected=sorted(protected), failed=failed,
                           correct=sum(actual.get(i)==labels[i] for i in samples), images=len(samples),
                           label_pending=['AMLT000355']))
    return dict(passed=not any(r['failed'] for r in result), slots=result,
                scope='Limited correction/negative regression gate; not 500-image accuracy acceptance')
