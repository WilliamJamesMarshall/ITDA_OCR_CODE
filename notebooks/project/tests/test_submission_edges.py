"""Regression boundaries for formatting repair versus unsupported digit inference."""
import unittest
from src.date_extraction import OCRLine, DateContext, select_date
from src.budget_pipeline import output_selection


class EvidenceBoundaryTests(unittest.TestCase):
    def output(self, text):
        selection = select_date([OCRLine(text,.98,(10,10,300,40))], final=False, context=DateContext())
        return selection, output_selection(selection)

    def test_space_inside_month_does_not_invent_digits(self):
        selection, output = self.output('2021.1 1.26')
        self.assertEqual(output.final_date, '2021-11-26')
        self.assertTrue(any(c.repair_kind == 'format-only' for c in selection.candidates))

    def test_month_word_zero_is_not_a_year_digit_repair(self):
        selection, output = self.output('09 0CT 21')
        self.assertEqual(output.final_date, '2021-10-09')
        self.assertTrue(any(c.repair_kind == 'format-only' for c in selection.candidates))

    def test_missing_year_digit_is_not_submitted(self):
        selection, output = self.output('026.01.21')
        self.assertIsNone(output.final_date)
        self.assertTrue(any(c.repair_kind == 'inferred-digits' for c in selection.candidates))

    def test_real_manufacturing_label_stays_negative(self):
        _, output = self.output('제조일자 2026.01.21')
        self.assertIsNone(output.final_date)


if __name__ == '__main__':
    unittest.main()
