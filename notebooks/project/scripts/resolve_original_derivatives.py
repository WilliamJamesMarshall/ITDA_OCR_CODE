"""Audit derivative-to-original links using full-frame geometric and pixel evidence.

No OCR, labels, training, or image file edits. Audit first; publish only strong unique links.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read, csv_write, digest
from scripts.grouped_plan import BASE, verify, revise_mapping
from scripts.grouped_rounds import evidence, checked_evidence, now

cv2.setNumThreads(1)


@lru_cache(maxsize=180)
def gray(path):
    with Image.open(path) as source:
        im = ImageOps.exif_transpose(source).convert('L')
        im.thumbnail((720, 720), Image.Resampling.LANCZOS)
        return np.asarray(im).copy()


def features(row):
    path = row['original_path'] if row['original_id'] else str(ROOT / '테스트용데이터' / (row['test_id']+'.jpg'))
    expected = row['original_sha256'] if row['original_id'] else row['test_sha256']
    if digest(path) != expected: raise ValueError('Image hash changed: '+path)
    im = gray(path)
    kp, desc = cv2.SIFT_create(nfeatures=650).detectAndCompute(im,None)
    return dict(path=path, points=np.float32([k.pt for k in kp]), desc=desc, size=im.shape[::-1])


def compare(a,b):
    if a['desc'] is None or b['desc'] is None: return None
    pairs=cv2.BFMatcher().knnMatch(b['desc'],a['desc'],k=2)
    good=[p[0] for p in pairs if len(p)==2 and p[0].distance < .75*p[1].distance]
    if len(good)<12: return None
    bp=np.float32([b['points'][m.queryIdx] for m in good])
    ap=np.float32([a['points'][m.trainIdx] for m in good])
    cv2.setRNGSeed(20260913)
    h,mask=cv2.findHomography(ap,bp,cv2.RANSAC,2.5)
    if h is None: return None
    valid=mask.ravel().astype(bool); count=int(valid.sum())
    if count<12: return None
    coverage=float(cv2.contourArea(cv2.convexHull(bp[valid]))/np.prod(b['size']))
    original,target=gray(a['path']),gray(b['path'])
    warped=cv2.warpPerspective(original,h,b['size'])
    overlap=cv2.warpPerspective(np.full(original.shape,255,np.uint8),h,b['size'])>250
    overlap &= (target>12)&(warped>12)
    overlap=cv2.erode(overlap.astype(np.uint8),np.ones((7,7),np.uint8)).astype(bool)
    if overlap.sum()<100: return None
    aa=cv2.GaussianBlur(warped,(5,5),0)[overlap].astype(float)
    bb=cv2.GaussianBlur(target,(5,5),0)[overlap].astype(float)
    corr=float(np.corrcoef(aa,bb)[0,1])
    if not np.isfinite(corr): return None
    # Correlation must hold across the frame, not just a repeated package logo.
    cells=[]
    for y in np.array_split(np.arange(target.shape[0]),3):
        for x in np.array_split(np.arange(target.shape[1]),3):
            region=np.ix_(y,x); m=overlap[region]
            wa=cv2.GaussianBlur(warped[region],(5,5),0)[m].astype(float)
            tb=cv2.GaussianBlur(target[region],(5,5),0)[m].astype(float)
            if len(wa)>1000 and np.std(wa)>8 and np.std(tb)>8:
                cells.append(float(np.corrcoef(wa,tb)[0,1]))
    passed=bool(count>=30 and count/len(good)>=.6 and coverage>=.2 and overlap.mean()>=.65
                and corr>=.98 and len(cells)>=6 and min(cells)>=.94)
    return dict(inliers=count,good_matches=len(good),inlier_ratio=count/len(good),
        target_feature_coverage=coverage,overlap=float(overlap.mean()),pixel_correlation=corr,
        cell_correlations=cells,homography_original_to_test=h.tolist(),strong=passed)


def audit(base,out,limit=None):
    verify(base)
    out.mkdir(parents=True,exist_ok=False)
    rows=csv_read(base/'test_to_original_mapping.csv')
    originals=[r for r in rows if r['original_id']]
    # Previously mapped derivatives are not independent original retrieval entries.
    originals=list({r['original_id']:r for r in originals}.values())
    targets=[r for r in rows if not r['original_id']][:limit]
    data=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,f in enumerate(pool.map(features,originals),1):
            data.append(f)
            if i%250==0: print(f'Original features {i}/{len(originals)}',flush=True)
    usable=[i for i,a in enumerate(data) if a['desc'] is not None]
    descriptors=np.concatenate([data[i]['desc'] for i in usable])
    owners=np.concatenate([np.full(len(data[i]['desc']),i,np.int32) for i in usable])
    print(f'Indexing {len(descriptors)} descriptors',flush=True)
    index=cv2.flann_Index(descriptors,dict(algorithm=1,trees=4))
    results=[]
    for position,row in enumerate(targets,1):
        b=features(row)
        if b['desc'] is None:
            results.append(dict(test_id=row['test_id'],accepted=False,candidates=[])); continue
        neighbors,_=index.knnSearch(b['desc'],4,params={'checks':96})
        votes=Counter(int(owner) for ids in owners[neighbors] for owner in set(ids))
        top=[i for i,_ in votes.most_common(12)]
        # Local order is an extra candidate source, never evidence for acceptance.
        serial=int(row['test_id'][4:])
        top+= [i for i,r in enumerate(originals) if abs(int(r['test_id'][4:])-serial)<=5]
        matches=[]
        for i in dict.fromkeys(top):
            match=compare(data[i],b)
            if match: matches.append(dict(original_id=originals[i]['original_id'],votes=votes[i],**match))
        matches.sort(key=lambda m:(m['strong'],m['pixel_correlation'],m['inliers']),reverse=True)
        strong=[m for m in matches if m['strong']]
        result=dict(test_id=row['test_id'],round=int(row['round']),accepted=len(strong)==1,
                    candidates=matches,original_id=strong[0]['original_id'] if len(strong)==1 else None)
        write(out/'comparisons'/f"{row['test_id']}.json",result)
        results.append(result)
        if position%25==0: print(f'Audited {position}/{len(targets)}, strong unique {sum(r["accepted"] for r in results)}',flush=True)
    summary=dict(created_at=now(),method='SIFT retrieval over every original; RANSAC alignment; full-frame and 3x3 pixel correlation',
        script=evidence(Path(__file__)),mapping=evidence(base/'test_to_original_mapping.csv'),
        total=len(results),accepted=sum(r['accepted'] for r in results),
        unresolved=[r['test_id'] for r in results if not r['accepted']],results=results,
        human_review_claimed=False,training_authorized=False)
    write(out/'audit.json',summary)
    print({k:v for k,v in summary.items() if k!='results'},flush=True)


def publish(base,out):
    audit_path=out/'audit.json'; audit_data=read(audit_path)
    checked_evidence(audit_data['mapping']); checked_evidence(audit_data['script'])
    rows=csv_read(base/'test_to_original_mapping.csv')
    index={r['test_id']:r for r in rows}; originals={r['original_id']:r for r in rows if r['original_id']}
    for result in audit_data['results']:
        if not result['accepted']: continue
        row=index[result['test_id']]; original=originals[result['original_id']]
        if row['original_id']: raise ValueError('Existing mapping must not change')
        for k in ('original_id','original_sha256','original_path','group_id','group_verified','annotation_path','annotation_sha256'):
            row[k]=original[k]
        proof=dict(relationship='derived_from',reviewer='Codex computational geometric/pixel verification; not human annotation approval',
            reviewed_at=now(),source_reference=str(audit_path),audit=evidence(audit_path),
            comparison=evidence(out/'comparisons'/f"{row['test_id']}.json"),
            **{k:row[k] for k in ('test_id','original_id','test_sha256','original_sha256')})
        proof_path=out/'proofs'/f"{row['test_id']}.json"; write(proof_path,proof)
        row.update(evidence='unique_geometric_full_frame_pixel_match',mapping_review_path=str(proof_path),mapping_review_sha256=digest(proof_path))
    candidate=out/'reviewed_mapping.csv'
    csv_write(candidate,rows,list(dict.fromkeys(k for row in rows for k in row)))
    return revise_mapping(base,candidate)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['audit','publish'])
    parser.add_argument('--workspace',type=Path,default=BASE)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    if args.action=='audit': audit(args.workspace,args.output,args.limit)
    else: print(publish(args.workspace,args.output))


if __name__=='__main__': main()
