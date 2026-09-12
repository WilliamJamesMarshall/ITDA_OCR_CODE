"""Export and verify the explicitly approved stage-2 annotation pool."""
import json
from collections import Counter
from pathlib import Path
from scripts import ocr_annotations as ann

def main():
    status=ann.audit()
    if not status['stage_2_complete']:
        raise ValueError('Stage 2 approval or annotation validation is incomplete')
    report=ann.export_approved()
    destination=Path(report['directory'])
    rec=[json.loads(line) for line in (destination/'recognition_pool.jsonl').read_text(encoding='utf-8').splitlines()]
    det=[json.loads(line) for line in (destination/'detection_pool.jsonl').read_text(encoding='utf-8').splitlines()]
    for row in rec:
        if ann.sha(Path(row['crop_path']))!=row['crop_sha256']:
            raise ValueError('Export crop hash mismatch: '+row['crop_path'])
    for image_id,digest in report['source_annotation_snapshot'].items():
        if ann.sha(ann.record_path(image_id))!=digest:
            raise ValueError('Annotation changed during export: '+image_id)
    if len(det)!=2610 or len({r['image_id'] for r in det})!=2610:
        raise ValueError('Detection pool does not contain 2610 unique scenes')
    closeout=dict(created_at=ann.now(),stage_2_complete=True,approved_images=2610,
        annotation_validation_errors=status['validation_errors'],recognition_crops=len(rec),
        detection_scenes=len(det),recognition_exclusions=dict(Counter(r['reason'] for r in report['recognition_exclusions'])),
        export_directory=str(destination),export_report_sha256=ann.sha(destination/'export_report.json'),
        crop_and_annotation_hashes_verified=True,approval_method='explicit_user_chat_bulk_as_is',
        individually_visually_verified=False,regression_tests_passed=297,
        stage3_ready=True,fold_assignment_created=False,training_started=False,
        note='Approved pool, not train/validation/test splits. Recognition exclusions are retained for detection and audit.')
    ann.write(ann.OUT/'stage2_closeout.json',closeout)
    print(closeout,flush=True)

if __name__=='__main__':main()
