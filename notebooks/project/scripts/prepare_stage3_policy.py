"""Prepare current-ID development exposure policy inputs; never assign folds."""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann


def main():
    records=[ann.read(p) for p in sorted((ann.OUT/'records').glob('*.json'))]
    legacy_path=ann.ROOT/'artifacts/date-recognition-repair-20260910/manifest.json'
    legacy=ann.read(legacy_path)['included']
    hashes={r['sha256'] for r in legacy}
    exposed=[r for r in records if r['image_sha256'] in hashes]
    if len(exposed)!=705 or len(hashes)!=705 or any(r['seen_in_development']!=(r['image_sha256'] in hashes) for r in records):
        raise ValueError('Legacy 705 exposure manifest mismatch')
    groups={r['group_id'] for r in exposed}
    prohibited=[r for r in records if r['group_id'] in groups]
    output=ann.ROOT/'학습 및 테스트 결과/03_existing_705_policy'
    fields=('image_id','source_image_id','source_dataset','image_sha256','group_id','seen_in_development')
    rows=[{k:r[k] for k in fields}|dict(user_accepted=r.get('user_acceptance',{}).get('status')=='approved',
        annotation_technically_released=r['review']['status']=='approved') for r in exposed]
    ann.write(output/'existing_705_manifest.json',dict(source_manifest=legacy_path.relative_to(ann.ROOT).as_posix(),
        source_manifest_sha256=ann.sha(legacy_path),images=rows))
    ann.write(output/'fold5_exclusion.json',dict(direct_exposure_ids=[r['image_id'] for r in exposed],
        group_closure_ids=[r['image_id'] for r in prohibited],
        rule='Exclude all exposed images and every member of their finalized product groups from fold 5.',
        recompute_after_group_changes=True,final_group_identity_verified=False))
    acceptance=ann.audit()
    report=dict(existing_images=len(exposed),datasets=dict(Counter(r['source_dataset'] for r in exposed)),
        current_group_closure=len(prohibited),stage3_policy_discussion_ready=True,
        user_as_is_accepted=acceptance['user_as_is_accepted_images'],
        annotation_technically_released=acceptance['annotation_images_approved'],
        annotation_technical_backlog=acceptance['pending_images'],
        stage3_policy_confirmed=True,
        inherited_policy=dict(allowed_folds=[1,2,3,4],forbidden_folds=[5],
            optimizer_training_only_after_assigned_fold_evaluation=True,
            old_scores_are_independent_generalization=False,external_warmup_training=False),
        limitations=['Final product-group consolidation and leakage check still required.',
            'Bulk as-is acceptance is not a claim of individual visual review.',
            'Missing annotations are not converted to negative detector labels.'],
        folds_created=False,training_started=False)
    ann.write(output/'stage3_entry_readiness.json',report)
    print(report,flush=True)


if __name__=='__main__':
    raise SystemExit('Legacy fold policy writer disabled. Exposure history remains preserved.')
