"""Fail-closed workflow checks; not an OS security boundary or scorer identity proof."""
import csv
import hashlib
import json
from pathlib import Path

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def validate_partition(rows,train_ids,validation_ids,round_number):
    by_id={r['image_id']:r for r in rows}
    if len(by_id)!=len(rows):raise ValueError('Duplicate manifest ID')
    for field in ('group_id','image_sha256'):
        seen={}
        for row in rows:
            fold=int(row['fold'])
            if not 1<=fold<=5:raise ValueError('Invalid fold number')
            if row[field] in seen and seen[row[field]]!=fold:raise ValueError(field+' crosses folds')
            seen[row[field]]=fold
    train_ids=set(train_ids);validation_ids=set(validation_ids)
    if not train_ids or not validation_ids:raise ValueError('Both partitions must be nonempty')
    if train_ids & validation_ids:raise ValueError('Image leakage')
    if not (train_ids|validation_ids)<=set(by_id):raise ValueError('Unknown training image')
    if any(int(by_id[i]['fold'])>round_number for i in train_ids|validation_ids):raise ValueError('Future/final fold leakage')
    for field in ('group_id','image_sha256'):
        train={by_id[i][field] for i in train_ids};val={by_id[i][field] for i in validation_ids}
        held={r[field] for r in rows if int(r['fold'])>round_number}
        if train&val or (train|val)&held:raise ValueError(field+' leakage')

def require_release(root,round_number,train_list,validation_list):
    raise ValueError('Legacy 5-fold release disabled; use sequential_rounds.require_training_release')

    # Historical implementation retained below for audit; unreachable under v2.
    base=Path(root)/'학습 및 테스트 결과'
    release_path=base/'01_splits/training_release.json'
    if not release_path.exists():
        raise ValueError('Training blocked: final group review, splits, round release and scorer isolation are not certified')
    release=json.loads(release_path.read_text(encoding='utf-8'))
    if release.get('status')!='released' or release.get('round')!=round_number:
        raise ValueError('No release for this round')
    if not release.get('scorer_isolation_verified') or not release.get('group_review_verified'):
        raise ValueError('Group review or scorer isolation is incomplete')
    manifest=base/'01_splits/split_manifest.csv'
    if digest(manifest)!=release['split_sha256']:raise ValueError('Split changed')
    for name,path in [('optimizer_train',train_list),('inner_validation',validation_list)]:
        if digest(path)!=release[name+'_sha256']:raise ValueError('Unapproved label list: '+name)
    with manifest.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    validate_partition(rows,release['optimizer_train_ids'],release['inner_validation_ids'],round_number)
    snapshot=Path(release['recognition_pool'])
    if digest(snapshot)!=release['recognition_pool_sha256']:raise ValueError('Recognition pool changed')
    pool=[json.loads(line) for line in snapshot.read_text(encoding='utf-8').splitlines()]
    by_path={str(Path(r['crop_path']).resolve()).casefold():r for r in pool}
    for name,path in [('optimizer_train',train_list),('inner_validation',validation_list)]:
        actual=set()
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():continue
            image,label=line.split('\t',1);image=Path(image)
            if not image.is_absolute():image=Path(root)/image
            record=by_path.get(str(image.resolve()).casefold())
            if record is None or label!=record['transcription'] or digest(image)!=record['crop_sha256']:
                raise ValueError('Unknown/changed crop or label')
            actual.add(record['image_id'])
        if actual!=set(release[name+'_ids']):raise ValueError('Release image IDs do not match labels')
    with manifest.open(encoding='utf-8-sig',newline='') as stream:groups={r['image_id']:r['group_id'] for r in csv.DictReader(stream)}
    for image_id in release['optimizer_train_ids']:
        if groups[image_id] in release['permanent_inner_validation_groups']:
            raise ValueError('Permanent validation group returned to optimizer')
    for image_id in release['inner_validation_ids']:
        if groups[image_id] not in release['permanent_inner_validation_groups']:
            raise ValueError('Validation group missing from permanent registry')
    for fold in range(1,round_number+1):
        evidence=release['completed_evaluations'][str(fold)]
        if digest(Path(evidence['path']))!=evidence['sha256']:raise ValueError('Round evaluation evidence changed')
