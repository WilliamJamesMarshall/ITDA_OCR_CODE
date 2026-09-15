"""Prepare immutable 1..5 input evidence; never run OCR, optimize, or assign groups."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scripts import ocr_annotations as ann


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.resolve(), args.out.resolve()
    if out.exists():
        raise FileExistsError('Preserve existing evidence; use a new audit directory')
    mapping_path = base / 'test_to_original_mapping.csv'
    mapping = {r['original_id']: r for r in rows(mapping_path) if r['round'] in ('1', '2', '3', '4', '5')}
    expected = {f'AMLC{i:06d}' for i in range(1, 1747)} | {f'BMLC{i:06d}' for i in range(2247, 2611)}
    assert set(mapping) == expected
    assert Counter(r['round'] for r in mapping.values()) == {'1': 216, '2': 500, '3': 500, '4': 394, '5': 500}
    parent = base / 'joint123-20260914-v1/targeted-retrain-code-20260914-v1'
    pool_path = parent / 'release-02/pool.json'
    pool = read(pool_path)
    roles = {i: pool['group_roles'][r['group_id']] for i, r in pool['admitted'].items()}
    registry = read(base / 'group_roles.json')
    assert all(registry[g] == role for g, role in pool['group_roles'].items())
    assert set(roles) == {i for i, r in mapping.items() if r['round'] in ('1', '2', '3')}
    for sample in pool['samples']:
        assert sha(sample['crop_path']) == sample['crop_sha256']
        assert sample['role'] == roles[sample['image_id']]
        assert sha(pool['admitted'][sample['image_id']]['annotation_path']) == sample['record_sha256']
    workbook = ann.ROOT / '학습대상_정답지/answer_000001_002610_manual.xlsx'
    assert sha(workbook) == '765db2f4781ec1975893e66b7c3c755f8a68246c68fc05d302597d36900a4d2d'
    import openpyxl
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    try:
        values = list(book.active.values)
        assert values[0][0] == 'image_id'
        labels = {int(row[0]): row[2] for row in values[1:] if row[0] is not None}
    finally:
        book.close()
    assert set(labels) == set(range(1, 2611))
    assert labels[1117] == '2021-06-26' and labels[1161] == '2021-01-27'
    records, amendments, problems = {}, [], []
    for image_id, row in mapping.items():
        path = Path(row['original_path']).resolve()
        assert path.parent == (ann.ROOT / '학습대상데이터').resolve()
        assert sha(path) == row['original_sha256']
        record = read(row['annotation_path'])
        assert sha(row['annotation_path']) == row['annotation_sha256']
        assert record['image_id'] == image_id and record['image_sha256'] == row['original_sha256']
        assert record['review']['status'] == 'approved'
        errors = ann.validate(record, approve=True)
        if errors:
            problems.append(dict(image_id=image_id, errors=errors))
        latest = labels[int(image_id[4:])]
        if record['final_date'] != latest:
            amendments.append(dict(image_id=image_id, historical_final_date=record['final_date'], final_date=latest,
                                   historical_annotation_path=row['annotation_path'], historical_annotation_sha256=row['annotation_sha256']))
        records[image_id] = record
    assert not problems, problems
    excluded = rows(base / 'excluded_derivatives.csv')
    assert len(excluded) == 1106
    excluded_hashes = {r['test_sha256'] for r in excluded}
    assert not excluded_hashes & {r['original_sha256'] for r in mapping.values()}
    assert len({r['original_sha256'] for r in mapping.values()}) == 2110
    new_ids = sorted(set(mapping) - set(roles))
    candidates_path = ann.ROOT / '학습 및 테스트 결과/04_group_review/candidate_pairs.json'
    decisions_path = candidates_path.with_name('pair_decisions.json')
    decisions = read(decisions_path)
    links = [p for p in read(candidates_path) if
             (p['a'] in new_ids and roles.get(p['b']) == 'inner_validation') or
             (p['b'] in new_ids and roles.get(p['a']) == 'inner_validation')]
    checkpoint = parent / 'training-run/joint123-attempt02/epoch_001.pdparams'
    assert sha(checkpoint) == '07f23a2059d05d9977969e1f4a8742974376a5e1e47e28f23af7f23f13c611d9'
    unresolved = [dict(image_id=i, round=mapping[i]['round'], group_id=records[i]['group_id'],
                       group_evidence=records[i]['group_evidence'], mapping_group_verified=mapping[i]['group_verified']) for i in new_ids]
    out.mkdir(parents=True)
    write_new(out / 'latest-final-date-overlay.json', dict(workbook=dict(path=str(workbook), sha256=sha(workbook)),
              scope='Final-date overlay only. Crop transcription and historical annotations are unchanged.', changes=amendments))
    write_new(out / 'new-group-evidence.json', dict(images=unresolved, validation_link_candidates=links,
              pair_decisions=decisions, note='Similarity is not product identity. Absence of a candidate is not proof of independence. No roles assigned.'))
    evidence_paths = [mapping_path, pool_path, workbook, checkpoint, candidates_path, decisions_path,
                      base / 'group_roles.json', parent / 'authorization.json',
                      base / 'joint123-20260914-v1/release/authorization.json',
                      base / 'answer-correction-20260915-v1/amendment.json',
                      base / 'label-1117-correction-20260915-v1/amendment.json']
    evidence_paths += [base / f'test_round_{n:02d}.csv' for n in range(1, 7)]
    result = dict(created_at=datetime.now(timezone.utc).isoformat(), status='input_audit_complete_group_assignment_pending',
        originals=2110, round_counts=dict(Counter(r['round'] for r in mapping.values())),
        verified_originals=2110, verified_annotations=2110, duplicate_original_hashes=0, excluded_derivatives=1106,
        old_group_roles=len(pool['group_roles']), inherited_original_roles=dict(Counter(roles.values())),
        old_verified_crop_counts=dict(Counter(s['role'] for s in pool['samples'])),
        new_originals_without_inherited_role=len(new_ids), new_group_verified_flags=dict(Counter(mapping[i]['group_verified'] for i in new_ids)),
        new_to_fixed_validation_candidates=len(links),
        new_images_in_validation_candidates=len({i for p in links for i in (p['a'], p['b']) if i in new_ids}),
        global_pair_decisions=len(decisions), final_date_overlay_changes=len(amendments),
        initial_development=dict(Counter(r['round'] for r in mapping.values() if r['seen_in_development'] == 'true')),
        optimizer_started=False, whole_image_tests='held_until_separate_user_instruction', shared_weights_changed=False,
        files={str(p): sha(p) for p in evidence_paths})
    write_new(out / 'audit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
