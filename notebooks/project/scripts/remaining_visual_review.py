"""Contact sheets and explicitly authored AI visual drafts for the fixed cohort."""
import argparse
import sys
import copy
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH,cohort,metadata


def sheets(mode):
    rows=[]
    for image_id in cohort():
        r=ann.read(ann.record_path(image_id))
        if r['review']['status']=='approved':
            continue
        if mode=='missing':
            if not any(a['kind']=='date_line' and a['status']!='rejected' for a in r['regions']):
                rows.append((r,None))
        else:
            for a in r['regions']:
                if a['status']!='rejected' and (a['legibility']=='unknown' or (a['kind']=='date_line' and 'unknown' in a['field_states'].values())):
                    rows.append((r,a))
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',18)
    per=4 if mode=='missing' else 8
    cw,ch=(650,820) if mode=='missing' else (1300,180)
    for page in range(0,len(rows),per):
        board=Image.new('RGB',(1300,1640 if mode=='missing' else per*ch),'#e8e8e8')
        draw=ImageDraw.Draw(board)
        for j,(r,a) in enumerate(rows[page:page+per]):
            x,y=(j%2*cw,j//2*ch) if mode=='missing' else (0,j*ch)
            with Image.open(ann.source_path(r)) as image:
                tile=image.convert('RGB') if a is None else ann.crop(image,a['polygon'])
                if mode=='context' and a is not None:
                    xs=[p[0] for p in a['polygon']];ys=[p[1] for p in a['polygon']]
                    w=max(xs)-min(xs);h=max(ys)-min(ys)
                    tile=image.convert('RGB').crop((max(0,min(xs)-w*.8),max(0,min(ys)-h*1.5),min(image.width,max(xs)+w*.8),min(image.height,max(ys)+h*1.5)))
                if a is not None:
                    if tile.height>tile.width:
                        tile=tile.rotate(90,expand=True)
                    scale=min(850/tile.width,(ch-60)/tile.height)
                    tile=tile.resize((max(1,round(tile.width*scale)),max(1,round(tile.height*scale))))
                else:
                    tile.thumbnail((cw-10,ch-65))
                board.paste(tile,(x,y+55))
                if a is None:
                    # Normalized grid labels are measured relative to the pasted raster.
                    for t in range(1,10):
                        gx=x+tile.width*t/10;gy=y+55+tile.height*t/10
                        draw.line((gx,y+55,gx,y+55+tile.height),fill='#80aa99',width=1)
                        draw.line((x,gy,x+tile.width,gy),fill='#80aa99',width=1)
            label=r['image_id']+' '+('full image' if a is None else a['region_id']+' '+a['kind'])
            draw.text((x+5,y+2),label,fill='black',font=font)
            draw.text((x+5,y+26),('' if a is None else a['transcription'][:80]),fill='black',font=font)
        path=BATCH/'sheets'/f'{mode}_{page//per:03d}.jpg'
        path.parent.mkdir(parents=True,exist_ok=True)
        board.save(path,quality=95)
    ann.write(BATCH/f'{mode}_sheet_index.json',[dict(image_id=r['image_id'],region_id=a['region_id'] if a else None) for r,a in rows])
    print(dict(items=len(rows),pages=(len(rows)+per-1)//per))


def apply(path,start=0):
    data=ann.read(Path(path))[start:];ids=set(cohort())
    for entry in data:
        existing={a['region_id'] for a in ann.read(ann.record_path(entry['image_id']))['regions']}
        for change in entry['regions']:
            if change['region_id'] not in existing and not any(k in change for k in ('polygon','normalized_polygon','relative_crop')):
                raise ValueError('Unknown region without geometry: '+entry['image_id']+'/'+change['region_id'])
    for entry in data:
        image_id=entry['image_id']
        if image_id not in ids:
            raise ValueError('Outside cohort')
        r=ann.read(ann.record_path(image_id))
        if r['review']['status']=='approved':
            raise ValueError('Already human approved; preserve it')
        original_regions={a['region_id']:copy.deepcopy(a) for a in r['regions']}
        for change in entry['regions']:
            region=next((a for a in r['regions'] if a['region_id']==change['region_id']),None)
            if region is None:
                region=ann.new_region(change['region_id'])
                r['regions'].append(region)
            values=dict(change)
            if 'relative_crop' in values:
                ref=original_regions[values.pop('from_region',change['region_id'])]['polygon']
                left,top,right,bottom=values.pop('relative_crop')
                x1,y1=min(p[0] for p in ref),min(p[1] for p in ref)
                x2,y2=max(p[0] for p in ref),max(p[1] for p in ref)
                region['polygon']=[[min(r['width'],max(0,x)),min(r['height'],max(0,y))] for x,y in
                    [[x1+(x2-x1)*left,y1+(y2-y1)*top],[x1+(x2-x1)*right,y1+(y2-y1)*top],
                    [x1+(x2-x1)*right,y1+(y2-y1)*bottom],[x1+(x2-x1)*left,y1+(y2-y1)*bottom]]]
            if 'normalized_polygon' in values:
                region['polygon']=[[x*r['width']/1000,y*r['height']/1000] for x,y in values.pop('normalized_polygon')]
            region.update(values)
            region['status']='pending'
            region['provenance']['ai_visual_review']=dict(type='AI_visual_draft_not_human_approval',
                source_image_sha256=r['image_sha256'],created_at=ann.now(),notes=entry.get('evidence',''))
        if 'no_date_regions' in entry:
            r['review']['no_date_regions']=entry['no_date_regions']
        if 'quality_tags' in entry:
            r['quality_tags']=entry['quality_tags']
        metadata(r)
        ann.save_review(image_id,r,r['revision'],False)
    print(dict(images_updated=len(data),human_approvals_created=0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['missing','fields','context','apply'])
    p.add_argument('--file')
    p.add_argument('--start',type=int,default=0)
    args=p.parse_args()
    apply(args.file,args.start) if args.mode=='apply' else sheets(args.mode)
