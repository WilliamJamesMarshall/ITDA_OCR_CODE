"""Disposable two-image UI smoke fixture. Never reads/writes production records."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='itda-annotation-ui-test-') as directory:
        root=Path(directory)
        output=root/'annotations'
        image=ann.Image.new('RGB',(320,120),'white')
        ann.ImageDraw.Draw(image).text((20,40),'EXP 2027.07.08',fill='black')
        image.save(root/'fixture.png')
        for number in (1,2):
            region=ann.new_region('date_1',polygon=[[15,35],[180,35],[180,65],[15,65]],text='EXP 2027.07.08')
            region.update(role='expiry',role_basis='visible_header',role_evidence='EXP',legibility='readable',
                field_states=dict(year='present',month='present',day='present'))
            image_id=f'AMLC{number:06d}'
            record=dict(schema_version=1,image_id=image_id,source_image_id=f'{number:06d}',
                image_path='fixture.png',image_sha256=ann.sha(root/'fixture.png'),width=320,height=120,
                source_dataset='additional',final_date='2027-07-08',final_date_review={'status':'approved'},
                seen_in_development=False,legacy_metadata={'condition_tags':[]},group_id='fixture',
                group_evidence='Synthetic test image',difficulty='easy',quality_tags=[],notes='TEST ONLY',
                regions=[region],revision=0,review=dict(status='pending',reviewer='',approved_at=None,
                date_regions_complete=False,header_regions_complete=False,quality_reviewed=False,
                group_reviewed=False,no_date_regions=False))
            ann.write(ann.record_path(image_id,output),record)
        print(f'Disposable fixture directory: {directory}',flush=True)
        ann.serve(8766,root,output)
