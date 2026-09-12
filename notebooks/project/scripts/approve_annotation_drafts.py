"""Record explicit user bulk approval without inventing missing annotations."""
import copy
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann

DECISION='주석은 전부 초안 그대로 승인한다. 남은 작업 시작해'


def approved_candidate(record, snapshot_sha256):
    candidate=copy.deepcopy(record)
    candidate['user_draft_approval']=dict(status='approved',method='explicit_user_bulk_approval',
        decision=DECISION,reviewer='user',approved_at=ann.now(),
        approved_revision=record['revision'],approved_snapshot_sha256=snapshot_sha256,
        individual_visual_inspection_claimed=False)
    candidate['review']['reviewer']=candidate['review']['reviewer'] or 'user'
    try:
        accepted=ann.accept_draft(candidate)
        accepted['review']['method']='explicit_user_bulk_approval'
        accepted['training_readiness']=dict(status='eligible',blockers=[])
        return accepted,True
    except ValueError as exc:
        candidate['training_readiness']=dict(status='blocked_missing_annotation',blockers=str(exc).splitlines())
        return candidate,False


def main(root=ann.ROOT,output=ann.OUT):
    results=[]
    for path in sorted((output/'records').glob('*.json')):
        record=ann.read(path)
        if record.get('user_draft_approval',{}).get('decision')==DECISION:
            results.append(dict(image_id=record['image_id'],training_readiness=record['training_readiness']))
            continue
        candidate,eligible=approved_candidate(record,ann.sha(path))
        saved=ann.save_review(record['image_id'],candidate,record['revision'],eligible,root,output)
        results.append(dict(image_id=record['image_id'],training_readiness=saved['training_readiness']))
    report=dict(decision=DECISION,created_at=ann.now(),user_approved_images=len(results),
        training_eligible_images=sum(r['training_readiness']['status']=='eligible' for r in results),
        technical_blocked_images=sum(r['training_readiness']['status']!='eligible' for r in results),
        individual_visual_inspection_claimed=False,images=results)
    ann.write(output/'bulk_approval_report.json',report)
    ann.audit(output)
    print({k:v for k,v in report.items() if k!='images'},flush=True)


if __name__=='__main__':
    main()
