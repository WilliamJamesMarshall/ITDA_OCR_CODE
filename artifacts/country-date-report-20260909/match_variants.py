"""Conservative geometric/pixel check of neighbouring augmentation variants.

Only propagates review candidates, never claims a new human verification.
"""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
from PIL import Image, ImageOps

BASE=Path(__file__).parent
SOURCE=Path('C:/ITDA_OCR_CODE/상품사진입니다')
FILES={int(p.stem):p for p in SOURCE.iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png'}}
cv2.setNumThreads(1)

def features(number):
 with Image.open(FILES[number]) as im:
  im=ImageOps.exif_transpose(im).convert('L')
  im.thumbnail((640,640))
  gray=np.asarray(im).copy()
 keypoints,desc=cv2.ORB_create(nfeatures=1200).detectAndCompute(gray,None)
 return number,(gray,keypoints,desc)

def match(pair):
 a,b=pair
 ga,ka,da=cache[a]; gb,kb,db=cache[b]
 if da is None or db is None:return None
 matches=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da,db,k=2)
 good=[m[0] for m in matches if len(m)==2 and m[0].distance<.70*m[1].distance]
 if len(good)<70:return None
 pa=np.float32([ka[m.queryIdx].pt for m in good]);pb=np.float32([kb[m.trainIdx].pt for m in good])
 h,inliers=cv2.findHomography(pa,pb,cv2.RANSAC,2.5)
 if h is None or int(inliers.sum())<65 or inliers.mean()<.8:return None
 shape=(gb.shape[1],gb.shape[0])
 warped=cv2.warpPerspective(ga,h,shape)
 mask=cv2.warpPerspective(np.full(ga.shape,255,np.uint8),h,shape)>250
 mask &= (gb>12)&(warped>12)
 mask=cv2.erode(mask.astype(np.uint8),np.ones((7,7),np.uint8)).astype(bool)
 if mask.mean()<.55:return None
 aa=cv2.GaussianBlur(warped,(5,5),0)[mask]
 bb=cv2.GaussianBlur(gb,(5,5),0)[mask]
 corr=float(np.corrcoef(aa,bb)[0,1])
 if corr<.985:return None
 return {'a':f'{a:06d}','b':f'{b:06d}','inliers':int(inliers.sum()),
         'pixel_correlation':round(corr,6),'overlap':round(float(mask.mean()),4)}

if __name__=='__main__':
 rows=json.loads((BASE/'country_screening.json').read_text(encoding='utf-8'))
 known={int(r['image_id']) for r in rows if r['country']!='미확정'}
 pairs=sorted({(min(i,j),max(i,j)) for i in known for j in [i-1,i+1] if 1<=j<=3352})
 ids=sorted({i for p in pairs for i in p})
 with ThreadPoolExecutor(max_workers=4) as pool:cache=dict(pool.map(features,ids))
 with ThreadPoolExecutor(max_workers=4) as pool:links=[r for r in pool.map(match,pairs) if r]
 (BASE/'verified_variant_links.json').write_text(json.dumps(links,indent=2),encoding='utf-8')
 print('Candidate pairs',len(pairs),'strict matches',len(links))
