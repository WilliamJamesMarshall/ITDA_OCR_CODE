"""Development-only pixel row and native-aspect recognition probe."""
import json
import sys
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.pipeline import _load_bgr,PaddleOCRBackend,PipelineConfig
from src.date_extraction import OCRLine
from src.line_recovery import _digit_evidence


def rows(image,label):
    height,width=image.shape[:2]; x1,y1,x2,y2=label.box; h=y2-y1
    left,top=max(0,int(x1-12*h)),max(0,int(y1-2*h))
    right,bottom=min(width,int(x1)),min(height,int(y2+h))
    gray=cv2.cvtColor(image[top:bottom,left:right],cv2.COLOR_BGR2GRAY)
    contours,_=cv2.findContours(cv2.inRange(gray,170,255),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    panels=[cv2.boundingRect(c) for c in contours if cv2.contourArea(c)>1.5*h*h]
    if not panels:return [],{}
    px,py,pw,ph=max(panels,key=lambda b:b[2]*b[3]); inset=max(2,round(h*.14))
    contour=max((c for c in contours if cv2.contourArea(c)>1.5*h*h),key=lambda c:np.prod(cv2.boundingRect(c)[2:]))
    panel_mask=np.zeros_like(gray);cv2.drawContours(panel_mask,[contour],-1,255,-1)
    panel_mask=cv2.erode(panel_mask,cv2.getStructuringElement(cv2.MORPH_RECT,(2*inset+1,2*inset+1)))
    panel_mask=panel_mask[py+inset:py+ph-inset,px+inset:px+pw-inset]
    gray=gray[py+inset:py+ph-inset,px+inset:px+pw-inset]; left+=px+inset;top+=py+inset
    binary=cv2.bitwise_and(cv2.inRange(gray,0,120),panel_mask)
    joined=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(max(3,round(h*1.5)),1)))
    ys=np.flatnonzero(np.count_nonzero(joined,axis=1)>=2*h)
    if not len(ys):return [],dict(panels=panels)
    gaps=np.diff(ys); blank=gaps[gaps>1]-1
    gap_limit=max(2,round(h*.025))
    runs=np.split(ys,np.flatnonzero(gaps>gap_limit+1)+1)
    boxes=[]; candidates=[]
    for run in runs:
        a,b=int(run[0]),int(run[-1])+1
        xs=np.flatnonzero(np.any(binary[a:b],axis=0))
        if not len(xs):continue
        x,w=int(xs[0]),int(xs[-1]-xs[0]+1); rh=b-a
        candidates.append((left+x,top+a,left+x+w,top+b,w/rh))
        if w>=2*h and 8<=rh<=1.4*h and w/rh>=4:boxes.append((left+x,top+a,left+x+w,top+b))
    return boxes,dict(panels=panels,gaps=blank.tolist(),gap_limit=gap_limit,candidates=candidates)


def main():
    data=json.loads((Path(__file__).parent/'live_progress.json').read_text(encoding='utf8'))
    backend=None if '--geometry' in sys.argv else PaddleOCRBackend(PipelineConfig())
    if '--english' in sys.argv:
        from paddlex import create_model
        from src.recognition_evidence import CTCEvidence
        model=create_model('en_PP-OCRv5_mobile_rec',model_dir=str(Path(__file__).parent/'en-model'),device='cpu',cpu_threads=4,enable_mkldnn=True)
        print(type(model),list(vars(model)),flush=True)
        model=getattr(model,'_predictor',model)
        def recognize(crops):
            decoder=model.post_op;evidence=CTCEvidence(decoder);model.post_op=evidence
            try:result=list(model(crops))
            finally:model.post_op=decoder
            return [(r['rec_text'],float(r['rec_score']),evidence.rows[i][1]) for i,r in enumerate(result)]
        backend.recognize_crops=recognize
    output=[]
    for iid in ['003489','000080']:
        record=next(r for r in data if r['current_id']==iid)
        label=next(o for o in record['after']['trace']['observations'] if o['pass_id']=='p001' and o['text']=='까지')
        image=_load_bgr(Path(record['path']))
        boxes,debug=rows(image,OCRLine(label['text'],label['score'],label['local_box']))
        print(iid,boxes,debug,flush=True)
        if backend:
            crops=[]; jobs=[]
            for box in boxes:
                x1,y1,x2,y2=box; pad=max(3,round((y2-y1)*.3))
                crop=image[max(0,y1-pad):min(image.shape[0],y2+pad),max(0,x1-pad):min(image.shape[1],x2+pad)]
                ratio=(x2-x1)/(y2-y1)
                for scale in (min(1.,4.8/ratio),min(1.08,5.2/ratio)):
                    crops.append(cv2.resize(crop,None,fx=scale,fy=1,interpolation=cv2.INTER_AREA))
                    jobs.append((box,scale))
            for (box,scale),result in zip(jobs,backend.recognize_crops(crops)):
                mean,minimum=_digit_evidence(result[0],result[2])
                item=dict(id=iid,box=box,scale=scale,text=result[0],score=result[1],date_mean=mean,date_min=minimum)
                output.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    if backend:(Path(__file__).parent/('row_probe_en.json' if '--english' in sys.argv else 'row_probe.json')).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
