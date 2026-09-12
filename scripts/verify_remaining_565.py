"""Read-only record verification and reproducible review handoff report."""
import copy
from collections import Counter
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH

def main():
    ids=ann.read(BATCH/'cohort.json')['image_ids']
    errors={};states=Counter();changed_dates=[]
    for image_id in ids:
        record=ann.read(ann.record_path(image_id));states[record['review']['status']]+=1
        before=ann.read(BATCH/'before'/f'{image_id}.json')
        if record['final_date']!=before['final_date']:changed_dates.append(image_id)
        candidate=copy.deepcopy(record);candidate['review']['reviewer']='verification-only'
        try:ann.accept_draft(candidate)
        except ValueError as exc:errors[image_id]=str(exc)
    report=dict(created_at=ann.now(),cohort_size=len(ids),unique_ids=len(set(ids)),
        ready_for_human_review=len(ids)-len(errors),errors=errors,review_status=dict(states),
        changed_final_dates=changed_dates,url='http://127.0.0.1:8767',
        human_approvals_created_by_completion=0,
        note='초안 완성도/승인 경로 검사이며 원문·영역의 정확도 인증이나 사람 승인이 아님. 가려진 문자는 추측하지 않음.')
    ann.write(BATCH/'completion_report.json',report)
    print(report)
    if len(ids)!=565 or len(set(ids))!=565 or errors or changed_dates:
        raise SystemExit(1)

if __name__=='__main__':main()
