import copy
import unittest

from scripts.build_annotation_drafts import enrich, date_fields, role_hint
from scripts.ocr_annotations import new_region
from scripts.refine_annotation_drafts import visible_fields, plausible_date
from scripts.import_annotation_cache import stored_point


class DraftTests(unittest.TestCase):
    def test_oriented_edge_coordinates_return_to_stored_raster(self):
        # Stored raster 100 x 80; orientation 6 maps (10,20) -> (60,10).
        self.assertEqual(stored_point(60,10,100,80,6),(10,20))
        self.assertEqual(stored_point(20,90,100,80,8),(10,20))
        self.assertEqual(stored_point(90,60,100,80,3),(10,20))
        self.assertEqual(stored_point(60,90,100,80,7),(10,20))

    def test_refinement_filters_package_noise(self):
        for text in ('TEL 080-123-4567', '지방 2.5% 3%', '2027.07.08'):
            self.assertEqual(plausible_date(text), text=='2027.07.08')
        self.assertEqual(visible_fields('08/02/2027'),dict(year='present',month='present',day='present'))
        self.assertEqual(visible_fields('20270708'),dict(year='present',month='present',day='present'))
        self.assertEqual(visible_fields('07.08'),dict(year='absent',month='present',day='present'))

    def record(self, text='EXP 2027.07.08'):
        return dict(review={'status':'pending','reviewer':''},
            legacy_metadata={'condition_tags':['reflection','full_date']},
            quality_tags=[], group_evidence='', final_date='2030-01-01',
            regions=[new_region('r1', polygon=[[0,0],[100,0],[100,20],[0,20]], text=text)])

    def test_drafts_do_not_copy_truth_or_approve(self):
        r=enrich(self.record())
        self.assertEqual(r['regions'][0]['transcription'],'EXP 2027.07.08')
        self.assertEqual(r['regions'][0]['role'],'expiry')
        self.assertEqual(r['regions'][0]['status'],'pending')
        self.assertEqual(r['review'],{'status':'pending','reviewer':''})
        self.assertEqual(r['quality_tags'],['reflection'])

    def test_reviewed_and_checked_work_preserved(self):
        r=self.record();r['review']['reviewer']='human'
        original=copy.deepcopy(r)
        self.assertEqual(enrich(r),original)
        r=self.record();r['regions'][0]['status']='checked'
        original=copy.deepcopy(r['regions'])
        self.assertEqual(enrich(r)['regions'],original)

    def test_ambiguous_dates_remain_questions(self):
        self.assertIn('unknown',date_fields('08/02/2027').values())
        r=enrich(self.record('27.07.08'))
        self.assertIsNone(r['regions'][0]['role'])
        self.assertTrue(r['regions'][0]['draft']['issues'])
        self.assertEqual(role_hint('MFG / EXP'),None)

    def test_no_text_never_becomes_none_truth(self):
        r=enrich(self.record(''))
        self.assertEqual(r['regions'][0]['transcription'],'')
        self.assertEqual(r['regions'][0]['legibility'],'unknown')

    def test_repeated_enrichment_is_idempotent(self):
        r=enrich(self.record('27.07.08'))
        original=copy.deepcopy(r)
        self.assertEqual(enrich(r),original)

    def test_non_date_ocr_retained_as_context_not_required_region(self):
        r=self.record()
        r['regions'].append(new_region('nutrition','other',[[0,30],[80,30],[80,50],[0,50]],
            'Protein',{'type':'automatic_ocr_candidate'}))
        enrich(r)
        self.assertEqual(len(r['regions']),1)
        self.assertEqual(r['ocr_context'][0]['transcription'],'Protein')
        original=copy.deepcopy(r)
        self.assertEqual(enrich(r),original)


if __name__=='__main__':
    unittest.main()
