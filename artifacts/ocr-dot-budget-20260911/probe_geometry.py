"""Bounded development-only row geometry probe; never changes images/labels."""
import json
from pathlib import Path
import sys
import cv2
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.pipeline import PaddleOCRBackend,PipelineConfig,_load_bgr
from src.line_recovery import _digit_evidence


def main():
    backend=PaddleOCRBackend(PipelineConfig())
    # Regions observed from pixel components, NOT used as production exceptions.
    image=_load_bgr(ROOT/'추가수집데이터/003355.jpg')
    rows=[]
    for bounds in [(286,749,522,764),(286,768,550,784)]:
        x1,y1,x2,y2=bounds
        jobs=[]; crops=[]
        for pad in (1,3,5):
            for scale in (.4,.45,.5,.55,.6):
                crop=image[y1-pad:y2+pad,x1-pad:x2+pad]
                crops.append(cv2.resize(crop,None,fx=scale,fy=1,interpolation=cv2.INTER_AREA))
                jobs.append(dict(bounds=bounds,pad=pad,scale=scale))
        for job,result in zip(jobs,backend.recognize_crops(crops)):
            text,score,chars=result
            mean,minimum=_digit_evidence(text,chars)
            row=dict(**job,text=text,score=score,date_mean=mean,date_min=minimum,character_scores=chars)
            rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
    (Path(__file__).parent/'geometry_probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
