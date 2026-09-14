import unittest
from src.date_extraction import OCRLine, DateContext, select_date, _mask_auxiliary
from src.budget_pipeline import output_selection
from src.line_recovery import safe_numeric_change
from src.selective_recovery import needs_recovery


class Accuracy1600Tests(unittest.TestCase):
    def output(self, lines):
        selected = select_date(lines, context=DateContext())
        return output_selection(selected, base_partial=selected.is_partial).final_date

    def test_compact_expiry_survives_identifier_mask(self):
        self.assertEqual(self.output([OCRLine('사용기한 20280527', .99, (0,0,250,30))]), '2028-05-27')
        self.assertEqual(self.output([OCRLine('사용기한', .99, (0,0,90,30)),
                                     OCRLine('20280527', .99, (95,0,250,30))]), '2028-05-27')

    def test_bare_compact_identifier_not_promoted(self):
        self.assertIsNone(self.output([OCRLine('20280527', .99, (0,0,200,30))]))
        self.assertFalse(_mask_auxiliary('8801039006610').strip())

    def test_discount_date_not_expiry(self):
        self.assertIsNone(self.output([OCRLine('할인판매 시작일', .99, (0,0,200,25)),
                                      OCRLine('2021.03.05', .99, (0,28,200,60))]))

    def test_explicit_partial_not_blocked_by_unrelated_full(self):
        self.assertEqual(self.output([OCRLine('EXP', .99, (0,200,70,230)),
                                      OCRLine('11/2021', .99, (75,200,200,230)),
                                      OCRLine('05.11.1996-180/43', .99, (0,0,250,30))]), '2021-11-NONE')

    def test_recovery_cannot_delete_day_digit_of_readable_date(self):
        self.assertFalse(safe_numeric_change(OCRLine('2027.03.17', .9, (0,0,100,20)),
                                              OCRLine('2027.03.7A', .95, (0,0,100,20))))
        self.assertTrue(safe_numeric_change(OCRLine('02601.21', .9, (0,0,100,20)),
                                             OCRLine('202601.21', .95, (0,0,100,20))))

    def test_high_row_score_does_not_skip_uncertain_date_check(self):
        lines=[OCRLine('2026.09.08 L1', .954, (0,0,200,30))]
        self.assertTrue(needs_recovery(select_date(lines, context=DateContext()), lines))
