"""Bounded dot-print/low-contrast line proposals for images missed by base OCR."""
import sys
import argparse
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann
from scripts.build_annotation_drafts import enrich
from scripts.refine_annotation_drafts import plausible_date, refine


def proposals(image):
    import cv2
    import numpy as np
    image=image.convert('RGB')
    scale=min(1,1600/max(image.size))
    small=image.resize((round(image.width*scale),round(image.height*scale)))
    gray=np.asarray(small.convert('L'))
    blackhat=cv2.morphologyEx(gray,cv2.MORPH_BLACKHAT,cv2.getStructuringElement(cv2.MORPH_RECT,(19,7)))
    mask=cv2.threshold(blackhat,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    joined=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(25,5)))
    contours=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    boxes=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if not (12<=h<=120 and 70<=w<=small.width*.95 and 2.5<=w/h<=25):
            continue
        density=cv2.countNonZero(mask[y:y+h,x:x+w])/(w*h)
        if not .05<=density<=.6:
            continue
        boxes.append((w*h,x,y,w,h))
    return [[[max(0,(x-4)/scale),max(0,(y-4)/scale)],
             [min(image.width,(x+w+4)/scale),max(0,(y-4)/scale)],
             [min(image.width,(x+w+4)/scale),min(image.height,(y+h+4)/scale)],
             [max(0,(x-4)/scale),min(image.height,(y+h+4)/scale)]]
            for _,x,y,w,h in sorted(boxes,reverse=True)[:12]]


def main(limit=None):
    import cv2
    import numpy as np
    from src.pipeline import PaddleOCRBackend, PipelineConfig
    backend=None
    report=dict(processed=0,images_recovered=0,failures=[],human_approvals_created=0)
    for path in sorted((ann.OUT/'records').glob('*.json')):
        record=ann.read(path)
        if record['review']['status']!='pending' or record['review']['reviewer'] or record.get('line_proposal_pass') or any(r['kind']=='date_line' for r in record['regions']):
            continue
        if limit is not None and report['processed']>=limit:
            break
        try:
            with ann.Image.open(ann.source_path(record)) as image:
                polygons=proposals(image)
                tiles=[cv2.cvtColor(np.asarray(ann.crop(image,p)),cv2.COLOR_RGB2BGR) for p in polygons]
            candidates=[]
            if tiles:
                if backend is None:
                    backend=PaddleOCRBackend(PipelineConfig(cpu_threads=4))
                english=backend.recognize_date_crops(tiles)
                korean=backend.recognize_crops(tiles)
                for i,(polygon,en,ko) in enumerate(zip(polygons,english,korean)):
                    valid=[(text,score) for text,score,_ in (en,ko) if plausible_date(text)]
                    if valid:
                        text,score=max(valid,key=lambda x:x[1])
                        candidates.append(ann.new_region(f'recovery_{i:03d}','date_line',polygon,text,
                            dict(type='automatic_ocr_candidate',method='morphological_line_crop_dual_recognizer',score=float(score),
                                alternatives=[dict(text=r[0],score=float(r[1])) for r in (en,ko)],created_at=ann.now())))
            record['regions'].extend(candidates)
            record['line_proposal_pass']=dict(created_at=ann.now(),proposals=len(polygons),date_candidates=len(candidates))
            if candidates:
                record.pop('quality_draft_measurements',None)
                report['images_recovered']+=1
            # Existing source strings and dates stay untouched.
            enrich(record)
            refine(record)
            ann.save_review(record['image_id'],record,record['revision'],False)
            report['processed']+=1
        except Exception as exc:
            report['failures'].append(dict(image_id=record['image_id'],error=str(exc)))
        if report['processed'] and report['processed']%20==0:
            print(report,flush=True)
    ann.write(ann.OUT/'line_proposal_report.json',report)
    print(report,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int)
    main(parser.parse_args().limit)
