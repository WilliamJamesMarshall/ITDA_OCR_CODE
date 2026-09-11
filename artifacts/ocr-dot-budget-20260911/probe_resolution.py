"""Same development image at nearby resolutions; not independent accuracy data."""
import json
from pathlib import Path
import sys
from unittest.mock import patch
import cv2
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.pipeline import PaddleOCRBackend,PipelineConfig,_load_bgr,predict_image


def main():
    path=ROOT/'추가수집데이터/003355.jpg'
    image=_load_bgr(path)
    config=PipelineConfig(progress_every=0)
    backend=PaddleOCRBackend(config)
    rows=[]
    for scale in (.85,1.15):
        resized=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)
        with patch('src.pipeline._load_bgr',return_value=resized):
            result=predict_image(path,backend,config)
        row=dict(scale=scale,value=result.final_date,passes=result.passes,trace=result.trace)
        rows.append(row)
        print(json.dumps({k:v for k,v in row.items() if k!='trace'},ensure_ascii=False),flush=True)
    (Path(__file__).parent/'resolution_probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
