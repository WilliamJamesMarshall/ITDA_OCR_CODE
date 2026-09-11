"""Four visually reviewed development date spans; not automatic OCR accuracy.

Diagnostic polygons are normalized to the EXIF-oriented original. They are never
loaded by production, copied into final labels, or approved as training data.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.pipeline import PaddleOCRBackend, PipelineConfig, _load_bgr
from src.line_recovery import _digit_evidence, _signature

# Ordered TL, TR, BR, BL. These are approximate diagnostic date-only regions,
# not complete line/lot transcripts or claims of precise curved boundaries.
REGIONS = {
    '003507': [[.431, .277], [.706, .281], [.706, .304], [.431, .300]],
    '000090': [[.230, .498], [.645, .498], [.645, .575], [.230, .575]],
    '000191': [[.330, .495], [.742, .495], [.742, .578], [.330, .578]],
    '000210': [[.280, .428], [.668, .434], [.668, .461], [.280, .451]],
}


def main():
    live = json.loads((OUT/'live.json').read_text(encoding='utf8'))
    backend = PaddleOCRBackend(PipelineConfig())
    output = []
    for row in live['rows']:
        iid = row['current_id']
        if iid not in REGIONS:
            continue
        path = Path(row['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
        image = _load_bgr(path)
        h, w = image.shape[:2]
        polygon = np.float32(REGIONS[iid])*np.float32([w, h])
        a, b = np.floor(polygon.min(axis=0)).astype(int)
        c, d = np.ceil(polygon.max(axis=0)).astype(int)
        crop = image[b:d, a:c]
        rw = int(max(np.linalg.norm(polygon[1]-polygon[0]), np.linalg.norm(polygon[2]-polygon[3])))
        rh = int(max(np.linalg.norm(polygon[3]-polygon[0]), np.linalg.norm(polygon[2]-polygon[1])))
        transform = cv2.getPerspectiveTransform(polygon, np.float32([[0,0],[rw-1,0],[rw-1,rh-1],[0,rh-1]]))
        rectified = cv2.warpPerspective(image, transform, (rw, rh))
        gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.cvtColor(cv2.createCLAHE(clipLimit=2.,tileGridSize=(4,4)).apply(gray),cv2.COLOR_GRAY2BGR)
        variants = [('axis-box',crop), ('quad',rectified), ('quad-contrast',enhanced),
                    ('quad-half-width',cv2.resize(rectified,None,fx=.5,fy=1,interpolation=cv2.INTER_AREA))]
        for variant, pixels in variants:
            ok, encoded = cv2.imencode('.png', pixels)
            assert ok
            (OUT/f'oracle-{iid}-{variant}.png').write_bytes(encoded.tobytes())
        reads = []
        for name, recognize in [('primary',backend.recognize_crops), ('english',backend.recognize_date_crops)]:
            start = time.perf_counter()
            results = recognize([v[1] for v in variants])
            elapsed = time.perf_counter()-start
            for (variant,_), (text,score,chars) in zip(variants,results):
                mean, minimum = _digit_evidence(text,chars)
                item = dict(model=name,view=variant,text=text,score=score,date_digit_mean=mean,
                            date_digit_min=minimum,signature=_signature(text),batch_seconds=elapsed)
                reads.append(item)
                print(json.dumps(dict(id=iid,**item),ensure_ascii=False),flush=True)
        output.append(dict(id=iid,path=str(path),sha256=row['sha256'],normalized_polygon=REGIONS[iid],
                           original_size=[w,h],frozen_expected=row['expected'],reads=reads,training_approved=False))
    assert len(output)==4
    result = dict(scope='Manual date-span inputs for module diagnosis only; NOT automatic detection or final accuracy',
                  production_code_sha256=live['code_sha256'],rows=output)
    (OUT/'region_oracle_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
