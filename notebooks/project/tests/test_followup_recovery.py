import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

from src.date_extraction import OCRLine, select_date
from src.pipeline import PipelineConfig, _label_crop_bounds, predict_image


def line(text,box=(0,0,200,30),score=.99,variant='original'):
    return OCRLine(text,score,box,variant=variant)


class PartialLegendTests(unittest.TestCase):
    def test_compact_month_year_not_six_digit_full_date(self):
        selected=select_date([line('022022'),line('유통기한 별도표시 (월/년 순)',(0,200,300,240))])
        self.assertEqual(selected.final_date,'2022-02-NONE')
        self.assertTrue(selected.stop_ocr)

    def test_separated_month_year_beats_cross_pass_compact_reading(self):
        selected=select_date([line('022022',variant='roi'),line('02/2022'),
                              line('읽는법 예) MM/YYYY → YYYY년 MM월 01일까지',(0,150,300,190))])
        self.assertEqual(selected.final_date,'2022-02-NONE')

    def test_without_legend_no_compact_month_year_assumption(self):
        self.assertNotEqual(select_date([line('022022')]).final_date,'2022-02-NONE')

    def test_different_frame_legend_is_not_borrowed(self):
        self.assertNotEqual(select_date([line('022022'),line('MM/YYYY',variant='other')]).reason,'printed-month-year')

    def test_two_partial_targets_do_not_share_distant_legend(self):
        rows=[line('02/2022'),line('03/2023',(0,100,200,130)),line('별도표시 MM/YYYY',(0,400,200,430))]
        self.assertNotEqual(select_date(rows).reason,'printed-month-year')

    def test_explicit_full_expiry_is_not_hidden(self):
        rows=[line('02/2022'),line('EXP 2023.04.05',(0,100,250,130)),line('별도표시 MM/YYYY',(0,400,200,430))]
        self.assertEqual(select_date(rows).final_date,'2023-04-05')

    def test_invalid_month_and_weak_digits_not_promoted(self):
        for text,score in [('13/2022',.99),('02/2022',.5)]:
            result=select_date([line(text,score=score),line('MM/YYYY',(0,50,200,80))])
            self.assertNotEqual(result.reason,'printed-month-year')


class RoleCropAndStopTests(unittest.TestCase):
    def test_unique_label_guides_bounded_crop(self):
        image=np.zeros((500,600,3),dtype=np.uint8)
        self.assertEqual(_label_crop_bounds(image,[line('까지',(350,430,390,460))]),(0,370,420,490))

    def test_ambiguous_or_narrative_labels_do_not_guide_crop(self):
        image=np.zeros((500,600,3),dtype=np.uint8)
        self.assertIsNone(_label_crop_bounds(image,[line('소비기한 상단표시')]))
        self.assertIsNone(_label_crop_bounds(image,[line('까지'),line('EXP')]))

    def test_missing_region_uses_label_before_unrelated_numbers(self):
        class Backend:
            def __init__(self):self.variants=[]
            def recognize(self,image,*,detector,variant):
                self.variants.append(variant)
                if variant=='original':return [line('까지',(350,430,390,460))]
                return [line('2026.09.20'),line('까지',(210,0,250,30))]
        backend=Backend()
        with patch('src.pipeline._load_bgr',return_value=np.zeros((500,600,3),dtype=np.uint8)):
            result=predict_image(Path('example.jpg'),backend,PipelineConfig())
        self.assertEqual(result.final_date,'2026-09-20')
        self.assertEqual(backend.variants,['original','label-roi'])

    def test_strong_local_pair_stops_without_extra_ocr(self):
        result=select_date([line('01.07.2020'),line('01.07.2023',(0,40,200,70))])
        self.assertEqual(result.final_date,'2023-07-01')
        self.assertTrue(result.stop_ocr)
        self.assertFalse(result.order_resolved)

    def test_weak_local_pair_does_not_gain_new_fast_exit(self):
        result=select_date([line('01.07.2020',score=.86),line('01.07.2023',(0,40,200,70),score=.86)])
        self.assertFalse(result.stop_ocr)


if __name__=='__main__':unittest.main()
