"""Fixed last-scene geometry and inspection crops."""
from PIL import Image
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH
BOXES=[(429,0,[180,590,366,620]),(441,1,[844,630,988,663]),(486,2,[150,1170,407,1215]),(537,3,[765,1245,975,1300]),(2243,0,[245,175,298,435])]
def entries():
    result=[]
    for n,cell,box in BOXES:
        r=ann.read(ann.record_path(f'AMLC{n:06d}'))
        with Image.open(ann.source_path(r)) as im:
            thumb=im.copy();thumb.thumbnail((640,755));w,h=thumb.size
            x=cell%2*650;y=cell//2*820+55;l,t,rr,b=box
            poly=[[(u-x)*r['width']/w,(v-y)*r['height']/h] for u,v in [(l,t),(rr,t),(rr,b),(l,b)]]
            tile=ann.crop(im,poly)
            if tile.height>tile.width:tile=tile.rotate(-90,expand=True)
            tile.thumbnail((1600,600));tile.save(BATCH/'sheets'/f'final_{n}.jpg')
        result.append(dict(image_id=r['image_id'],regions=[dict(region_id='visual_final_date',polygon=poly)]))
    return result
if __name__=='__main__':
    import sys
    data=entries()
    ann.write(BATCH/'final_scene_proposals.json',data)
    if '--apply' in sys.argv:
        from scripts.remaining_visual_review import apply
        texts=['2026. 01. 04','2025. 12. 15','2027. 07. 1','2026.8.19 F.7','25.12.08 07시 25.12.10 10시']
        for row,text in zip(data,texts):
            row['evidence']='원본 장면 및 확대 영역 직접 확인한 AI 초안; 사람 승인 아님'
            a=row['regions'][0]
            a.update(kind='date_line',transcription=text,legibility='readable',role='expiry',role_evidence='인쇄 위치 및 소비기한 표제에 따른 AI 초안',field_states=dict(year='present',month='present',day='present'))
            if row['image_id']=='AMLC000486':
                a.update(legibility='partially_occluded',occluded_characters=[dict(field='day',description='반사와 포장 무늬가 겹쳐 일 마지막 숫자가 불명확')])
                a['field_states']['day']='unreadable'
        p=BATCH/'visual_final_scenes.json';ann.write(p,data);apply(p)
