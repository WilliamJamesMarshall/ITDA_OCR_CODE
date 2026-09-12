"""Inspection-only enlarged crops for the last ambiguous draft fields."""
from PIL import Image,ImageDraw,ImageFont
from scripts import ocr_annotations as ann
from scripts.complete_remaining_drafts import BATCH

TARGETS=[(2248,'source_003'),(2336,'source_002'),(2429,'source_001'),(2477,'source_001'),(2505,'source_002'),(2588,'source_001'),(488,'ocr_066'),(1124,'cache_004'),(1124,'cache_006'),(1124,'cache_010'),(1518,'deep_004'),(821,'deep_002'),(824,'deep_000'),(824,'deep_002')]+[(831,f'deep_{i:03d}') for i in range(7)]
def main():
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',18)
    for idx,(n,rid) in enumerate(TARGETS):
        r=ann.read(ann.record_path(('BMLC' if n>=2247 else 'AMLC')+f'{n:06d}'))
        a=next(a for a in r['regions'] if a['region_id']==rid)
        with Image.open(ann.source_path(r)) as im:
            xs=[p[0] for p in a['polygon']];ys=[p[1] for p in a['polygon']];w=max(xs)-min(xs);h=max(ys)-min(ys)
            tile=im.convert('RGB').crop((max(0,min(xs)-w),max(0,min(ys)-h*2),min(im.width,max(xs)+w*2),min(im.height,max(ys)+h*2)))
        board=Image.new('RGB',(1600,850),'#eee');d=ImageDraw.Draw(board)
        for j,angle in enumerate([0,90,180,270]):
            t=tile.rotate(angle,expand=True);scale=min(790/t.width,370/t.height);t=t.resize((max(1,round(t.width*scale)),max(1,round(t.height*scale))))
            x=j%2*800;y=j//2*425
            board.paste(t,(x,y+45));d.text((x+5,y+3),r['image_id']+' '+rid+f' rotation {angle}',font=font,fill='black')
        board.save(BATCH/'sheets'/f'detail_{idx:02d}.jpg',quality=96)
    print(len(TARGETS))
if __name__=='__main__':main()
