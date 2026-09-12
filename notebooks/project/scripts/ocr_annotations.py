"""Local OCR annotation workspace: candidates, human review and approved exports.

Source pixels use the stored raster orientation (no EXIF transpose), consistently
for source bbox coordinates, the editor, OCR suggestions and training crops.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import re
import secrets
import sys
import threading
from contextlib import contextmanager
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / '학습 및 테스트 결과/02_annotations'
KINDS = ('date_line', 'date_block', 'header', 'lot', 'time', 'other')
ROLES = ('expiry', 'manufacture', 'other')
FIELD_STATES = ('present', 'absent', 'occluded', 'unreadable', 'unknown')
QUALITY_TAGS = ('reflection', 'curved', 'bleed', 'dot_print', 'low_resolution', 'blur', 'rotation', 'low_contrast')
IMMUTABLE = ('schema_version', 'image_id', 'source_image_id', 'image_path', 'image_sha256',
             'width', 'height', 'source_dataset', 'final_date', 'final_date_review',
             'seen_in_development', 'legacy_metadata')
LOCK = threading.Lock()


@contextmanager
def workspace_lock(output):
    """Serialize browser and background-worker writes, including revision checks."""
    output.mkdir(parents=True, exist_ok=True)
    with (output/'.review.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if sys.platform=='win32':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform=='win32':
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def record_path(image_id, output=OUT):
    if not re.fullmatch(r'[AB]MLC\d{6}', image_id):
        raise ValueError('Invalid image_id')
    return output / 'records' / (image_id + '.json')


def source_path(record, root=ROOT):
    path = (root / record['image_path']).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Invalid image path')
    return path


def new_region(region_id, kind='date_line', polygon=None, text='', provenance=None):
    return dict(region_id=region_id, kind=kind, polygon=polygon or [], transcription=text,
        role=None, role_basis='undetermined', role_evidence='', header_region_ids=[],
        field_states=dict(year='unknown', month='unknown', day='unknown'),
        occluded_characters=[], separators='', time_text='', lot_text='',
        legibility='unknown', status='pending', notes='', provenance=provenance or {'type':'human_drawn'})


def crop(image, polygon):
    """Mask outside the polygon; do not invent/rectify characters or normalize text."""
    xs, ys = zip(*polygon)
    bounds = (math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys)))
    tile = image.crop(bounds).convert('RGB')
    mask = Image.new('L', tile.size)
    ImageDraw.Draw(mask).polygon([(x-bounds[0], y-bounds[1]) for x,y in polygon], fill=255)
    result = Image.new('RGB', tile.size, 'white')
    result.paste(tile, mask=mask)
    return result


def polygon_errors(points, width, height):
    if not isinstance(points, list) or len(points) < 3:
        return ['polygon needs at least three vertices']
    if any(not isinstance(p, list) or len(p)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in p) for p in points):
        return ['polygon coordinates must be finite numbers']
    errors = []
    if any(not (0 <= x <= width and 0 <= y <= height) for x,y in points):
        errors.append('polygon is outside image bounds')
    if len({tuple(p) for p in points}) != len(points):
        errors.append('polygon repeats a vertex')
    area = abs(sum(points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points))))/2
    if area < 1:
        errors.append('polygon area is too small')
    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for i in range(len(points)):
        a,b=points[i],points[(i+1)%len(points)]
        for j in range(i+1,len(points)):
            if j in (i,(i+1)%len(points)) or (j+1)%len(points)==i:
                continue
            c,d=points[j],points[(j+1)%len(points)]
            if cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0:
                errors.append('polygon self-intersects')
    return errors


def validate(record, approve=False):
    errors = []
    region_ids = [r.get('region_id') for r in record['regions']]
    if len(set(region_ids)) != len(region_ids) or any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9_-]+', k) for k in region_ids):
        errors.append('Region IDs must be unique simple identifiers')
    if any(t not in QUALITY_TAGS for t in record['quality_tags']):
        errors.append('Unsupported quality tag')
    if not isinstance(record['group_id'],str) or not record['group_id'].strip():
        errors.append('group_id is required')
    if record['difficulty'] not in ('easy','medium','hard','unassessed'):
        errors.append('Invalid difficulty')
    for region in record['regions']:
        prefix = str(region.get('region_id')) + ': '
        if region['kind'] not in KINDS or region['status'] not in ('pending','checked','rejected'):
            errors.append(prefix+'invalid kind/status')
        if not isinstance(region['transcription'],str) or '\t' in region['transcription'] or '\r' in region['transcription']:
            errors.append(prefix+'raw text must be a string without TAB/CR')
        if region['legibility'] not in ('unknown','readable','partially_occluded','unreadable'):
            errors.append(prefix+'invalid legibility')
        if region['role_basis'] not in ('undetermined','visible_header','package_context','reviewer_inference'):
            errors.append(prefix+'invalid role basis')
        if not isinstance(region['occluded_characters'],list) or any(not isinstance(c,dict) for c in region['occluded_characters']):
            errors.append(prefix+'occluded_characters must be an array of descriptions')
        if any(not isinstance(region[f],str) for f in ('separators','time_text','lot_text','role_evidence','notes')):
            errors.append(prefix+'text attributes must be strings')
        if any(region['field_states'].get(f) not in FIELD_STATES for f in ('year','month','day')):
            errors.append(prefix+'invalid date field state')
        if any(k not in region_ids or next(r for r in record['regions'] if r['region_id']==k)['kind']!='header' for k in region['header_region_ids']):
            errors.append(prefix+'header link must name an existing header region')
        if region['status']=='rejected':
            continue
        errors.extend(prefix+e for e in polygon_errors(region['polygon'],record['width'],record['height']))
        if approve:
            if region['status'] != 'checked':
                errors.append(prefix+'human check is required')
            if region['legibility']=='unknown':
                errors.append(prefix+'mark readable/occluded/unreadable')
            if region['legibility']=='readable' and not region['transcription'].strip():
                errors.append(prefix+'readable region needs its printed text')
            if region['legibility']=='partially_occluded' and not region['occluded_characters']:
                errors.append(prefix+'describe the occluded characters without guessing them')
            if region['legibility']=='readable' and any(v in ('occluded','unreadable') for v in region['field_states'].values()):
                errors.append(prefix+'readable text contradicts occluded/unreadable date fields')
            if region['kind'] in ('date_line','date_block','header') and region['role'] not in ROLES:
                errors.append(prefix+'choose expiry/manufacture/other')
            if region['kind'] in ('date_line','date_block'):
                if 'unknown' in region['field_states'].values():
                    errors.append(prefix+'confirm each date field visibility')
                if not region['role_evidence'].strip():
                    errors.append(prefix+'record role evidence (including unknown-role explanation for other)')
    if approve:
        review = record['review']
        if not str(review.get('reviewer','')).strip():
            errors.append('A human reviewer name is required')
        for field in ('date_regions_complete','header_regions_complete','quality_reviewed','group_reviewed'):
            if review.get(field) is not True:
                errors.append('Confirm '+field)
        if record['difficulty']=='unassessed':
            errors.append('Confirm difficulty')
        if not record['group_evidence'].strip():
            errors.append('Record the product-group review evidence')
        dates=[r for r in record['regions'] if r['kind']=='date_line' and r['status']!='rejected']
        if not dates and review.get('no_date_regions') is not True:
            errors.append('Confirm no date regions, or annotate date lines')
        if dates and review.get('no_date_regions') is True:
            errors.append('No-date flag contradicts date-line annotations')
        if not dates and record['final_date']!='NONE':
            errors.append('Approved final date requires a date-line region; explain/correct annotation')
    return errors


def initialize(root=ROOT, output=OUT):
    protocol = root / '학습 및 테스트 결과/00_protocol'
    frozen = read(protocol / 'data/frozen_hashes.json')
    for relative in ('추가수집데이터/metadata/annotations.json',
                     '추가수집_정답지/answer_003353_003716_manual.xlsx',
                     '학습 및 테스트 결과/00_protocol/dataset_inventory.json'):
        if sha(root/relative) != frozen[relative]:
            raise ValueError('Stage 1 input changed: '+relative)
    inventory = read(protocol / 'dataset_inventory.json')['images']
    source_annotations = read(root/'추가수집데이터/metadata/annotations.json')
    created=0
    for item in inventory:
        if not item['selected_for_training']:
            continue
        image_id=item['training_image_id']
        path=record_path(image_id,output)
        if path.exists():
            continue  # Never replace a review already in progress.
        image=next(c for c in item['copies'] if c['kind']=='training')
        if sha(root/image['path']) != image['sha256']:
            raise ValueError('Image SHA mismatch: '+image_id)
        regions=[]
        if item['source_dataset']=='additional':
            for index, annotation in enumerate(source_annotations[Path(item['source_path']).name]['ann']):
                kind='date_line' if annotation['cls'] in ('date','exp') else 'header' if annotation['cls'] in ('due','prod') else 'lot'
                x1,y1,x2,y2=annotation['bbox']
                regions.append(new_region(f'source_{index:03d}',kind,[[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                    annotation.get('transcription',''),dict(type='external_source_candidate',source_class=annotation['cls'],
                    path='추가수집데이터/metadata/annotations.json',key=Path(item['source_path']).name,index=index)))
        record=dict(schema_version=1,image_id=image_id,source_image_id=item['source_image_id'],
            image_path=image['path'],image_sha256=image['sha256'],width=image['width'],height=image['height'],
            source_dataset=item['source_dataset'],final_date=item['final_date'],
            final_date_review=dict(status='approved',scope='normalized_final_date_only',reviewer='user',
                method='human_visual_review_of_all_364_images' if item['source_dataset']=='additional' else 'user_approved_workbook',
                source=item['label_source']),seen_in_development=item['seen_in_development'],
            legacy_metadata=dict(difficulty=item['difficulty'],condition_tags=item['condition_tags']),
            group_id=item['group_id'],group_evidence='',difficulty=item['difficulty'],quality_tags=[],notes='',regions=regions,
            revision=0,review=dict(status='pending',reviewer='',approved_at=None,date_regions_complete=False,
                header_regions_complete=False,quality_reviewed=False,group_reviewed=False,no_date_regions=False))
        errors=validate(record)
        if errors:
            raise ValueError(f'{image_id}: {errors}')
        write(path,record)
        with Image.open(root/image['path']) as source:
            for region in regions:
                if region['kind']=='date_line':
                    destination=output/'candidate_crops'/image_id/(region['region_id']+'.png')
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    crop(source,region['polygon']).save(destination)
        created+=1
    return dict(created=created,**audit(output))


def save_review(image_id, candidate, expected_revision, approve, root=ROOT, output=OUT):
    with LOCK, workspace_lock(output):
        path=record_path(image_id,output)
        original=read(path)
        if expected_revision!=original['revision']:
            raise ValueError('Revision conflict; reload before saving')
        for field in IMMUTABLE:
            if candidate.get(field)!=original[field]:
                raise ValueError('Immutable source field: '+field)
        if sha(source_path(original,root))!=original['image_sha256']:
            raise ValueError('Image changed since inventory')
        errors=validate(candidate,approve)
        if errors:
            raise ValueError('\n'.join(errors))
        result=copy.deepcopy(candidate)
        if not approve and original.get('user_acceptance') and candidate.get('user_acceptance')==original.get('user_acceptance'):
            result['user_acceptance']=dict(original['user_acceptance'],status='superseded_by_edit')
        result['revision']=original['revision']+1
        result['review']['status']='approved' if approve else 'pending'
        result['review']['approved_at']=now() if approve else None
        write(output/'history'/image_id/f'{original["revision"]:06d}.json',original)
        write(path,result)
        return result


def audit(output=OUT):
    records=[read(p) for p in sorted((output/'records').glob('*.json'))]
    kinds=Counter(r['kind'] for record in records for r in record['regions'] if r['status']!='rejected')
    problems={r['image_id']:validate(r,r['review']['status']=='approved') for r in records}
    problems={k:v for k,v in problems.items() if v}
    approved=sum(r['review']['status']=='approved' for r in records)
    report=dict(images=len(records),final_dates_approved=sum(r['final_date_review']['status']=='approved' for r in records),
        human_reviewed_final_dates_additional=sum(r['source_dataset']=='additional' for r in records),
        annotation_images_approved=approved,pending_images=len(records)-approved,
        user_as_is_accepted_images=sum(r.get('user_acceptance',{}).get('status')=='approved' for r in records),
        region_counts=dict(kinds),validation_errors=problems,stage_2_complete=len(records)==2610 and approved==2610 and not problems,
        fold_assignment_created=False,training_started=False)
    write(output/'status.json',report)
    return report


def export_approved(root=ROOT, output=OUT):
    records=[read(p) for p in sorted((output/'records').glob('*.json'))]
    selected=[r for r in records if r['review']['status']=='approved']
    for r in selected:
        errors=validate(r,True)
        if errors or sha(source_path(r,root))!=r['image_sha256']:
            raise ValueError(f'Invalid approved record: {r["image_id"]}: {errors}')
    # Versioned exports retain old snapshots; never mix a revoked label into a new export.
    destination=output/'exports'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination.mkdir(parents=True)
    rec,det,skipped=[],[],[]
    for record in selected:
        polygons=[]
        with Image.open(source_path(record,root)) as image:
            for region in record['regions']:
                if region['kind']!='date_line' or region['status']=='rejected':
                    continue
                polygons.append(dict(points=region['polygon'],transcription=region['transcription'],
                                     ignore=False,role=region['role']))
                reason = ('not_fully_readable' if region['legibility']!='readable' else
                          'multiline_needs_line_split' if '\n' in region['transcription'] else
                          'over_training_max_length_25' if len(region['transcription'])>25 else None)
                if reason:
                    skipped.append(dict(image_id=record['image_id'],region_id=region['region_id'],reason=reason))
                    continue
                path=destination/'crops'/f'{record["image_id"]}_{region["region_id"]}.png'
                path.parent.mkdir(parents=True,exist_ok=True)
                crop(image,region['polygon']).save(path)
                rec.append(dict(image_id=record['image_id'],crop_path=str(path),transcription=region['transcription'],
                    group_id=record['group_id'],seen_in_development=record['seen_in_development'],
                    record_revision=record['revision'],record_sha256=sha(record_path(record['image_id'],output)),crop_sha256=sha(path)))
        det.append(dict(image_id=record['image_id'],image_path=str(source_path(record,root)),
            polygons=polygons,group_id=record['group_id'],seen_in_development=record['seen_in_development']))
    for name,rows in (('recognition_pool.jsonl',rec),('detection_pool.jsonl',det)):
        (destination/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    (destination/'recognition_pool.txt').write_text(''.join(r['crop_path']+'\t'+r['transcription']+'\n' for r in rec),encoding='utf-8')
    # Date-only detector labels use a neutral non-ignore token, even if text is unreadable.
    (destination/'detection_pool.txt').write_text(''.join(r['image_path']+'\t'+json.dumps([
        dict(points=p['points'],transcription='date') for p in r['polygons']],ensure_ascii=False)+'\n' for r in det),encoding='utf-8')
    report=dict(approved_images=len(selected),recognition_crops=len(rec),detection_scenes=len(det),
        directory=str(destination),usage='Approved annotation pool only. Assign group-safe folds and inner validation before training.',
        training_allowed=False,recognition_exclusions=skipped,
        source_annotation_snapshot={r['image_id']:sha(record_path(r['image_id'],output)) for r in selected})
    write(destination/'export_report.json',report)
    return report


def suggest(image_id, root=ROOT, output=OUT):
    import cv2
    import numpy as np
    from src.pipeline import PaddleOCRBackend, PipelineConfig
    path=record_path(image_id,output)
    record=read(path)
    if record['review']['status']=='approved' or any(r['provenance']['type']=='automatic_ocr_candidate' for r in record['regions']):
        raise ValueError('Already approved or already has OCR suggestions; preserve existing work')
    backend=PaddleOCRBackend(PipelineConfig(cpu_threads=4))
    with Image.open(source_path(record,root)) as image:
        raster=cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2BGR)
    for i,line in enumerate(backend.recognize(raster,detector='mobile',variant='stored-raster')):
        if not line.geometry_valid:
            continue
        poly=[list(p) for p in line.polygon] if line.polygon else [[line.box[0],line.box[1]],[line.box[2],line.box[1]],[line.box[2],line.box[3]],[line.box[0],line.box[3]]]
        if polygon_errors(poly,record['width'],record['height']):
            continue
        kind='date_line' if re.search(r'\d.*[./년월-].*\d',line.text) else 'other'
        record['regions'].append(new_region(f'ocr_{i:03d}',kind,poly,line.text,dict(type='automatic_ocr_candidate',score=line.score)))
    return save_review(image_id,record,record['revision'],False,root,output)


def suggest_missing_text(root=ROOT, output=OUT):
    """Fill empty external header/code candidates, never date truth or reviewed text."""
    import cv2
    import numpy as np
    from src.pipeline import PaddleOCRBackend, PipelineConfig
    records=[read(p) for p in sorted((output/'records').glob('BMLC*.json'))]
    records=[r for r in records if r['review']['status']=='pending' and any(
        a['kind'] in ('header','lot','time') and a['status']=='pending' and not a['transcription']
        and 'text_candidate' not in a['provenance'] for a in r['regions'])]
    if not records:
        return dict(images_updated=0,regions_processed=0)
    backend=PaddleOCRBackend(PipelineConfig(cpu_threads=4))
    processed=0
    filled=0
    conflicts=[]
    for index,record in enumerate(records):
        regions=[a for a in record['regions'] if a['kind'] in ('header','lot','time') and a['status']=='pending'
                 and not a['transcription'] and 'text_candidate' not in a['provenance']]
        with Image.open(source_path(record,root)) as image:
            crops=[cv2.cvtColor(np.asarray(crop(image,a['polygon'])),cv2.COLOR_RGB2BGR) for a in regions]
        results=backend.recognize_crops(crops)
        if len(results)!=len(regions):
            raise ValueError('Crop recognizer returned an unexpected row count')
        for region,(text,score,_) in zip(regions,results):
            region['transcription']=text
            region['provenance']['text_candidate']=dict(type='automatic_ocr_candidate',
                model='korean_PP-OCRv5_mobile_rec',score=score,created_at=now())
            processed+=1
            filled+=bool(text)
        try:
            save_review(record['image_id'],record,record['revision'],False,root,output)
        except ValueError as exc:
            if 'Revision conflict' not in str(exc):
                raise
            conflicts.append(record['image_id'])
        if (index+1)%40==0:
            print(f'Text candidates: {index+1}/{len(records)} images, {processed} regions',flush=True)
    result=dict(images_updated=len(records)-len(conflicts),regions_processed=processed,nonempty_candidates=filled,
                conflicting_images_preserved=conflicts,approval_status='pending',method='CPU OCR suggestions only')
    write(output/'text_candidate_report.json',result)
    audit(output)
    return result


def accept_draft(record):
    """Called only by an explicit human approve-all action, never by generation."""
    candidate = copy.deepcopy(record)
    for region in candidate['regions']:
        if region['status'] != 'rejected':
            region['status'] = 'checked'
    for field in ('date_regions_complete','header_regions_complete','quality_reviewed','group_reviewed'):
        candidate['review'][field] = True
    errors = validate(candidate, approve=True)
    if errors:
        raise ValueError('\n'.join(errors))
    candidate['review']['method'] = 'explicit_human_accept_draft_and_next'
    return candidate


def serve(port=8765, root=ROOT, output=OUT, cohort_path=None):
    scope=set(read(Path(cohort_path))['image_ids']) if cohort_path else None
    if scope is not None and any(not record_path(i,output).exists() for i in scope):
        raise ValueError('Review cohort contains missing records')
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def send(self,data,kind='application/json',status=200):
            if not isinstance(data,bytes):
                data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                path=urlparse(self.path).path
                if path=='/':
                    html=(ROOT/'notebooks/project/scripts/annotation_editor.html').read_text(encoding='utf-8').replace('__SESSION_TOKEN__',token)
                    return self.send(html.encode(),'text/html; charset=utf-8')
                if path=='/api/index':
                    rows=[]
                    readiness=output/'acceptance_readiness.json'
                    ready=set(read(readiness)['ready_for_human_visual_accept']) if readiness.exists() else set()
                    for p in (output/'records').glob('*.json'):
                        if scope is not None and p.stem not in scope:
                            continue
                        r=read(p)
                        rows.append({k:r[k] for k in ('image_id','source_image_id','source_dataset','final_date')}|{'status':r['review']['status'],'regions':len(r['regions']), 'ocr_completed':bool(r.get('ocr_draft_pass')),'accept_ready':r['image_id'] in ready})
                        rows[-1]['user_accepted']=r.get('user_acceptance',{}).get('status')=='approved'
                    return self.send(sorted(rows,key=lambda r:(r['source_dataset']!='additional',r['image_id'])))
                if path=='/api/scope':
                    return self.send({'restricted':scope is not None,'count':len(scope) if scope is not None else None})
                if path.startswith('/api/record/'):
                    return self.send(read(record_path(path.rsplit('/',1)[1],output)))
                if path.startswith('/api/group-candidates/'):
                    group_file=output/'group_candidates.json'
                    candidates=read(group_file) if group_file.exists() else {}
                    return self.send(candidates.get(path.rsplit('/',1)[1],{}))
                if path.startswith('/image/'):
                    r=read(record_path(path.rsplit('/',1)[1],output))
                    with Image.open(source_path(r,root)) as original:
                        im=original.convert('RGB')
                        im.info.clear()
                        buffer=io.BytesIO()
                        im.save(buffer,format='PNG')
                    return self.send(buffer.getvalue(),'image/png')
                self.send({'error':'Not found'},status=404)
            except (ValueError,KeyError,FileNotFoundError) as exc:
                self.send({'error':str(exc)},status=400)

        def do_POST(self):
            if self.headers.get('X-Annotation-Token')!=token:
                return self.send({'error':'Invalid session token'},status=403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<2_000_000:
                    raise ValueError('Invalid body size')
                payload=json.loads(self.rfile.read(length))
                path=urlparse(self.path).path
                if path not in ('/api/save','/api/approve','/api/approve-draft'):
                    return self.send({'error':'Not found'},status=404)
                if scope is not None and payload['record']['image_id'] not in scope:
                    return self.send({'error':'이 검수 화면의 대상이 아닙니다.'},status=403)
                candidate=accept_draft(payload['record']) if path=='/api/approve-draft' else payload['record']
                result=save_review(candidate['image_id'],candidate,payload['revision'],path!='/api/save',root,output)
                return self.send(result)
            except (ValueError,KeyError,TypeError,FileNotFoundError) as exc:
                self.send({'error':str(exc)},status=400)

        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Annotation editor: http://127.0.0.1:{port}',flush=True)
    server.serve_forever()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('init','audit','export','serve','suggest','suggest-missing-text'))
    parser.add_argument('--image-id')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--cohort',help='Fixed review cohort JSON containing image_ids')
    args=parser.parse_args()
    if args.command=='serve':
        serve(args.port,cohort_path=args.cohort)
    else:
        result=initialize() if args.command=='init' else audit() if args.command=='audit' else export_approved() if args.command=='export' else suggest_missing_text() if args.command=='suggest-missing-text' else suggest(args.image_id)
        print(json.dumps(result,ensure_ascii=False,indent=2))
