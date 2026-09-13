"""Dense feature verification of withheld matches without lowering pixel thresholds."""
import argparse
from pathlib import Path
import cv2
import numpy as np
from scripts.verify_derivative_color import rgb, reconstruct_color
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read
from scripts.grouped_rounds import evidence, checked_evidence, now


def precise(a,b):
    sift=cv2.SIFT_create(nfeatures=2500,contrastThreshold=.02)
    ka,da=sift.detectAndCompute(cv2.cvtColor(a,cv2.COLOR_RGB2GRAY),None)
    kb,db=sift.detectAndCompute(cv2.cvtColor(b,cv2.COLOR_RGB2GRAY),None)
    if da is None or db is None: return []
    good=[p[0] for p in cv2.BFMatcher().knnMatch(db,da,k=2) if len(p)==2 and p[0].distance<.75*p[1].distance]
    if len(good)<25: return []
    ap=np.float32([ka[m.trainIdx].pt for m in good]);bp=np.float32([kb[m.queryIdx].pt for m in good])
    cv2.setRNGSeed(20260913)
    affine,amask=cv2.estimateAffine2D(ap,bp,method=cv2.RANSAC,ransacReprojThreshold=1,refineIters=50)
    homography,hmask=cv2.findHomography(ap,bp,cv2.RANSAC,1)
    results=[]
    for kind,h,mask in [('affine',np.vstack([affine,[0,0,1]]) if affine is not None else None,amask),
                        ('homography',homography,hmask)]:
        if h is None:continue
        valid=mask.ravel().astype(bool);count=int(valid.sum())
        coverage=float(cv2.contourArea(cv2.convexHull(bp[valid]))/(b.shape[0]*b.shape[1]))
        if count<25 or count/len(good)<.45 or coverage<.1:continue
        models=reconstruct_color(a,b,h)
        results.append(dict(geometry=kind,homography_original_to_test=h.tolist(),inliers=count,
            good_matches=len(good),inlier_ratio=count/len(good),target_feature_coverage=coverage,
            color_reconstruction=models,strong=any(p['strong'] for p in models)))
    return results


def refine(base,source,out):
    audit=read(source/'audit.json');checked_evidence(audit['mapping'])
    out.mkdir(parents=True,exist_ok=False)
    originals={r['original_id']:r for r in csv_read(base/'test_to_original_mapping.csv') if r['original_id']}
    results=[]
    for row in audit['results']:
        row=dict(row)
        if not row['accepted']:
            target=rgb(ROOT/'테스트용데이터'/(row['test_id']+'.jpg'))
            matches=[]
            for candidate in row['candidates']:
                match=dict(candidate)
                if candidate['inliers']>=12 and candidate['pixel_correlation']>=.8:
                    checks=precise(rgb(originals[candidate['original_id']]['original_path']),target)
                    match.update(precise_geometry=checks,strong=any(p['strong'] for p in checks))
                matches.append(match)
            strong=[m for m in matches if m['strong']]
            row.update(candidates=matches,accepted=len(strong)==1,original_id=strong[0]['original_id'] if len(strong)==1 else None)
        results.append(row);write(out/'comparisons'/f"{row['test_id']}.json",row)
    summary=dict(audit,created_at=now(),results=results,accepted=sum(r['accepted'] for r in results),
        unresolved=[r['test_id'] for r in results if not r['accepted']],preceding_audit=evidence(source/'audit.json'),
        precise_geometry_script=evidence(Path(__file__)))
    write(out/'audit.json',summary)
    print(dict(accepted=summary['accepted'],unresolved=summary['unresolved']),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','source','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();refine(a.workspace,a.source,a.output)


if __name__=='__main__':main()
