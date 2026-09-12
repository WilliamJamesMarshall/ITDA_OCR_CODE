"""Repair the fixed 565-image cohort; preserve labels and human review history."""
import argparse
import copy
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann
from scripts.build_annotation_drafts import enrich, role_hint
from scripts.refine_annotation_drafts import refine, visible_fields, plausible_date
from scripts.import_annotation_cache import stored_point

BATCH=ann.OUT/'remaining_565'


def cohort():
    path=BATCH/'cohort.json'
    if not path.exists():
        readiness=ann.read(ann.OUT/'acceptance_readiness.json')
        ids=list(readiness['requires_correction'])
        if len(ids)!=565:
            raise ValueError('Expected the original 565-image cohort')
        ann.write(path,dict(image_ids=ids,created_at=ann.now(),initial_errors=readiness['requires_correction']))
        for image_id in ids:
            ann.write(BATCH/'before'/f'{image_id}.json',ann.read(ann.record_path(image_id)))
    return ann.read(path)['image_ids']


def fields_hint(text):
    if re.fullmatch(r'\s*(?:\d{1,2}[/ .]+\d{4}|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s*\d{4})\s*',text,re.I):
        return dict(year='present',month='present',day='absent')
    fields=visible_fields(text)
    if fields:
        return fields
    # Presence is distinct from numerical validity; preserve the OCR string.
    if re.search(r'(?<!\d)\d{2,4}[./년 -]+\d{1,2}[./월 -]+\d{1,4}(?!\d)',text):
        return dict(year='present',month='present',day='present')
    if re.search(r'(?<!\d)\d{1,2}[./월]+\d{1,2}(?=까지|\s|일|$)',text):
        return dict(year='absent',month='present',day='present')
    return None


def metadata(record):
    for r in record['regions']:
        if r['status']=='rejected':
            continue
        text=r['transcription']
        if r['legibility']=='unknown' and text.strip():
            r['legibility']='readable'
            r.setdefault('draft',{})['legibility_basis']='기존 OCR 원문 후보 있음; 시각 검수 전 임시 판독 상태'
        if r['kind']=='date_line':
            if re.search(r'제조원|제조및|판매원|인증기관|인증번호|식품연|광역시|\bTEL\b|품목보고',text,re.I):
                r['kind']='other'
                r.setdefault('draft',{})['classification_basis']='주소·업체·인증 설명문 후보, 삭제하지 않고 보존'
            elif 'unknown' in r['field_states'].values():
                fields=fields_hint(text)
                if fields:
                    r['field_states']=fields
        if r['role'] is None:
            r['role']=role_hint(text) or 'other'
            r['role_evidence']='초안: 인쇄 표제 단서' if role_hint(text) else '초안: 역할을 특정할 표제 근거 없음'
        if not r['separators'] and r['kind']=='date_line':
            r['separators']=''.join(dict.fromkeys(re.findall(r'[./년월일-]',text)))
    return record


def overlap(a,b):
    def bounds(p):
        return min(x for x,y in p),min(y for x,y in p),max(x for x,y in p),max(y for x,y in p)
    x1,y1,x2,y2=bounds(a);u1,v1,u2,v2=bounds(b)
    intersection=max(0,min(x2,u2)-max(x1,u1))*max(0,min(y2,v2)-max(y1,v1))
    return intersection/max(1,(x2-x1)*(y2-y1)+(u2-u1)*(v2-v1)-intersection)


def run(mode,limit=None,reverse=False):
    ids=sorted(cohort(),reverse=reverse)
    backend=None
    done=0
    failures=[]
    for image_id in ids:
        record=ann.read(ann.record_path(image_id))
        if record['review']['status']!='pending':
            continue
        before=copy.deepcopy(record)
        metadata(record)
        if mode=='full':
            if any(r['kind']=='date_line' and r['status']!='rejected' for r in record['regions']) or record.get('deep_draft_pass'):
                if before!=record:
                    ann.save_review(image_id,record,record['revision'],False)
                continue
            if limit is not None and done>=limit:
                break
            try:
                from src.pipeline import PaddleOCRBackend,PipelineConfig,predict_image
                if backend is None:
                    config=PipelineConfig(cpu_threads=4,enable_rotation_fallback=True)
                    backend=PaddleOCRBackend(config)
                path=ann.source_path(record)
                if ann.sha(path)!=record['image_sha256']:
                    raise ValueError('Image SHA mismatch')
                prediction=predict_image(path,backend,config)
                ann.write(BATCH/'traces'/f'{image_id}.json',prediction.trace)
                with ann.Image.open(path) as image:
                    orientation=image.getexif().get(274,1)
                observations=[o for o in prediction.trace['observations'] if o['original_polygon'] and o['text'].strip()
                    and (o['full_parses'] or o['partial_parses'] or plausible_date(o['text']))]
                chosen=[]
                for o in sorted(observations,key=lambda o:float(o['score'] or 0),reverse=True):
                    polygon=[list(stored_point(x,y,record['width'],record['height'],orientation)) for x,y in o['original_polygon']]
                    if ann.polygon_errors(polygon,record['width'],record['height']) or any(overlap(polygon,r['polygon'])>.45 for r in chosen):
                        continue
                    r=ann.new_region(f'deep_{len(chosen):03d}','date_line',polygon,o['text'],dict(
                        type='automatic_ocr_candidate',method='full_pipeline_recovery',score=o['score'],
                        trace=(BATCH/'traces'/f'{image_id}.json').relative_to(ann.ROOT).as_posix(),observation_id=o['observation_id']))
                    chosen.append(r)
                record['regions'].extend(chosen)
                record['deep_draft_pass']=dict(created_at=ann.now(),candidates=len(chosen),elapsed_seconds=prediction.elapsed_seconds)
                enrich(record)
                metadata(record)
                done+=1
                print(dict(image_id=image_id,processed=done,candidates=len(chosen),seconds=round(prediction.elapsed_seconds,2)),flush=True)
            except Exception as exc:
                failures.append(dict(image_id=image_id,error=str(exc)))
                continue
        if before!=record:
            ann.save_review(image_id,record,record['revision'],False)
    ann.write(BATCH/f'{mode}{"_reverse" if reverse else ""}_report.json',dict(processed=done,failures=failures,human_approvals_created=0))
    print(dict(processed=done,failures=failures),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['metadata','full'])
    parser.add_argument('--limit',type=int)
    parser.add_argument('--reverse',action='store_true')
    args=parser.parse_args()
    run(args.mode,args.limit,args.reverse)
