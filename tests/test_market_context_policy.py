import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.date_extraction import DateContext, OCRLine, select_date, submission_fields
from src.pipeline import PipelineConfig, predict_image


def line(text, box=(0,0,400,40), score=.99, variant='original'):
    return OCRLine(text,score,box,variant=variant)


def choose(*lines, context=DateContext(), final=True):
    return select_date(lines,context=context,final=final)


class MarketContextPolicyTest(unittest.TestCase):
    def test_requested_examples_without_image_identifiers(self):
        for raw,expected in [('26.04.24 B 17:20','2026-04-24'),('26.06.17 09:23 F2','2026-06-17'),
                             ('26.05.30 06:18 F2','2026-05-30'),('26.06.04 B 11:32','2026-06-04'),
                             ('26.08.30 A 08:14','2026-08-30'),('27.01.02 B','2027-01-02'),
                             ('26.02.24','2026-02-24')]:
            with self.subTest(raw=raw):
                result=choose(line('소비기한 '+raw+' 까지'))
                self.assertEqual(result.final_date,expected)
                self.assertEqual(result.policy_details['market'],'KR')
                self.assertEqual(result.candidates[0].order_reason,'market_policy:korean_food_context')

    def test_clock_lot_and_barcode_do_not_supply_date_digits(self):
        result=choose(line('소비기한 26.06.17 09:23 F2 까지'),line('8801062 879090',(0,80,400,120)))
        self.assertEqual(result.final_date,'2026-06-17')
        self.assertEqual(result.policy_details['auxiliary_time'],'09:23')
        self.assertEqual(result.policy_details['lot_code'],'F2')
        self.assertFalse(result.policy_details['confidence_is_calibrated'])
        for raw in ('17:20','09:23:04','8801062879090','20260424','8801062 879090'):
            self.assertIsNone(choose(line(raw)).final_date,raw)
        self.assertEqual(choose(line('EXP 19 09 2021')).final_date,'2021-09-19')
        self.assertEqual(choose(line('소비기한 2026 04 24')).final_date,'2026-04-24')
        separated=choose(line('소비기한 26.04.24 B'),line('17:20',(0,45,180,85)))
        self.assertEqual(separated.policy_details['auxiliary_time'],'17:20')

    def test_separators_and_date_only_glyph_repair(self):
        for raw in ('26 - 04 - 24','26 / 04 / 24','26 04 24','26·04·24','26:04:24'):
            self.assertEqual(choose(line('소비기한 '+raw)).final_date,'2026-04-24')
        result=choose(line('소비기한 26.O6.17 F2'))
        self.assertEqual(result.final_date,'2026-06-17')
        self.assertTrue(result.candidates[0].repaired)
        self.assertIn('26.O6.17',result.policy_details['raw_text'])
        self.assertFalse(result.digits_confident)

    def test_invalid_domestic_date_cannot_be_flipped_or_repaired(self):
        for raw in ('26.02.29','26.14.04'):
            result=choose(line('소비기한 '+raw))
            self.assertIsNone(result.final_date)
            self.assertEqual(result.policy_details['status'],'REVIEW_REQUIRED')
        self.assertEqual(choose(line('소비기한 24.02.29')).final_date,'2024-02-29')
        self.assertEqual(choose(line('소비기한 99.12.31')).final_date,'2099-12-31')

    def test_invalid_market_calendar_keeps_digit_recovery_open(self):
        result=choose(line('소비기한 26.02.29'),final=False)
        self.assertFalse(result.stop_ocr)
        self.assertIsNone(result.final_date)
        self.assertEqual(result.policy_details['status'],'REVIEW_REQUIRED')

    def test_explicit_orders_override_market_even_on_korean_import_label(self):
        for raw,expected in [('소비기한 DDMMYY 050926','2026-09-05'),
                             ('소비기한 일월년순 26.04.24','2024-04-26'),
                             ('소비기한 MM/DD/YYYY 03/06/2028','2028-03-06')]:
            self.assertEqual(choose(line(raw)).final_date,expected)
        self.assertEqual(choose(line('BBD 20/06/2026')).final_date,'2026-06-20')

    def test_unknown_and_imported_context_review_preserves_alternatives(self):
        result=choose(line('04.05.06'))
        self.assertIsNone(result.final_date)
        self.assertEqual(result.policy_details['status'],'REVIEW_REQUIRED')
        self.assertEqual(len({c.iso for c in result.candidates}),3)
        self.assertEqual(submission_fields(result.final_date)['final_date'],'NONE-NONE-NONE')
        imported=choose(line('소비기한 26.04.24'),line('수입판매원 한국무역',(0,60,400,100)))
        self.assertIsNone(imported.final_date)
        self.assertEqual(imported.policy_details['status'],'REVIEW_REQUIRED')

    def test_korean_background_must_not_leak_to_foreign_date(self):
        for hint in (line('소비기한',(5000,5000,5300,5040)),line('소비기한',variant='roi-1'),line('한글 상품 설명')):
            self.assertIsNone(choose(line('26.04.24'),hint).final_date)

    def test_explicit_metadata_is_food_and_language_scoped(self):
        self.assertEqual(choose(line('26.04.24'),context=DateContext('KR',language='ko')).final_date,'2026-04-24')
        self.assertIsNone(choose(line('26.04.24'),context=DateContext('KR',product_type='cosmetic',language='ko')).final_date)
        self.assertEqual(choose(line('EXP 03/06/2028'),context=DateContext('US')).final_date,'2028-03-06')
        self.assertEqual(choose(line('EXP 03/06/2028'),context=DateContext('GB')).final_date,'2028-06-03')
        self.assertIsNone(choose(line('소비기한 26.04.24'),line('수입판매원',(0,50,400,90)),
                                 context=DateContext('KR',language='ko')).final_date)

    def test_import_evidence_survives_mapped_roi_without_mixing_local_boxes(self):
        target=replace(line('소비기한 26.04.24',variant='roi-1'),original_box=(100,100,500,140))
        imported=replace(line('수입판매원',(4000,4000,4400,4040)),original_box=(100,150,500,190))
        self.assertIsNone(choose(target,imported).final_date)
        self.assertEqual(choose(target,replace(imported,original_box=(5000,5000,5400,5040))).final_date,'2026-04-24')

    def test_manufacturing_is_not_the_expiry(self):
        result=choose(line('제조일자 26.04.24'),line('소비기한 27.04.24',(0,60,400,100)))
        self.assertEqual(result.final_date,'2027-04-24')
        self.assertEqual(result.policy_details['manufactured_date'],'2026-04-24')
        self.assertIsNone(choose(line('제조일자 26.04.24')).final_date)

    def test_unknown_clear_digits_stop_without_inventing_order(self):
        class Backend:
            calls=0
            def recognize(self,image,*,detector,variant):
                self.calls+=1
                return [line('26.04.24')]
        backend=Backend()
        with patch('src.pipeline._load_bgr',return_value=np.zeros((100,500,3),dtype=np.uint8)):
            result=predict_image(Path('unseen.jpg'),backend,PipelineConfig())
        self.assertEqual(backend.calls,1)
        self.assertIsNone(result.final_date)
        self.assertEqual(result.selection.policy_details['status'],'REVIEW_REQUIRED')
        self.assertEqual(result.trace['outcomes'][0]['selection']['policy_details']['status'],'REVIEW_REQUIRED')


if __name__=='__main__':unittest.main()
