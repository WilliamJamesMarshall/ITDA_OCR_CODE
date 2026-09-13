import unittest

from src.date_extraction import DateContext, OCRLine, select_date
from src.verified_product_rules import VERIFIED_PRODUCT_RULES


class ApprovedProductRulesTests(unittest.TestCase):
    def select(self, date, identity):
        lines = [OCRLine(date, .99, (0, 100, 300, 140))]
        lines += [OCRLine(identity, .99, (0, 0, 400, 40))]
        return select_date(lines, final=True, context=DateContext(),
                           product_rules=VERIFIED_PRODUCT_RULES)

    def test_mocha_product_ymd(self):
        self.assertEqual(self.select('27.02.05', '모카골드 믹스커피 STICKS').final_date,
                         '2027-02-05')

    def test_barilla_package_dmy(self):
        self.assertEqual(self.select('01 10 2026', 'Barilla Fratelli Parma HOUDBAAR TOT').final_date,
                         '2026-10-01')

    def test_other_coffee_not_assumed_ymd(self):
        self.assertIsNone(self.select('27.02.05', '다른 믹스커피 STICKS').final_date)

    def test_barilla_brand_alone_not_enough(self):
        self.assertIsNone(self.select('01 10 2026', 'Barilla').final_date)

    def test_other_digits_use_same_rule_without_date_lookup(self):
        self.assertEqual(self.select('02 11 2028', 'Barilla Fratelli Parma HOUDBAAR TOT').final_date,
                         '2028-11-02')

    def test_mapped_date_keeps_verified_package_identity(self):
        lines = [OCRLine('01 10 2026', .99, (0, 0, 300, 40), variant='roi',
                         original_box=(500, 1000, 800, 1040)),
                 OCRLine('Barilla Fratelli Parma HOUDBAAR TOT', .99,
                         (500, 1100, 1000, 1140), original_box=(500, 1100, 1000, 1140))]
        self.assertEqual(select_date(lines, final=True, context=DateContext(),
                                     product_rules=VERIFIED_PRODUCT_RULES).final_date, '2026-10-01')

    def test_low_quality_identity_does_not_trigger_rule(self):
        lines = [OCRLine('01 10 2026', .99, (0, 100, 300, 140)),
                 OCRLine('Barilla Fratelli Parma HOUDBAAR TOT', .4, (0, 0, 400, 40))]
        self.assertIsNone(select_date(lines, final=True, context=DateContext(),
                                      product_rules=VERIFIED_PRODUCT_RULES).final_date)
