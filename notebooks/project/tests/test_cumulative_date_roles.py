"""Printed-role regressions from the round 4/5 diagnosis; no image inference."""
import unittest
from dataclasses import replace
from src.date_extraction import DateContext, OCRLine, _inline_role, select_date
from src.budget_pipeline import output_selection


class CumulativeDateRoleTest(unittest.TestCase):
    def test_japanese_manufacturing_label_is_not_an_unlabelled_date(self):
        self.assertEqual(_inline_role('製造年月日 2025.09.25'), 'start')

    def test_japanese_manufacturer_prose_is_not_a_date_role(self):
        for label in ('製造者', '製造元', '製造所', '製造方法', '製造工程', '製造 されています'):
            with self.subTest(label=label):
                self.assertIsNone(_inline_role(label + ' 東京都'))

    def test_printed_japanese_expiry_manufacture_pair_resolves_order(self):
        lines = [OCRLine('賞味期限 26.09.24', .99, (0, 0, 350, 40)),
                 OCRLine('製造 25.09.25', .99, (0, 60, 350, 100))]
        result = output_selection(select_date(lines, context=DateContext()))
        self.assertEqual(result.final_date, '2026-09-24')

    def test_manufacturing_date_alone_does_not_supply_expiry_fields(self):
        result = output_selection(select_date(
            [OCRLine('製造年月日 2025.09.25', .99, (0, 0, 350, 40))], context=DateContext()))
        self.assertIsNone(result.final_date)

    def test_retracted_partial_fields_do_not_survive_negative_role(self):
        old = output_selection(select_date(
            [OCRLine('소비기한 2026.05', .99, (0, 0, 350, 40))], context=DateContext()))
        for reason in ('negative-context', 'expiry-not-printed'):
            retracted = replace(old, reason=reason, confident=False)
            with self.subTest(reason=reason):
                self.assertIsNone(output_selection(retracted, previous=old).final_date)

    def skewed_pair(self, end_score=.74, end_box=(462, 901, 499, 938)):
        return [OCRLine('부터', .98, (464, 876, 498, 908)),
                OCRLine('21.01.07', .995, (282, 902, 435, 935)),
                OCRLine('까지', end_score, end_box),
                OCRLine('21.02.05', .996, (279, 926, 435, 964))]

    def test_aligned_pair_supports_one_weaker_but_literal_role_label(self):
        result = output_selection(select_date(self.skewed_pair(), context=DateContext()))
        self.assertEqual(result.final_date, '2021-02-05')

    def test_low_confidence_or_misaligned_label_does_not_certify_pair(self):
        from src.date_extraction import _printed_pair_roles, parse_dates
        for lines in (self.skewed_pair(.50), self.skewed_pair(end_box=(520, 901, 557, 938))):
            with self.subTest(lines=lines):
                self.assertEqual(_printed_pair_roles(lines, [parse_dates(l.text) for l in lines]), {})

    def test_standalone_japanese_labels_keep_their_pair_roles(self):
        from src.date_extraction import _printed_pair_roles, parse_dates
        lines = self.skewed_pair(.99)
        lines[0] = replace(lines[0], text='製造年月日')
        lines[2] = replace(lines[2], text='賞味期限')
        roles = _printed_pair_roles(lines, [parse_dates(l.text) for l in lines])
        self.assertEqual(roles, {1: 'start', 3: 'end'})


if __name__ == '__main__':
    unittest.main()
