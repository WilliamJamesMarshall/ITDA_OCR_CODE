"""Development-only conditional second recognizer; no production configuration change."""
import json
import sys
from pathlib import Path
from dataclasses import replace
import time
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src import pipeline,line_recovery
from src.date_extraction import _link_roles,parse_dates
from src.recognition_evidence import CTCEvidence


def main():
    model=None
    def recognize(crops):
        nonlocal model
        if model is None:
            from paddlex import create_model
            model=create_model('en_PP-OCRv5_mobile_rec',model_dir=str(OUT/'en-model'),device='cpu',cpu_threads=4,enable_mkldnn=True)._predictor
        decoder=model.post_op;evidence=CTCEvidence(decoder);model.post_op=evidence
        try:results=list(model(crops))
        finally:model.post_op=decoder
        aligned=len(results)==len(evidence.rows) and all(r['rec_text']==e[0] for r,e in zip(results,evidence.rows))
        output=[]
        for i,r in enumerate(results):
            text=r['rec_text'];chars=evidence.rows[i][1] if aligned else ()
            mean,minimum=line_recovery._digit_evidence(text,chars)
            # A competing recognizer must provide aligned, strong character
            # evidence; normal row confidence alone cannot admit a replacement.
            score=float(r['rec_score']) if mean is not None and mean>=.95 and minimum>=.8 else 0.
            output.append((text,score,chars))
        return output
    original=line_recovery.recover_lines
    def recover(image,lines,primary):
        active,obs,decisions,seconds=original(image,lines,primary)
        # Do not disturb successful primary recovery or clear complete dates.
        pending=[i for i in line_recovery.recovery_targets(lines)
                 if active[i].text==lines[i].text and
                 (not parse_dates(lines[i].text) or any(p.repaired for p in parse_dates(lines[i].text)))]
        if not pending:return active,obs,decisions,seconds
        # Retain all labels while restricting OCR targets to the pending rows.
        saved=line_recovery.recovery_targets
        line_recovery.recovery_targets=lambda _:pending
        try:other,raw,extra,elapsed=original(image,active,recognize)
        finally:line_recovery.recovery_targets=saved
        # Store the actual model scores (probe admission score was zeroed for
        # rejected reads); probe only, not a production confidence record.
        raw=[replace(o,variant=o.variant+'-english') for o in raw]
        return other,obs+raw,decisions+extra,seconds+elapsed
    pipeline.recover_lines=recover
    rows=json.loads((OUT/'live.json').read_text(encoding='utf8'))['rows']
    config=pipeline.PipelineConfig(progress_every=0)
    backend=pipeline.PaddleOCRBackend(config)
    output=[]
    for row in rows:
        result=pipeline.predict_image(Path(row['path']),backend,config)
        item=dict(id=row['current_id'],expected=row['expected'],previous=row['after']['value'],value=result.final_date or 'NONE',seconds=result.elapsed_seconds,trace=result.trace)
        output.append(item)
        print(json.dumps({k:v for k,v in item.items() if k!='trace'},ensure_ascii=False),flush=True)
        (OUT/'english_pipeline_probe.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
