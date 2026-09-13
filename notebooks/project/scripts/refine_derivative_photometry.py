"""Verify stored geometric candidates by reconstructing brightness-shifted pixels."""
import argparse
from pathlib import Path
import cv2
import numpy as np
from scripts.resolve_original_derivatives import gray
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read
from scripts.grouped_rounds import evidence, checked_evidence, now


def reconstruct(original,target,h):
    size=target.shape[::-1]
    warped=cv2.warpPerspective(original,h,size)
    mask=cv2.warpPerspective(np.full(original.shape,255,np.uint8),h,size)>250
    mask=cv2.erode(mask.astype(np.uint8),np.ones((9,9),np.uint8)).astype(bool)
    fit=mask&(warped>20)&(warped<235)&(target>20)&(target<235)
    if fit.sum()<5000: return dict(strong=False,reason='Insufficient unclipped pixels')
    x=warped[fit].astype(float); y=target[fit].astype(float)
    valid=np.ones(len(x),bool)
    for _ in range(4):
        if valid.sum()<5000 or np.std(x[valid])<12: return dict(strong=False,reason='Insufficient intensity variation')
        slope=float(np.cov(x[valid],y[valid],ddof=0)[0,1]/np.var(x[valid]))
        offset=float(np.median(y[valid]-slope*x[valid]))
        valid=np.abs(y-(slope*x+offset))<=6
    if not .5<slope<1.6 or abs(offset)>100: return dict(strong=False,reason='Implausible photometric transform')
    prediction=np.clip(warped.astype(float)*slope+offset,0,255).astype(np.uint8)
    prediction=cv2.GaussianBlur(prediction,(5,5),0)
    target_blur=cv2.GaussianBlur(target,(5,5),0)
    error=np.abs(prediction.astype(float)-target_blur)
    matched=(error<=8)&mask
    texture=(np.abs(cv2.Sobel(target_blur,cv2.CV_32F,1,0))+np.abs(cv2.Sobel(target_blur,cv2.CV_32F,0,1)))>30
    texture &= mask & (target_blur>15)&(target_blur<240)
    texture_fraction=float(texture.mean())
    texture_match=float((error[texture]<=10).mean()) if texture.any() else 0
    cells=[]
    for ys in np.array_split(np.arange(target.shape[0]),3):
        for xs in np.array_split(np.arange(target.shape[1]),3):
            region=np.ix_(ys,xs); valid_mask=mask[region]
            if valid_mask.sum()>2000: cells.append(float((error[region][valid_mask]<=8).mean()))
    rate=float(matched.sum()/mask.sum())
    median=float(np.median(error[mask]));p95=float(np.percentile(error[mask],95))
    strong=bool(mask.mean()>=.65 and rate>=.94 and median<=2 and texture_fraction>=.025
                and texture_match>=.9 and len(cells)>=7 and sum(c>=.85 for c in cells)>=7 and min(cells)>=.6)
    return dict(strong=strong,gain=slope,offset=offset,overlap=float(mask.mean()),
        pixel_within_8_fraction=rate,median_pixel_error=median,p95_pixel_error=p95,
        textured_fraction=texture_fraction,textured_within_10_fraction=texture_match,cell_within_8_fractions=cells)


def refine(base,source,out):
    original_audit=read(source/'audit.json')
    checked_evidence(original_audit['mapping']); checked_evidence(original_audit['script'])
    out.mkdir(parents=True,exist_ok=False)
    rows=csv_read(base/'test_to_original_mapping.csv')
    originals={r['original_id']:r for r in rows if r['original_id']}
    results=[]
    for position,old in enumerate(original_audit['results'],1):
        row=dict(old);matches=[]
        target=gray(str(ROOT/'테스트용데이터'/(row['test_id']+'.jpg')))
        for candidate in row['candidates']:
            match=dict(candidate)
            if not candidate['strong'] and candidate['inliers']>=30 and candidate['inlier_ratio']>=.6 and candidate['target_feature_coverage']>=.2:
                orig=gray(originals[candidate['original_id']]['original_path'])
                proof=reconstruct(orig,target,np.asarray(candidate['homography_original_to_test']))
                match.update(photometric_reconstruction=proof,strong=proof['strong'])
            matches.append(match)
        matches.sort(key=lambda m:(m['strong'],m['inliers']),reverse=True)
        strong=[m for m in matches if m['strong']]
        row.update(candidates=matches,accepted=len(strong)==1,original_id=strong[0]['original_id'] if len(strong)==1 else None)
        results.append(row);write(out/'comparisons'/f"{row['test_id']}.json",row)
        if position%100==0: print(f'Reconstructed {position}, accepted {sum(r["accepted"] for r in results)}',flush=True)
    summary=dict(original_audit,created_at=now(),results=results,accepted=sum(r['accepted'] for r in results),
        unresolved=[r['test_id'] for r in results if not r['accepted']],
        geometric_audit=evidence(source/'audit.json'),photometry_script=evidence(Path(__file__)),
        method=original_audit['method']+'; robust affine brightness and clipping pixel reconstruction')
    write(out/'audit.json',summary)
    print(dict(total=summary['total'],accepted=summary['accepted'],unresolved=summary['unresolved']),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();refine(a.workspace,a.source,a.output)


if __name__=='__main__': main()
