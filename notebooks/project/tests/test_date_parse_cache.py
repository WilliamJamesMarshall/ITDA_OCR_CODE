import unittest
from dataclasses import FrozenInstanceError
from src.date_extraction import parse_dates, _cached_date_parses, _parse_dates_uncached


class DateParseCacheTest(unittest.TestCase):
    def setUp(self):
        _cached_date_parses.cache_clear()

    def test_exact_text_only_and_uncached_equivalence(self):
        for text in ('2028.03.04', '03.04.28', '10.20', '10:20 13:57',
                     'DD.MM.YY 03.04.28', 'YY.MM.DD 03.04.28', 'PD 2028.03.04', 'garbage'):
            self.assertEqual(parse_dates(text), _parse_dates_uncached(text))
        self.assertEqual(_cached_date_parses.cache_info().misses, 8)
        parse_dates('2028.03.04')
        self.assertEqual(_cached_date_parses.cache_info().hits, 1)

    def test_callers_cannot_mutate_cached_results(self):
        result = parse_dates('2028.03.04')
        expected = result.copy()
        result.clear()
        self.assertEqual(parse_dates('2028.03.04'), expected)
        with self.assertRaises(FrozenInstanceError):
            expected[0].year_digits = 2

    def test_memory_is_bounded(self):
        for i in range(4200):
            parse_dates('not a date '+str(i))
        self.assertEqual(_cached_date_parses.cache_info().currsize, 4096)

if __name__ == '__main__':
    unittest.main()
