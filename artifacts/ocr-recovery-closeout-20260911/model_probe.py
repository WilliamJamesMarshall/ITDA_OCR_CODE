"""Oracle development date rows: compare recognition, NOT end-to-end accuracy."""
import json
from pathlib import Path
import sys
import time
import cv2
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src.pipeline import _load_bgr
from src.recognition_evidence import CTCEvidence


def main():
    from paddlex import create_model
    started=time.perf_counter()
    model=create_model('en_PP-OCRv5_mobile_rec',model_dir=str(OUT/'en-model'),device='cpu',cpu_threads=4,enable_mkldnn=True)
    print('init',time.perf_counter()-started,flush=True)
    # Visually reviewed approximate original-normalized date regions only.
    # Never loaded by the production pipeline or used to change final labels.
    annotations={
        '003355':[(.32,.59,.64,.62),(.32,.62,.66,.65)],
        '003489':[(.145,.515,.442,.576),(.155,.573,.446,.633)],
        '003486':[(.39,.53,.69,.605),(.39,.585,.69,.654)],
        '000034':[(.25,.56,.706,.611)],
        '000061':[(.172,.562,.637,.637)],
        '000090':[(.232,.489,.643,.579)],
        '000202':[(.386,.514,.631,.544)],
        '000305':[(.23,.368,.669,.418)],
    }
    outputs=[]
    for iid,boxes in annotations.items():
        path=ROOT/('추가수집데이터' if int(iid)>3352 else '상품사진입니다')/(iid+'.jpg')
        image=_load_bgr(path); h,w=image.shape[:2]
        crops=[];jobs=[]
        for box in boxes:
            x1,y1,x2,y2=[int(v*s) for v,s in zip(box,(w,h,w,h))]
            crop=image[y1:y2,x1:x2]
            for scale in (1.,.45):
                crops.append(cv2.resize(crop,None,fx=scale,fy=1,interpolation=cv2.INTER_AREA));jobs.append((box,scale))
        decoder=model.post_op; evidence=CTCEvidence(decoder);model.post_op=evidence
        try: results=list(model(crops))
        finally:model.post_op=decoder
        for job,result in zip(jobs,results):
            item=dict(id=iid,box=job[0],scale=job[1],text=result['rec_text'],score=float(result['rec_score']))
            outputs.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    (OUT/'model_probe.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
