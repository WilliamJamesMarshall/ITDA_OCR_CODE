"""Additional full-frame RGB/HSV augmentation reconstruction for withheld candidates."""
import argparse
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read
from scripts.grouped_rounds import now, evidence, checked_evidence


def rgb(path):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB')
        image.thumbnail((720,720),Image.Resampling.LANCZOS)
        return np.asarray(image).copy()


def score_pixels(prediction,target,mask):
    prediction=cv2.GaussianBlur(prediction,(5,5),0)
    target=cv2.GaussianBlur(target,(5,5),0)
    error=np.abs(prediction.astype(float)-target).mean(axis=2)
    gray=cv2.cvtColor(target,cv2.COLOR_RGB2GRAY)
    texture=(np.abs(cv2.Sobel(gray,cv2.CV_32F,1,0))+np.abs(cv2.Sobel(gray,cv2.CV_32F,0,1)))>30
    texture &= mask
    cells=[]
    for ys in np.array_split(np.arange(target.shape[0]),3):
        for xs in np.array_split(np.arange(target.shape[1]),3):
            region=np.ix_(ys,xs);m=mask[region]
            if m.sum()>2000:cells.append(float((error[region][m]<=8).mean()))
    rate=float((error[mask]<=8).mean());median=float(np.median(error[mask]))
    textured=float((error[texture]<=10).mean()) if texture.any() else 0
    strong=bool(mask.mean()>=.65 and rate>=.94 and median<=2 and texture.mean()>=.025
        and textured>=.9 and len(cells)>=7 and sum(c>=.85 for c in cells)>=7 and min(cells)>=.6)
    return dict(strong=strong,pixel_within_8_fraction=rate,median_rgb_error=median,
        p95_rgb_error=float(np.percentile(error[mask],95)),textured_within_10_fraction=textured,
        textured_fraction=float(texture.mean()),overlap=float(mask.mean()),cell_within_8_fractions=cells)


def reconstruct_color(original,target,h):
    size=target.shape[1::-1]; warped=cv2.warpPerspective(original,h,size)
    mask=cv2.warpPerspective(np.full(original.shape[:2],255,np.uint8),h,size)>250
    mask=cv2.erode(mask.astype(np.uint8),np.ones((9,9),np.uint8)).astype(bool)
    if mask.sum()<10000:return []
    models=[]
    fit=mask & (warped.min(axis=2)>20)&(warped.max(axis=2)<235)&(target.min(axis=2)>20)&(target.max(axis=2)<235)
    if fit.sum()>1000:
        offsets=np.median(target[fit].astype(float)-warped[fit],axis=0)
        if np.max(np.abs(offsets))<=100:
            pred=np.clip(warped.astype(float)+offsets,0,255).astype(np.uint8)
            models.append(dict(model='RGB_add',offsets=offsets.tolist(),**score_pixels(pred,target,mask)))
    a=cv2.cvtColor(warped,cv2.COLOR_RGB2HSV);b=cv2.cvtColor(target,cv2.COLOR_RGB2HSV)
    fit=mask&(a[:,:,2]>20)&(a[:,:,2]<235)&(b[:,:,2]>20)&(b[:,:,2]<235)
    if fit.sum()>1000:
        offset=float(np.median(b[:,:,2][fit].astype(float)-a[:,:,2][fit]))
        if abs(offset)<=100:
            pred=a.copy();pred[:,:,2]=np.clip(a[:,:,2].astype(float)+offset,0,255).astype(np.uint8)
            models.append(dict(model='HSV_V_add',offset=offset,
                **score_pixels(cv2.cvtColor(pred,cv2.COLOR_HSV2RGB),target,mask)))
    return sorted(models,key=lambda m:(m['strong'],m['pixel_within_8_fraction']),reverse=True)


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
            for m in row['candidates']:
                m=dict(m)
                if m['inliers']>=25 and m['inlier_ratio']>=.45 and m['target_feature_coverage']>=.1:
                    models=reconstruct_color(rgb(originals[m['original_id']]['original_path']),target,
                        np.asarray(m['homography_original_to_test']))
                    m.update(color_reconstruction=models,strong=any(p['strong'] for p in models))
                matches.append(m)
            strong=[m for m in matches if m['strong']]
            row.update(candidates=matches,accepted=len(strong)==1,original_id=strong[0]['original_id'] if len(strong)==1 else None)
        results.append(row);write(out/'comparisons'/f"{row['test_id']}.json",row)
    summary=dict(audit,created_at=now(),results=results,accepted=sum(r['accepted'] for r in results),
        unresolved=[r['test_id'] for r in results if not r['accepted']],
        preceding_audit=evidence(source/'audit.json'),color_script=evidence(Path(__file__)))
    write(out/'audit.json',summary)
    print(dict(accepted=summary['accepted'],unresolved=summary['unresolved']),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','source','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();refine(a.workspace,a.source,a.output)


if __name__=='__main__':main()
