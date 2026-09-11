"""Local title-guided crops on pre-existing development failures only."""
import json
from pathlib import Path
import sys
import time
import cv2

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.pipeline import PaddleOCRBackend,PipelineConfig,_load_bgr


def main():
    backend=PaddleOCRBackend(PipelineConfig())
    rows=json.loads((ROOT/'artifacts/structural-integration-20260911/live_result.json').read_text(encoding='utf-8'))['rows']
    for row in rows:
        if row['current_id'] not in {'003355','003531'}:
            continue
        image=_load_bgr(Path(row['path']))
        labels=[o for o in row['after']['trace']['observations'] if o['pass_id']=='p001' and o['text']=='까지']
        for label in labels:
            x1,y1,x2,y2=label['local_box']; h=y2-y1
            bounds=(max(0,int(x1-12*h)),max(0,int(y1-2*h)),min(image.shape[1],int(x2+h)),min(image.shape[0],int(y2+h)))
            left,top,right,bottom=bounds
            crop=image[top:bottom,left:right]
            for mode in ('original','erode','blur'):
                view=crop
                if mode=='erode':view=cv2.erode(view,cv2.getStructuringElement(cv2.MORPH_RECT,(2,2)))
                if mode=='blur':view=cv2.GaussianBlur(view,(3,3),.8)
                view=cv2.resize(view,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
                start=time.perf_counter()
                lines=backend.recognize(view,detector='mobile',variant='role-roi')
                print(row['current_id'],mode,bounds,time.perf_counter()-start,[(l.text,l.score) for l in lines],flush=True)


if __name__=='__main__':main()
