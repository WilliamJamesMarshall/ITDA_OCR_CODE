import unittest
from src.date_extraction import OCRLine, DateContext, select_date

class Stage04PolicyTests(unittest.TestCase):
    def test_packaging_material_is_not_packaging_date(self):
        from src.date_extraction import _inline_role
        self.assertIsNone(_inline_role('포장재질 폴리프로필렌'))
        self.assertEqual(_inline_role('포장일 2026.01.01'), 'start')

    def test_mapped_short_until_label_supplies_role_and_order(self):
        lines=[OCRLine('26.05.08',.99,(0,0,300,40),variant='roi',original_box=(500,1000,800,1040)),
               OCRLine('까지',.99,(820,1000,900,1040),original_box=(820,1000,900,1040))]
        self.assertEqual(select_date(lines,final=True,context=DateContext()).final_date,'2026-05-08')

    def test_split_year_month_day_survives_interleaved_unrelated_text(self):
        lines=[OCRLine('2026.03',.995,(571,1854,1376,2115)),
               OCRLine('22까지',.718,(1369,1931,1945,2194)),
               OCRLine('문구',.98,(0,1920,100,2040))]
        self.assertEqual(select_date(lines,final=True,context=DateContext()).final_date,'2026-03-22')

    def test_split_pair_does_not_cross_ocr_frames(self):
        from src.date_extraction import _split_year_month_day_windows
        self.assertEqual(_split_year_month_day_windows([
            OCRLine('2026.03',.99,(0,0,200,40)),
            OCRLine('22까지',.99,(205,0,300,40),variant='other')]),[])

    def test_split_pair_rejects_two_competing_days(self):
        from src.date_extraction import _split_year_month_day_windows
        self.assertEqual(_split_year_month_day_windows([
            OCRLine('2026.03',.99,(0,0,200,40)),
            OCRLine('22까지',.99,(205,0,300,40)),
            OCRLine('23까지',.99,(210,10,305,50))]),[])

    def test_heading_search_includes_right_and_below(self):
        import numpy as np
        from src.pipeline import _label_crop_bounds
        bounds=_label_crop_bounds(np.zeros((1000,1000,3),dtype=np.uint8),
                                  [OCRLine('소비기한',.99,(400,400,500,440))])
        self.assertGreater(bounds[2],500)
        self.assertGreater(bounds[3],600)

    def test_low_quality_digits_not_rescued_by_expiry_keyword(self):
        result=select_date([OCRLine('2072.07.12까지',.4,(0,0,300,40))],final=True,context=DateContext())
        self.assertIsNone(result.final_date)

    def test_legible_expiry_retained(self):
        self.assertEqual(select_date([OCRLine('2027.07.12까지',.98,(0,0,300,40))],final=True,context=DateContext()).final_date,'2027-07-12')

    def test_mapped_role_keeps_korean_order_evidence(self):
        lines=[OCRLine('25.10.17',.99,(0,0,300,40),original_box=(100,100,400,140)),
               OCRLine('25.10.17까지',.85,(0,0,300,40),variant='recovery',original_box=(100,100,400,140))]
        self.assertEqual(select_date(lines,final=True,context=DateContext()).final_date,'2025-10-17')

    def test_unrelated_expiry_does_not_supply_order(self):
        result=select_date([OCRLine('25.10.17',.99,(0,0,300,40),original_box=(100,100,400,140)),
                            OCRLine('까지',.99,(0,0,100,40),variant='other',original_box=(100,900,200,940))],final=True,context=DateContext())
        self.assertIsNone(result.final_date)

    def test_month_day_with_clock_not_replaced_by_bare_neighbour(self):
        result=select_date([OCRLine('10.13',.999,(0,0,100,30)),
                           OCRLine('10.14 09:45 PA',.97,(500,600,1000,640))],final=True,context=DateContext())
        self.assertEqual(result.final_date,'NONE-10-14')

    def test_dmy_mdy_ambiguity_is_not_silently_guessed(self):
        result=select_date([OCRLine('01 10 2026',.99,(0,0,300,40))],final=True,context=DateContext())
        self.assertIsNone(result.final_date)
