"""Pixel-component date-row feasibility inside title-guided development ROIs."""
import json
from pathlib import Path
import sys
import cv2
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.pipeline import PaddleOCRBackend,PipelineConfig,_load_bgr


def main():
    backend=PaddleOCRBackend(PipelineConfig())
    rows=json.loads((ROOT/'artifacts/structural-integration-20260911/live_result.json').read_text(encoding='utf-8'))['rows']
    for row in rows:
        if row['current_id'] not in {'003355','003531'}:continue
        image=_load_bgr(Path(row['path']))
        label=next(o for o in row['after']['trace']['observations'] if o['pass_id']=='p001' and o['text']=='까지')
        x1,y1,x2,y2=label['local_box']; h=y2-y1
        left,top,right,bottom=max(0,int(x1-12*h)),max(0,int(y1-2*h)),int(x1),min(image.shape[0],int(y2+h))
        crop=image[top:bottom,left:right]
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        bright=cv2.inRange(gray,170,255)
        cs,_=cv2.findContours(bright,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        panels=[cv2.boundingRect(c) for c in cs if cv2.contourArea(c)>2000]
        print(row['current_id'],'panels',panels,flush=True)
        if panels:
            px,py,pw,ph=max(panels,key=lambda b:b[2]*b[3])
            crop=crop[py+5:py+ph-5,px+5:px+pw-5]; left+=px+5;top+=py+5
            gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        binary=cv2.inRange(gray,0,120)
        joined=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(55,3)))
        contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        boxes=[]; crops=[]
        for c in contours:
            x,y,w,hh=cv2.boundingRect(c)
            if w<80 or hh<8 or hh>h*1.4 or w/hh<4:continue
            boxes.append((left+x,top+y,w,hh))
            crops.append(crop[max(0,y-3):min(crop.shape[0],y+hh+3),max(0,x-3):min(crop.shape[1],x+w+3)])
        if crops:
            print(row['current_id'],list(zip(boxes,backend.recognize_crops(crops))),flush=True)
            for k in ((2,2),(2,1),(1,2)):
                altered=[cv2.erode(c,cv2.getStructuringElement(cv2.MORPH_RECT,k)) for c in crops]
                print(row['current_id'],k,[(r[0],r[1]) for r in backend.recognize_crops(altered)],flush=True)
            for scale in (.5,.7):
                altered=[cv2.resize(c,None,fx=scale,fy=1,interpolation=cv2.INTER_AREA) for c in crops]
                print(row['current_id'],scale,[(r[0],r[1]) for r in backend.recognize_crops(altered)],flush=True)


if __name__=='__main__':main()
