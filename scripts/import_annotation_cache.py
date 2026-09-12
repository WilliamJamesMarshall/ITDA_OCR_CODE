"""Reuse local historical OCR as visibly unverified candidates, not truth."""
import sys
import json
import argparse
from pathlib import Path
from PIL import ImageOps

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann
from scripts.build_annotation_drafts import enrich, region_kind


def stored_point(u,v,width,height,orientation):
    return {1:(u,v),2:(width-u,v),3:(width-u,height-v),4:(u,height-v),
        5:(v,u),6:(v,height-u),7:(width-v,height-u),8:(width-v,u)}.get(orientation,(u,v))


def main(supplement=False):
    source=ann.ROOT/'artifacts/country-date-report-20260909/ocr_evidence.jsonl'
    evidence={r['image_id']:r for r in (json.loads(s) for s in source.read_text(encoding='utf-8').splitlines())}
    digest=ann.sha(source)
    report=dict(imported=0,conflicts=[],rejected=[],historical_image_hash_available=False)
    for path in sorted((ann.OUT/'records').glob('AMLC*.json')):
        record=ann.read(path)
        if record['review']['status']!='pending' or record['review']['reviewer']:
            continue
        if supplement:
            if record.get('cache_supplement') or any(r['kind']=='date_line' for r in record['regions']):
                continue
        elif record.get('ocr_draft_pass') or record['regions']:
            continue
        cached=evidence.get(record['source_image_id'])
        if not cached or cached.get('error'):
            continue
        try:
            image_path=ann.source_path(record)
            if ann.sha(image_path)!=record['image_sha256']:
                raise ValueError('Current image SHA mismatch')
            with ann.Image.open(image_path) as image:
                orientation=image.getexif().get(274,1)
                oriented=ImageOps.exif_transpose(image)
                ow,oh=oriented.size
                oriented.thumbnail((1600,1600))
                if list(oriented.size)!=cached['ocr_size']:
                    raise ValueError('Historical OCR size mismatch')
            cw,ch=cached['ocr_size']
            for i,line in enumerate(cached['lines']):
                if supplement:
                    from scripts.refine_annotation_drafts import plausible_date
                    if not plausible_date(line['text']):
                        continue
                x1,y1,x2,y2=line['box']
                polygon=[list(stored_point(x*ow/cw,y*oh/ch,record['width'],record['height'],orientation))
                    for x,y in ((x1,y1),(x2,y1),(x2,y2),(x1,y2))]
                if ann.polygon_errors(polygon,record['width'],record['height']):
                    continue
                text=line['text']
                region_id=f'supplement_{i:03d}' if supplement else f'cache_{i:03d}'
                record['regions'].append(ann.new_region(region_id,'date_line' if supplement else region_kind(text),polygon,text,
                    dict(type='automatic_ocr_candidate',method='historical_cpu_ocr_import',score=line['score'],
                        path=source.relative_to(ann.ROOT).as_posix(),cache_sha256=digest,
                        source_image_id=cached['image_id'],historical_image_sha256=None,
                        current_image_sha256=record['image_sha256'],geometry='resized_oriented_box_to_stored_raster',
                        warning='당시 이미지 해시 미기록. 현재 파일 연결 및 크기 확인; 사진 대조 필요.')))
            if supplement:
                record['cache_supplement']=dict(created_at=ann.now(),cache_sha256=digest)
                record.pop('quality_draft_measurements',None)
            else:
                record['ocr_draft_pass']=dict(status='completed',method='historical_cpu_ocr_import',created_at=ann.now(),
                    cache_sha256=digest,historical_image_hash_available=False)
            enrich(record)
            ann.save_review(record['image_id'],record,record['revision'],False)
            report['imported']+=1
        except ValueError as exc:
            report['conflicts' if 'Revision conflict' in str(exc) else 'rejected'].append(dict(image_id=record['image_id'],error=str(exc)))
    ann.write(ann.OUT/('cache_supplement_report.json' if supplement else 'cache_import_report.json'),report)
    print(report,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supplement',action='store_true')
    main(parser.parse_args().supplement)
