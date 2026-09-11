"""Audit known training-copy provenance without touching the held-out test set.

An exact-hash exclusion is necessary, not sufficient: package/product groups
and raw line/polygon annotations must be reviewed before fitting a model.
"""
import json
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent


def main():
    mapping_path=ROOT/'artifacts/training_dataset_20260910/source_mapping.json'
    development_path=ROOT/'artifacts/date-recognition-repair-20260910/manifest.json'
    mapping=json.loads(mapping_path.read_text(encoding='utf8'))
    development=json.loads(development_path.read_text(encoding='utf8'))['included']
    development_hashes={r['sha256'] for r in development}
    excluded=[];pending=[]
    seen={}
    for row in mapping:
        item=dict(row)
        if row['sha256'] in development_hashes:
            item['reason']='exact_copy_of_frozen_development_input'
            excluded.append(item)
        elif row['sha256'] in seen:
            item.update(reason='exact_duplicate_training_candidate',duplicate_of=seen[row['sha256']])
            excluded.append(item)
        else:
            item.update(status='NOT_TRAINING_APPROVED',raw_line_annotations=None,
                        product_group=None,polygon_annotations=None,
                        blocker='raw transcription and region/group verification required')
            pending.append(item)
        seen.setdefault(row['sha256'],row['filename'])
    result=dict(scope='Provenance metadata only; no test directory access, no training or label edits',
                sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (mapping_path,development_path)},
                mapped_images=len(mapping),frozen_development_images=len(development),
                excluded_count=len(excluded),pending_annotation_count=len(pending),
                approved_for_training_count=0,exact_hash_exclusion_is_not_product_group_split=True,
                excluded=excluded,pending=pending)
    (OUT/'training_readiness.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('pending','excluded')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
