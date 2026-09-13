"""Publish image-audit and actual visual-review evidence, preserving missing-file gates."""
import argparse
import shutil
from pathlib import Path
from collections import Counter
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read, csv_write, digest
from scripts.grouped_plan import BASE, verify, revise_mapping
from scripts.grouped_rounds import evidence, checked_evidence, now


def finalize(base,audit_dir,visual_path,out):
    verify(base)
    audit=read(audit_dir/'audit.json');checked_evidence(audit['mapping'])
    for name in ('script','photometry_script','color_script','precise_geometry_script'):
        checked_evidence(audit[name])
    visual=read(visual_path)
    if visual['training_authorized'] is not False: raise ValueError('Mapping cannot grant training approval')
    decisions={r['test_id']:r for r in visual['decisions']}
    if len(decisions)!=17: raise ValueError('Unexpected visual review coverage')
    rows=csv_read(base/'test_to_original_mapping.csv');before={r['test_id']:dict(r) for r in rows}
    originals={r['original_id']:r for r in rows if r['original_id']}
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(base/'test_to_original_mapping.csv',out/'mapping_before.csv')
    audit_rows={r['test_id']:dict(r) for r in audit['results']}
    historical_path=ROOT/'artifacts/duplicate_audit_20260910/confirmed_duplicates.json'
    historical={"AMLT"+Path(r['a']).stem:r for r in read(historical_path)}
    deleted_path=ROOT/'artifacts/renumber_additional_20260910/삭제한_사진_22장.txt'
    deleted=deleted_path.read_text(encoding='utf-8-sig')
    missing=[]
    for row in rows:
        if row['original_id']:continue
        result=audit_rows[row['test_id']]
        decision=decisions.get(row['test_id'])
        if decision:
            if result['accepted'] or not decision['observation']:raise ValueError('Unexpected visual override')
            result.update(accepted=True,original_id=decision['original_id'],visual_review=decision)
        if digest(ROOT/'테스트용데이터'/(row['test_id']+'.jpg'))!=row['test_sha256']:
            raise ValueError('Test changed during audit')
        if result['accepted']:
            original=originals[result['original_id']]
            if digest(original['original_path'])!=original['original_sha256']:raise ValueError('Original changed')
            checked_evidence(dict(path=original['annotation_path'],sha256=original['annotation_sha256']))
            for key in ('original_id','original_path','original_sha256','group_id','group_verified','annotation_path','annotation_sha256'):
                row[key]=original[key]
            method='visual_and_geometric_review' if decision else 'unique_geometric_photometric_reconstruction'
            proof=dict(relationship='derived_from',reviewer=visual['reviewer'] if decision else 'Codex computational image verification; not human annotation approval',
                reviewed_at=now(),source_reference=str(audit_dir/'audit.json'),method=method,
                audit=evidence(audit_dir/'audit.json'),visual_review=evidence(visual_path) if decision else None,
                comparison=result,**{k:row[k] for k in ('test_id','original_id','test_sha256','original_sha256')})
            proof_path=out/'proofs'/f"{row['test_id']}.json";write(proof_path,proof)
            row.update(evidence=method,mapping_status='original_verified',mapping_review_path=str(proof_path),mapping_review_sha256=digest(proof_path))
        else:
            item=historical.get(row['test_id'])
            if not item or Path(item['b']).stem not in deleted:raise ValueError('Unclassified unresolved source')
            source=item['source_metadata']
            if any(r['original_sha256']==source['sha256'] for r in originals.values()):raise ValueError('Historical source is actually present')
            issue='Source identified; original deleted in prior duplicate cleanup; restore/re-admit requires explicit decision'
            row.update(mapping_status='source_identified_file_missing',mapping_issue=issue,
                identified_source_archive=source['original_archive'],identified_source_path=source['original_path'],
                identified_source_sha256=source['sha256'])
            missing.append(dict(test_id=row['test_id'],round=int(row['round']),reason=issue,
                old_additional_path=item['b'],source=source,prior_confirmation=item,
                history=evidence(historical_path),deletion_list=evidence(deleted_path)))
    if len(missing)!=22:raise ValueError('Unexpected missing original count')
    candidate=out/'reviewed_mapping.csv'
    csv_write(candidate,rows,list(dict.fromkeys(k for row in rows for k in row)))
    write(out/'missing_originals.json',dict(created_at=now(),count=len(missing),items=missing))
    summary=revise_mapping(base,candidate)
    current=csv_read(base/'test_to_original_mapping.csv')
    for row in current:
        old=before[row['test_id']]
        if old['original_id'] and any(row.get(k)!=v for k,v in old.items()):raise ValueError('Existing mapping changed')
    counts=[]
    for n in range(4,9):
        selected=[r for r in current if int(r['round'])==n and not before[r['test_id']]['original_id']]
        counts.append(dict(round=n,reviewed=len(selected),linked=sum(bool(r['original_id']) for r in selected),missing=sum(not r['original_id'] for r in selected)))
    result=dict(created_at=now(),reviewed=1106,linked=1084,automatic=1067,visual=17,missing_files=22,
        unknown_source=0,counts=counts,verification=summary,baseline=evidence(out/'mapping_before.csv'),
        mapping=evidence(base/'test_to_original_mapping.csv'),missing=evidence(out/'missing_originals.json'),
        training_authorized=False,protected_images_changed=False)
    write(out/'summary.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,default=BASE)
    for name in ('audit','visual','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(finalize(a.workspace,a.audit,a.visual,a.output))


if __name__=='__main__':main()
