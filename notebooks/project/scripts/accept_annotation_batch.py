"""Record explicit user as-is approval; retain technical release gates."""
import copy
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann

DECISION='주석은 전부 초안 그대로 승인한다. 또한 3단계 — 기존 705장 처리 정책 확정 단계로 넘어갈 수 있게 되도록 남은 작업 시작해.'


def prepare(record, source_digest, decision_id):
    candidate=copy.deepcopy(record)
    candidate['user_acceptance']=dict(status='approved',method='explicit_user_chat_bulk_as_is',
        decision_id=decision_id,accepted_source_sha256=source_digest,
        individually_visually_verified=False,scope='existing_draft_as_is_not_missing_annotations')
    probe=copy.deepcopy(candidate)
    probe['review']['reviewer']='사용자 (대화에서 초안 일괄 승인)'
    try:
        released=ann.accept_draft(probe)
        released['review']['method']='explicit_user_chat_bulk_as_is'
        released['review']['individually_visually_verified']=False
        released['training_readiness']=dict(status='eligible',blockers=[])
        return released,[]
    except ValueError as exc:
        return candidate,str(exc).splitlines()


def main(decision_id='user-as-is-approval-20260912', decision=DECISION):
    snapshot=ann.OUT/'approvals'/decision_id
    if (snapshot/'result.json').exists():
        print(ann.read(snapshot/'result.json'))
        return
    paths=sorted((ann.OUT/'records').glob('*.json'))
    if len(paths)!=2610:
        raise ValueError('Expected 2610 records')
    manifest={}
    # Snapshot first. Later writes still use revision/hash checks.
    for path in paths:
        record=ann.read(path)
        destination=snapshot/'records'/path.name
        if not destination.exists():
            ann.write(destination,record)
        manifest[record['image_id']]=ann.sha(destination)
    ann.write(snapshot/'decision.json',dict(decision_id=decision_id,recorded_at=ann.now(),
        user_instruction=decision,source_annotation_snapshot=manifest,
        approval_is_not_individual_visual_verification=True))
    blocked={}
    released=[]
    for path in paths:
        record=ann.read(path)
        candidate,errors=prepare(record,manifest[record['image_id']],decision_id)
        if record.get('user_acceptance',{}).get('decision_id')!=decision_id:
            frozen=ann.read(snapshot/'records'/path.name)
            if record!=frozen:
                raise ValueError('Record changed after snapshot: '+record['image_id'])
            ann.save_review(record['image_id'],candidate,record['revision'],not errors)
        if errors:
            blocked[record['image_id']]=errors
        else:
            released.append(record['image_id'])
    ann.write(snapshot/'technical_blockers.json',blocked)
    ann.write(snapshot/'result.json',dict(user_accepted_images=2610,technically_released_images=len(released),
        technically_blocked_images=len(blocked),released_ids=released,
        stage3_policy_discussion_ready=True,all_annotation_requirements_complete=not blocked,
        training_allowed=False))
    ann.audit()
    print(dict(user_accepted=2610,released=len(released),blocked=len(blocked)),flush=True)


if __name__=='__main__':
    main()
