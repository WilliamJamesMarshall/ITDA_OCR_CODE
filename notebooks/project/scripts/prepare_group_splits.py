"""Reproducible provisional group/fold analysis; never certify visual identities."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
from scripts import ocr_annotations as ann

BASE=ann.ROOT/'학습 및 테스트 결과'
OUT=BASE/'04_group_review'
SEED=20260911

def assign_folds(rows):
    """Size/stratum-balanced deterministic greedy assignment of indivisible groups."""
    groups=defaultdict(list)
    for row in rows:groups[row['group_id']].append(row)
    sizes=Counter(); strata={i:Counter() for i in range(1,6)}; result={}
    totals=Counter((r['date_type'],r['difficulty'],r['source_dataset']) for r in rows)
    def order(item):
        group,members=item
        return (-len(members),not any(r['seen_in_development'] for r in members),hashlib.sha256(f'{SEED}:{group}'.encode()).hexdigest())
    for group,members in sorted(groups.items(),key=order):
        counts=Counter((r['date_type'],r['difficulty'],r['source_dataset']) for r in members)
        allowed=range(1,5) if any(r['seen_in_development'] for r in members) else range(1,6)
        def cost(fold):
            n=len(members);target=len(rows)/5
            size=((sizes[fold]+n-target)**2-(sizes[fold]-target)**2)/max(target,1)
            balance=sum(((strata[fold][k]+v-totals[k]/5)**2-(strata[fold][k]-totals[k]/5)**2)/max(totals[k]/5,1) for k,v in counts.items())
            return max(0,sizes[fold]+n-target),size*5+balance, sizes[fold],fold
        fold=min(allowed,key=cost);sizes[fold]+=len(members);strata[fold].update(counts)
        for row in members:result[row['image_id']]=fold
    return result

def leakage(rows,assignment):
    if set(assignment)!= {r['image_id'] for r in rows}:raise ValueError('Incomplete assignment')
    groups=defaultdict(set);hashes=defaultdict(set)
    for row in rows:
        fold=assignment[row['image_id']]
        if fold not in range(1,6):raise ValueError('Invalid fold')
        groups[row['group_id']].add(fold);hashes[row['image_sha256']].add(fold)
        if row['seen_in_development'] and fold==5:raise ValueError('Development exposure in fold 5')
    if any(len(v)>1 for v in groups.values()):raise ValueError('Group leakage')
    if any(len(v)>1 for v in hashes.values()):raise ValueError('Hash leakage')

def features(path):
    with Image.open(path) as image:
        image=image.convert('RGB');image.thumbnail((256,256));rgb=np.asarray(image)
    hashes=[];layouts=[]
    for k in range(4):
        rotated=np.rot90(rgb,k).copy()
        gray=cv2.cvtColor(rotated,cv2.COLOR_RGB2GRAY)
        dct=cv2.dct(cv2.resize(gray,(32,32)).astype('float32'))[:8,:8].reshape(-1)[1:]
        hashes.append(''.join('1' if n>np.median(dct) else '0' for n in dct))
        small=cv2.resize(rotated,(8,8)).astype('float32')/255
        vector=small.reshape(-1);vector=vector-vector.mean();vector/=max(np.linalg.norm(vector),1e-6)
        layouts.append(vector.tolist())
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    hist=cv2.calcHist([hsv],[0,1],None,[12,8],[0,180,0,256]).flatten()
    hist/=max(np.linalg.norm(hist),1e-6)
    return dict(phash=hashes,histogram=hist.tolist(),layouts=layouts)

def main():
    records=[ann.read(p) for p in sorted((ann.OUT/'records').glob('*.json'))]
    if len(records)!=2610 or not all(r['review']['status']=='approved' for r in records):raise ValueError('Require 2610 approved records')
    cache_path=OUT/'visual_features_v1.json';cache=ann.read(cache_path) if cache_path.exists() else {}
    for i,r in enumerate(records):
        if r['image_sha256'] not in cache:cache[r['image_sha256']]=features(ann.source_path(r))
        if i%100==0:
            ann.write(cache_path,cache);print('features',i,len(records),flush=True)
    ann.write(cache_path,cache)
    fs=[cache[r['image_sha256']] for r in records]
    hist=np.asarray([f['histogram'] for f in fs],dtype='float32')
    layouts=np.asarray([f['layouts'] for f in fs],dtype='float32')
    bits=np.asarray([[[int(c) for c in h] for h in f['phash']] for f in fs],dtype='uint8')
    pairs={}; neighbours=defaultdict(list)
    for i,r in enumerate(records):
        distance=np.count_nonzero(bits!=bits[i,0],axis=2).min(axis=1)
        color=hist@hist[i];spatial=np.einsum('nkd,d->nk',layouts,layouts[i,0]).max(axis=1)
        score=(1-distance/63)*.5+color*.25+spatial*.25;score[i]=-10
        candidates=set(np.argsort(score)[-3:].tolist())|set(np.flatnonzero(distance<=10).tolist())
        candidates.discard(i)
        for j in candidates:
            a,b=sorted([r['image_id'],records[j]['image_id']]);key=a+'__'+b
            if key in pairs:continue
            pairs[key]=dict(pair_id=key,a=a,b=b,phash_distance=int(distance[j]),color_similarity=round(float(color[j]),5),
                spatial_similarity=round(float(spatial[j]),5),score=round(float(score[j]),5),decision='pending',reviewer='',
                note='Similarity candidate only; not evidence of identical product or singleton identity.')
        if i%500==0:print('neighbours',i,flush=True)
    pairs=sorted(pairs.values(),key=lambda p:(-p['score'],p['pair_id']))
    ann.write(OUT/'candidate_pairs.json',pairs)
    ann.write(OUT/'group_review_template.json',dict(status='pending',reviewer='',all_images_reviewed=False,
        images=[dict(image_id=r['image_id'],group_id=r['group_id'],decision='pending',evidence='') for r in records]))
    rows=[]
    for r in records:
        rows.append(dict(image_id=r['image_id'],image_path=str(ann.source_path(r)),image_sha256=r['image_sha256'],group_id=r['group_id'],
            seen_in_development=r['seen_in_development'],difficulty=r['difficulty'],source_dataset=r['source_dataset'],
            date_type='none' if r['final_date']=='NONE' else 'partial' if 'NONE' in r['final_date'] else 'full'))
    assignment=assign_folds(rows);leakage(rows,assignment)
    dest=BASE/'01_splits/draft';dest.mkdir(parents=True,exist_ok=True)
    fields=['image_id','image_path','fold','group_id','image_sha256']
    with (dest/'split_manifest.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        writer.writerows({k:(assignment[r['image_id']] if k=='fold' else r[k]) for k in fields} for r in rows)
    for fold in range(1,6):
        # All evaluation manifests are labels-free; fold 5 exposes only ID/path.
        name=f'fold_{fold:02d}'+('_final' if fold==5 else '')+'.csv'
        with (dest/name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['image_id','image_path']);writer.writeheader()
            writer.writerows({k:r[k] for k in ['image_id','image_path']} for r in rows if assignment[r['image_id']]==fold)
    strata={f:dict(Counter('|'.join([r['date_type'],r['difficulty'],r['source_dataset']]) for r in rows if assignment[r['image_id']]==f)) for f in range(1,6)}
    exact=Counter(r['image_sha256'] for r in rows)
    summary=dict(status='provisional_not_for_training',seed=SEED,algorithm='group_greedy_size5_plus_joint_stratum_v1',
        images=len(rows),current_groups=len(set(r['group_id'] for r in rows)),exact_duplicate_groups=sum(n>1 for n in exact.values()),
        candidate_pairs=len(pairs),fold_sizes=dict(Counter(assignment.values())),strata=strata,
        current_group_and_hash_overlap=0,development_images_in_fold5=0,
        visual_product_group_verification_complete=False,fold_size_tolerance_approved=False,
        blockers=['Current groups are SHA identities only; manual product grouping required.',
            '522 is a target, not authority to split groups. Any size deviation needs approval before final freeze.'],
        training_allowed=False,source_annotation_hashes={r['image_id']:ann.sha(ann.record_path(r['image_id'])) for r in records})
    ann.write(dest/'split_summary.json',summary)
    print({k:v for k,v in summary.items() if k not in ('source_annotation_hashes','strata')},flush=True)

if __name__=='__main__':
    raise SystemExit('Legacy fold writer disabled. Use scripts.prepare_sequential_rounds.')
