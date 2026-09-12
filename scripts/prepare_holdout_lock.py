"""Inventory existing answer exposure without moving/deleting user originals."""
from pathlib import Path
from scripts import ocr_annotations as ann

def main():
    base=ann.ROOT/'학습 및 테스트 결과';out=base/'05_holdout_lock'
    sources=[]
    for directory in ['상품사진_정답지','추가수집_정답지','테스트용_정답지','학습대상_정답지']:
        for path in sorted((ann.ROOT/directory).glob('*.xlsx')):
            sources.append(dict(path=str(path),sha256=ann.sha(path),risk='full answer workbook readable by current account'))
    # Whole directories contain labels or prior label-bearing snapshots. Listing
    # only a newly split answer file would overlook these readable copies.
    for relative in ['학습 및 테스트 결과/00_protocol','학습 및 테스트 결과/02_annotations','artifacts']:
        directory=ann.ROOT/relative
        count=sum(1 for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in ('.json','.jsonl','.csv','.txt','.xlsx'))
        sources.append(dict(path=str(directory),label_or_trace_candidate_files=count,
            risk='records, exports, histories, snapshots or traces can expose holdout answers; requires custody audit'))
    split=base/'01_splits/draft/split_manifest.csv'
    report=dict(created_at=ann.now(),status='blocked_pending_group_review_and_scorer_custody',physical_lock_complete=False,
        scorer_only_access_verified=False,training_allowed=False,
        draft_split_sha256=ann.sha(split) if split.exists() else None,
        final_holdout_hash=None,final_holdout_created_at=None,
        existing_plaintext_sources=sources,
        required_decisions=['Separate scorer account or external custodian; training identity must not read answer archives.',
            'Approved final product groups and fold sizes before final holdout commitment.'],
        actions_not_taken=['No workbooks, annotations or backups deleted/moved.',
            'No account/ACL changes or keys stored alongside ciphertext.',
            'No claim that previously viewed labels have become unseen.'])
    ann.write(out/'lock_readiness.json',report)
    print(dict(status=report['status'],source_locations=len(sources),physical_lock_complete=False))

if __name__=='__main__':main()
