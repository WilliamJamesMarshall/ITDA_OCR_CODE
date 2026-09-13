import unittest
from unittest.mock import patch
import numpy as np
from src.thin_dot_recovery import recover_thin_dots, thin_views
from src.date_extraction import select_date


class ThinDotTest(unittest.TestCase):
    def setUp(self):
        self.image = np.full((120, 700, 3), 230, np.uint8)
        self.image[30:33, 40:44] = 0
        self.quad = ((0.,0.), (699.,0.), (699.,119.), (0.,119.))

    def reading(self, text, score=.99):
        return text, score, tuple([score]*len(text))

    def run_reads(self, primary, english=None):
        with patch('src.thin_dot_recovery.dot_row_proposals', return_value=[self.quad]):
            return recover_thin_dots(self.image, [], lambda crops: primary,
                                     (lambda crops:english) if english is not None else None)

    def test_repeated_full_date_and_clock(self):
        added, _, _, _ = self.run_reads([self.reading('2028.03.04 13:50')]*2)
        self.assertEqual(select_date(added, final=True).final_date, '2028-03-04')

    def test_same_value_two_orders_is_not_forced(self):
        added, _, _, _ = self.run_reads([self.reading('25.10.25 11:50')]*2)
        self.assertEqual(select_date(added, final=True).final_date, '2025-10-25')

    def test_single_hit_conflict_and_weak_digits_rejected(self):
        for reads in ([self.reading('2028.03.04'), self.reading('noise')],
                      [self.reading('2028.03.04'), self.reading('2029.03.04')],
                      [self.reading('2028.03.04', .6)]*2):
            self.assertFalse(self.run_reads(reads)[0])

    def test_cross_model_conflict_rejected(self):
        self.assertFalse(self.run_reads([self.reading('2028.03.04')]*2,
                                        [self.reading('2029.03.04')]*2)[0])

    def test_overlapping_rows_cannot_supply_conflicting_or_duplicate_votes(self):
        for second, count in [('2028.03.04', 1), ('2029.03.04', 0)]:
            shifted = tuple((x+2,y) for x,y in self.quad)
            with patch('src.thin_dot_recovery.dot_row_proposals', return_value=[self.quad,shifted]):
                readings = [self.reading('2028.03.04')]*2 + [self.reading(second)]*2
                result = recover_thin_dots(self.image, [], lambda crops:readings)
            self.assertEqual(len(result[0]), count)

    def test_role_must_be_printed_in_both_views(self):
        self.assertFalse(self.run_reads([self.reading('28.03.04까지'), self.reading('28.03.04')])[0])

    def test_clock_never_gets_a_year(self):
        self.assertFalse(self.run_reads([self.reading('10:20 13:57')]*2)[0])

    def test_identical_views_and_invalid_geometry_rejected(self):
        self.assertFalse(thin_views(np.full_like(self.image, 230), self.quad))
        self.assertFalse(thin_views(self.image, ()))

    def test_budget_and_no_lines_or_identifiers_needed(self):
        with patch('src.thin_dot_recovery.dot_row_proposals', return_value=[]) as p:
            self.assertFalse(recover_thin_dots(self.image, [], lambda c: [])[0])
        self.assertEqual(p.call_args.kwargs, dict(limit=6, thin=True))

if __name__ == '__main__':
    unittest.main()
