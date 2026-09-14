import unittest
from src.date_extraction import _policy_parses, parse_dates, OCRLine, select_date, DateContext
from src.budget_pipeline import output_selection


class PaperDateBoundaryTests(unittest.TestCase):
    def test_colon_inside_full_date_survives_clock_mask(self):
        self.assertIn('2026-05-03', [p.value.isoformat() for p in _policy_parses('2026.05:03')])

    def test_attached_clock_does_not_become_four_digit_year(self):
        dates = list(parse_dates('28.04.1912:58 까지'))
        self.assertIn('2028-04-19', [p.value.isoformat() for p in dates])
        self.assertNotIn('1912-04-28', [p.value.isoformat() for p in dates])
        self.assertTrue(all(p.raw == '28.04.19' for p in dates))

    def test_standalone_clocks_and_quantities_stay_masked(self):
        for text in ('12:58', '2026 12:58', '12.5%', '2026.05 12:58'):
            self.assertEqual(_policy_parses(text), [], text)

    def test_four_digit_trailing_year_is_still_supported(self):
        self.assertIn('2019-04-28', [p.value.isoformat() for p in _policy_parses('28.04.2019 12:58')])

    def test_geometric_reread_keeps_nearby_printed_order(self):
        lines = [OCRLine('BEST BEFORE 일/월/년 순', .98, (100, 100, 300, 125),
                         original_box=(100, 100, 300, 125)),
                 OCRLine('22/12/21', .99, (0, 0, 200, 30), source='paddle-geometric',
                         variant='geometric-rows', original_box=(100, 150, 300, 180))]
        selected = select_date(lines, context=DateContext())
        self.assertEqual(output_selection(selected).final_date, '2021-12-22')

    def test_cross_pass_legend_requires_mapped_geometry(self):
        lines = [OCRLine('BEST BEFORE 일/월/년 순', .98, (100, 100, 300, 125)),
                 OCRLine('22/12/21', .99, (100, 150, 300, 180), source='paddle-geometric')]
        self.assertNotEqual(output_selection(select_date(lines, context=DateContext())).final_date, '2021-12-22')

    def test_closer_distinct_date_blocks_cross_pass_legend(self):
        lines = [OCRLine('일/월/년 순', .98, (100, 100, 300, 125), original_box=(100,100,300,125)),
                 OCRLine('22/12/21', .99, (100, 180, 300, 210), source='paddle-geometric',
                         original_box=(100,180,300,210)),
                 OCRLine('2024.12.21', .99, (100, 130, 300, 155), original_box=(100,130,300,155))]
        selected = select_date(lines, context=DateContext())
        self.assertFalse(any(c.iso == '2021-12-22' and c.order_reason == 'explicit_order' for c in selected.candidates))

    def test_partial_crop_does_not_remove_printed_day(self):
        lines = [OCRLine('2025.12.01', .98, (100,100,300,130), original_box=(100,100,300,130)),
                 OCRLine('소비기한', .99, (100,140,280,165), original_box=(100,140,280,165)),
                 OCRLine('2025.12', .99, (100,100,250,130), variant='roi', original_box=(100,100,250,130))]
        self.assertEqual(output_selection(select_date(lines, context=DateContext())).final_date, '2025-12-01')


if __name__ == '__main__':
    unittest.main()
