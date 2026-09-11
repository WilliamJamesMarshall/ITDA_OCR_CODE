"""Alternative model on automatically selected first-pass development boxes only.

This is a recognition experiment, not a production or accuracy certification.
"""
import json
import sys
from pathlib import Path
import time
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src.pipeline import _load_bgr
from src.date_extraction import OCRLine,select_date
from src.line_recovery import recover_lines,recovery_targets
from src.recognition_evidence import CTCEvidence


def main():
    from paddlex import create_model
    model=create_model('en_PP-OCRv5_mobile_rec',model_dir=str(OUT/'en-model'),device='cpu',cpu_threads=4,enable_mkldnn=True)._predictor
    def recognize(crops):
        decoder=model.post_op;evidence=CTCEvidence(decoder);model.post_op=evidence
        try:results=list(model(crops))
        finally:model.post_op=decoder
        aligned=len(results)==len(evidence.rows) and all(r['rec_text']==e[0] for r,e in zip(results,evidence.rows))
        return [(r['rec_text'],float(r['rec_score']),evidence.rows[i][1] if aligned else ()) for i,r in enumerate(results)]
    records=json.loads((OUT/'live.json').read_text(encoding='utf8'))['rows']
    outputs=[]
    for row in records:
        first=[OCRLine(o['text'],o['score'],o['local_box'],source=o['source'],variant=o['variant'])
               for o in row['after']['trace']['observations'] if o['pass_id']=='p001' and o['recognition_state']=='recognized']
        if not recovery_targets(first):continue
        active,obs,decisions,seconds=recover_lines(_load_bgr(Path(row['path'])),first,recognize)
        selected=select_date(active,final=True)
        item=dict(id=row['current_id'],expected=row['expected'],previous=row['after']['value'],value=selected.final_date,seconds=seconds,
                  decisions=decisions,observations=[dict(text=o.text,score=o.score,mean=o.date_digit_score,minimum=o.date_digit_min_score,box=o.box) for o in obs])
        outputs.append(item)
        print(json.dumps(item,ensure_ascii=False),flush=True)
    (OUT/'english_auto_probe.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
