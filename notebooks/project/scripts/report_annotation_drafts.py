"""Read-only candidate snapshot and frozen source verification."""
import sys
import json
from collections import Counter
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann


def main():
    records=[ann.read(p) for p in sorted((ann.OUT/'records').glob('*.json'))]
    regions=[r for record in records for r in record['regions']]
    questions=[]
    for record in records:
        questions.append(dict(image_id=record['image_id'],
            ocr_completed=bool(record.get('ocr_draft_pass')) or record['source_dataset']=='additional',
            image_issues=record.get('draft',{}).get('issues',[]),
            regions=[dict(region_id=r['region_id'],text=r['transcription'],issues=r.get('draft',{}).get('issues',[]))
                for r in record['regions'] if r.get('draft',{}).get('issues')]))
    frozen=ann.read(ann.ROOT/'학습 및 테스트 결과/00_protocol/data/frozen_hashes.json')
    changed=[path for path,digest in frozen.items() if ann.sha(ann.ROOT/path)!=digest]
    labels={r['training_image_id']:r['final_date'] for r in (json.loads(line) for line in
        (ann.ROOT/'학습 및 테스트 결과/00_protocol/data/training_labels.jsonl').read_text(encoding='utf-8').splitlines())}
    final_date_changes=[r['image_id'] for r in records if labels.get(r['image_id'])!=r['final_date']]
    source=ann.read(ann.ROOT/'추가수집데이터/metadata/annotations.json')
    source_text_changes=[]
    checked_source_dates=0
    for record in records:
        for r in record['regions']:
            p=r['provenance']
            if p.get('type')=='external_source_candidate' and p.get('source_class') in ('date','exp'):
                checked_source_dates+=1
                if r['transcription']!=source[p['key']]['ann'][p['index']].get('transcription',''):
                    source_text_changes.append(record['image_id']+'/'+r['region_id'])
    ready=[]
    incomplete={}
    for record in records:
        candidate=dict(record,review=dict(record['review'],reviewer='dry_run_validation_only'))
        try:
            ann.accept_draft(candidate)
            ready.append(record['image_id'])
        except ValueError as exc:
            incomplete[record['image_id']]=str(exc).splitlines()
    report=dict(created_at=ann.now(),images=len(records),
        metadata_drafts=sum(bool(r.get('draft')) for r in records),
        product_ocr_completed=sum(bool(r.get('ocr_draft_pass')) for r in records),
        product_ocr_total=2246,additional_source_images=364,
        product_draft_sources=dict(Counter(r.get('ocr_draft_pass',{}).get('method','fresh_cpu_ocr') for r in records if r.get('ocr_draft_pass'))),
        complete_for_visual_accept=len(ready),requires_correction_before_accept=len(incomplete),
        images_without_date_candidates=sum(not any(a['kind']=='date_line' and a['status']!='rejected' for a in r['regions']) for r in records),
        candidate_regions=dict(Counter(r['kind'] for r in regions)),
        nonempty_raw_text=sum(bool(r['transcription'].strip()) for r in regions),
        roles_suggested=sum(r['role'] is not None for r in regions),
        date_field_sets_suggested=sum(r['kind']=='date_line' and 'unknown' not in r['field_states'].values() for r in regions),
        context_regions=sum(len(r.get('ocr_context',[])) for r in records),
        approved=sum(r['review']['status']=='approved' for r in records),
        frozen_source_changes=changed,
        final_date_changes=final_date_changes,external_date_strings_checked=checked_source_dates,
        external_date_string_changes=source_text_changes,
        structural_errors={r['image_id']:ann.validate(r) for r in records if ann.validate(r)},
        note='초안 생성과 사용자 승인 상태를 분리 집계. 승인 근거는 각 레코드의 review/user_acceptance 및 approvals 스냅샷을 참조.')
    ann.write(ann.OUT/'draft_progress.json',report)
    ann.write(ann.OUT/'focused_review_queue.json',questions)
    ann.write(ann.OUT/'acceptance_readiness.json',dict(ready_for_human_visual_accept=ready,requires_correction=incomplete,
        note='구조상 승인 가능 여부만 검사. 실제 사람 승인이나 정확도 평가 아님.'))
    print(report,flush=True)


if __name__=='__main__':
    main()
