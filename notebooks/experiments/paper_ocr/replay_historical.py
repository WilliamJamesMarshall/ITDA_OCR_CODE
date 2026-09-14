"""Replay preserved round-1 inputs; report inherited and new failures separately."""
import argparse
import hashlib
import json
import sys
from dataclasses import fields
from pathlib import Path

BASE=Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
HISTORY=Path('C:/ITDA_OCR_WORKSPACE/sequential-8-rounds/remediation_12')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--code-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compare',type=Path)
    args=p.parse_args()
    sys.path.insert(0,str(args.code_root/'notebooks/project'))
    from src.date_extraction import OCRLine,select_date
    from src.budget_pipeline import output_selection
    from src.pipeline import PipelineConfig
    config=PipelineConfig()
    allowed={f.name for f in fields(OCRLine)}
    latest={}
    trace=HISTORY/'candidate_01/submission.csv.trace.jsonl'
    with trace.open(encoding='utf-8') as stream:
        for line in stream:
            event=json.loads(line)
            if event['kind']=='selector_input':
                latest[event['image_id']]=event
    predictions={}
    for image_id,event in latest.items():
        lines=[OCRLine(**{k:v for k,v in row.items() if k in allowed}) for row in event['lines']]
        selection=select_date(lines,final=event.get('final',False),context=config.date_context,
                              product_rules=config.product_date_rules)
        predictions[image_id]=output_selection(selection).final_date or 'NONE'
    assert len(predictions)==216
    # Labels are read after prediction. A legacy failure is not silently cleared.
    detail=json.loads((HISTORY/'comparison.json').read_text(encoding='utf-8'))['detail']
    protected=[r for r in detail if r['after_correct']]
    failed=[r['image_id'] for r in protected if predictions[r['image_id']]!=r['expected']]
    report=dict(scope='Last accepted OCR-state replay; not fresh OCR or round-1 qualification',
        code_root=str(args.code_root),source_sha256=hashlib.sha256(
            (args.code_root/'notebooks/project/src/date_extraction.py').read_bytes()).hexdigest(),
        images=216,protected_images=len(protected),failed_protected=failed,predictions=predictions,
        trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())
    if args.compare:
        baseline=json.loads(args.compare.read_text(encoding='utf-8'))
        report['new_failures']=sorted(set(failed)-set(baseline['failed_protected']))
        report['inherited_failures']=sorted(set(failed)&set(baseline['failed_protected']))
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='predictions'}))


if __name__=='__main__':
    main()
