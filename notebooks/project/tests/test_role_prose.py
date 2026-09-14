import unittest
from src.date_extraction import OCRLine, DateContext, select_date, _link_roles
from src.budget_pipeline import output_selection


class RoleProseTests(unittest.TestCase):
    def test_manufacturer_and_material_prose_are_not_date_roles(self):
        for text in ('제조번호:20003', '제조업자:주식회사', '제조의뢰자:',
                     '은제조시설에서 제조하고있습니다', '폴리에틸렌(내포장)',
                     '빨대&포장-폴리프로필렌'):
            self.assertIsNone(_link_roles([OCRLine(text,.99,(0,0,300,30))])[0].role,text)

    def test_use_by_korean_is_positive(self):
        s=select_date([OCRLine('제조번호:20003',.99,(0,0,250,30)),
                       OCRLine('사용기한:2023.05.06',.99,(0,40,300,70))],context=DateContext())
        self.assertEqual(output_selection(s).final_date,'2023-05-06')

    def test_month_year_mfg_cannot_label_separate_expiry(self):
        lines=[OCRLine('30JUN2021',.98,(381,598,547,639)),
               OCRLine('MFG DEC2020',.93,(376,632,548,671))]
        self.assertIsNone(_link_roles(lines)[0].role)

    def test_actual_manufacturing_date_still_rejected(self):
        s=select_date([OCRLine('제조일자:2023.05.06',.99,(0,0,300,30))],context=DateContext())
        self.assertIsNone(output_selection(s).final_date)
