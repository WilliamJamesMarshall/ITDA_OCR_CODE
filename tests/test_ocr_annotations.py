import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from scripts.ocr_annotations import (IMMUTABLE, audit, crop, export_approved, new_region,
    accept_draft, polygon_errors, read, record_path, save_review, sha, suggest_missing_text, validate, write)


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.output=self.root/'annotations'
        Image.new('RGB',(100,80),'black').save(self.root/'sample.png')
        region=new_region('date_1','date_line',[[10,10],[90,10],[90,30],[10,30]],'EXP 2027.07.08',{'type':'automatic_ocr_candidate'})
        self.record=dict(schema_version=1,image_id='AMLC000001',source_image_id='000001',
            image_path='sample.png',image_sha256=sha(self.root/'sample.png'),width=100,height=80,
            source_dataset='product',final_date='2027-07-08',final_date_review={'status':'approved'},
            seen_in_development=True,legacy_metadata={},group_id='product-A',group_evidence='',
            difficulty='easy',quality_tags=[],notes='',regions=[region],revision=0,
            review=dict(status='pending',reviewer='',approved_at=None,date_regions_complete=False,
                header_regions_complete=False,quality_reviewed=False,group_reviewed=False,no_date_regions=False))
        write(record_path(self.record['image_id'],self.output),self.record)

    def checked(self):
        result=copy.deepcopy(self.record)
        result['group_evidence']='Fixture group reviewed against source assets'
        result['review'].update(reviewer='Fixture reviewer',date_regions_complete=True,
            header_regions_complete=True,quality_reviewed=True,group_reviewed=True)
        result['regions'][0].update(status='checked',legibility='readable',role='expiry',
            role_basis='visible_header',role_evidence='EXP printed on line',
            field_states={'year':'present','month':'present','day':'present'})
        return result

    def test_source_final_date_does_not_approve_ocr(self):
        self.assertEqual(validate(self.record),[])
        self.assertTrue(validate(self.record,True))
        exported=export_approved(self.root,self.output)
        self.assertEqual(exported['recognition_crops'],0)
        self.assertEqual(exported['detection_scenes'],0)

    def test_scoped_review_http_index_and_approval(self):
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from scripts import ocr_annotations as ann
        other=copy.deepcopy(self.record)
        other['image_id']='AMLC000002'
        write(record_path(other['image_id'],self.output),other)
        cohort=self.root/'cohort.json'
        write(cohort,{'image_ids':['AMLC000001']})
        ready=threading.Event(); servers=[]
        def factory(address,handler):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            servers.append(server);ready.set();return server
        with patch.object(ann,'ThreadingHTTPServer',side_effect=factory),patch.object(ann.secrets,'token_urlsafe',return_value='fixture-token'):
            worker=threading.Thread(target=ann.serve,args=(0,self.root,self.output,cohort),daemon=True)
            worker.start();self.assertTrue(ready.wait(5))
            server=servers[0];url=f'http://127.0.0.1:{server.server_port}'
            try:
                def get(path):
                    with urllib.request.urlopen(url+path) as response:return json.load(response)
                self.assertEqual(get('/api/scope'),{'restricted':True,'count':1})
                self.assertEqual([r['image_id'] for r in get('/api/index')],['AMLC000001'])
                def post(record):
                    payload=json.dumps({'record':record,'revision':0}).encode()
                    request=urllib.request.Request(url+'/api/approve-draft',data=payload,headers={'Content-Type':'application/json','X-Annotation-Token':'fixture-token'})
                    return urllib.request.urlopen(request)
                with self.assertRaises(urllib.error.HTTPError) as caught:post(other)
                self.assertEqual(caught.exception.code,403)
                with post(self.checked()) as response:
                    self.assertEqual(json.load(response)['review']['status'],'approved')
                self.assertEqual(read(record_path(other['image_id'],self.output))['revision'],0)
            finally:
                server.shutdown();worker.join(5);server.server_close()

    def test_user_bulk_acceptance_preserves_missing_annotation_gate(self):
        from scripts.accept_annotation_batch import prepare
        candidate,errors=prepare(self.record,'fixture_hash','fixture_decision')
        self.assertEqual(candidate['user_acceptance']['status'],'approved')
        self.assertTrue(errors)
        self.assertEqual(candidate['regions'],self.record['regions'])
        self.assertFalse(candidate['user_acceptance']['individually_visually_verified'])
        candidate,errors=prepare(self.checked(),'fixture_hash','fixture_decision')
        self.assertFalse(errors)
        self.assertEqual(candidate['review']['method'],'explicit_user_chat_bulk_as_is')

    def test_edit_supersedes_as_is_acceptance(self):
        from scripts.accept_annotation_batch import prepare
        candidate,errors=prepare(self.checked(),'fixture_hash','fixture_decision')
        saved=save_review(candidate['image_id'],candidate,0,True,self.root,self.output)
        saved['notes']='Changed after acceptance'
        revised=save_review(saved['image_id'],saved,saved['revision'],False,self.root,self.output)
        self.assertEqual(revised['user_acceptance']['status'],'superseded_by_edit')
        self.assertEqual(revised['review']['status'],'pending')

    def test_explicit_accept_draft_replaces_repeated_checks(self):
        candidate=self.checked()
        candidate['regions'][0]['status']='pending'
        for key in ('date_regions_complete','header_regions_complete','quality_reviewed','group_reviewed'):
            candidate['review'][key]=False
        accepted=accept_draft(candidate)
        self.assertEqual(validate(accepted,True),[])
        self.assertEqual(candidate['regions'][0]['status'],'pending')
        self.assertEqual(read(record_path(candidate['image_id'],self.output))['review']['status'],'pending')
        saved=save_review(candidate['image_id'],accepted,0,True,self.root,self.output)
        self.assertEqual(saved['review']['status'],'approved')

    def test_accept_draft_cannot_hide_missing_annotations(self):
        with self.assertRaises(ValueError):
            accept_draft(self.record)
        candidate=self.checked()
        candidate['regions']=[]
        with self.assertRaises(ValueError):
            accept_draft(candidate)

    def test_missing_human_confirmation_blocks_approval(self):
        for field in ['reviewer','date_regions_complete','header_regions_complete','quality_reviewed','group_reviewed']:
            record=self.checked()
            record['review'][field]='' if field=='reviewer' else False
            with self.assertRaises(ValueError):
                save_review(record['image_id'],record,0,True,self.root,self.output)

    def test_approval_export_and_revocation(self):
        record=self.checked()
        approved=save_review(record['image_id'],record,0,True,self.root,self.output)
        self.assertEqual(approved['review']['status'],'approved')
        self.assertIsNotNone(approved['review']['approved_at'])
        self.assertTrue((self.output/'history/AMLC000001/000000.json').exists())
        report=export_approved(self.root,self.output)
        self.assertEqual((report['recognition_crops'],report['detection_scenes']),(1,1))
        text=(Path(report['directory'])/'recognition_pool.txt').read_text(encoding='utf-8')
        self.assertTrue(text.endswith('\tEXP 2027.07.08\n'))
        approved['regions'][0]['transcription']='EXP 2027.07.09'
        saved=save_review(approved['image_id'],approved,1,False,self.root,self.output)
        self.assertEqual(saved['review']['status'],'pending')
        self.assertIsNone(saved['review']['approved_at'])
        self.assertEqual(export_approved(self.root,self.output)['recognition_crops'],0)

    def test_revision_conflict_and_immutable_label(self):
        with self.assertRaisesRegex(ValueError,'Revision conflict'):
            save_review(self.record['image_id'],self.record,1,False,self.root,self.output)
        self.record['final_date']='2028-01-01'
        with self.assertRaisesRegex(ValueError,'Immutable'):
            save_review(self.record['image_id'],self.record,0,False,self.root,self.output)

    def test_image_hash_change_blocks_save(self):
        Image.new('RGB',(100,80),'white').save(self.root/'sample.png')
        with self.assertRaisesRegex(ValueError,'Image changed'):
            save_review(self.record['image_id'],self.record,0,False,self.root,self.output)

    def test_bad_polygon_is_rejected(self):
        for polygon in ([[0,0],[2,2]],[[0,0],[120,0],[10,10]],
                        [[0,0],[20,20],[0,20],[20,0]],[[0,0],[float('nan'),2],[3,4]]):
            self.assertTrue(polygon_errors(polygon,100,80))

    def test_unreadable_date_still_counts_for_detection(self):
        record=self.checked()
        record['regions'][0].update(legibility='unreadable',transcription='')
        save_review(record['image_id'],record,0,True,self.root,self.output)
        report=export_approved(self.root,self.output)
        self.assertEqual(report['recognition_crops'],0)
        self.assertEqual(report['detection_scenes'],1)
        det=(Path(report['directory'])/'detection_pool.txt').read_text(encoding='utf-8')
        self.assertIn('"transcription": "date"',det)
        self.assertNotIn('###',det)

    def test_none_is_not_an_automatic_negative_scene(self):
        record=self.checked()
        record['final_date']='NONE'
        record['regions']=[]
        self.assertTrue(validate(record,True))
        record['review']['no_date_regions']=True
        self.assertEqual(validate(record,True),[])
        record['regions']=[self.checked()['regions'][0]]
        self.assertTrue(validate(record,True))

    def test_header_links_and_unknown_role_need_review(self):
        record=self.checked()
        record['regions'][0]['header_region_ids']=['missing']
        self.assertTrue(validate(record,True))
        record=self.checked()
        record['regions'][0]['role']=None
        self.assertTrue(validate(record,True))

    def test_crop_uses_original_polygon_and_masks_background(self):
        image=Image.new('RGB',(100,80),'black')
        result=crop(image,[[10,10],[50,10],[10,50]])
        self.assertEqual(result.size,(40,40))
        self.assertEqual(result.getpixel((2,2)),(0,0,0))
        self.assertEqual(result.getpixel((39,39)),(255,255,255))

    def test_occlusion_cannot_silently_enter_readable_training_labels(self):
        record=self.checked()
        record['regions'][0]['field_states']['day']='occluded'
        self.assertTrue(validate(record,True))
        record['regions'][0]['legibility']='partially_occluded'
        self.assertTrue(validate(record,True))
        record['regions'][0]['occluded_characters']=[{'location':'last date field','reason':'covered by fold'}]
        self.assertEqual(validate(record,True),[])

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            record_path('../../anything',self.output)

    def test_missing_header_ocr_is_a_candidate_and_preserves_date(self):
        record=copy.deepcopy(self.record)
        record['image_id']='BMLC002247'
        record['source_dataset']='additional'
        record['regions'].append(new_region('header_1','header',[[1,1],[30,1],[30,8],[1,8]],
            provenance={'type':'external_source_candidate'}))
        write(record_path(record['image_id'],self.output),record)
        with patch('src.pipeline.PaddleOCRBackend') as backend:
            backend.return_value.recognize_crops.return_value=[('까지',.94,())]
            report=suggest_missing_text(self.root,self.output)
        saved=read(record_path(record['image_id'],self.output))
        self.assertEqual(report['regions_processed'],1)
        self.assertEqual(saved['final_date'],record['final_date'])
        self.assertEqual(saved['regions'][0]['transcription'],record['regions'][0]['transcription'])
        self.assertEqual(saved['regions'][1]['transcription'],'까지')
        self.assertEqual(saved['regions'][1]['status'],'pending')
        self.assertEqual(saved['review']['status'],'pending')
        with patch('src.pipeline.PaddleOCRBackend') as backend:
            self.assertEqual(suggest_missing_text(self.root,self.output)['regions_processed'],0)
            backend.assert_not_called()


if __name__=='__main__':
    unittest.main()
