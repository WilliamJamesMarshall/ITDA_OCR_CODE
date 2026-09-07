import unittest

from src.date_extraction import OCRLine, parse_dates, select_date, submission_fields


def line(text, score=0.95, box=(0, 0, 300, 40), source="test", variant="original"):
    return OCRLine(text=text, score=score, box=box, source=source, variant=variant)


class ParseDatesTest(unittest.TestCase):
    def test_supported_formats(self):
        cases = {
            "2026.05.29": "2026-05-29",
            "2026년 5월 29일": "2026-05-29",
            "20260529": "2026-05-29",
            "26-05-29": "2026-05-29",
            "29 MAY 2026": "2026-05-29",
            "29/05/2026": "2026-05-29",
            "05/29/2026": "2026-05-29",
            "19 11 2027": "2027-11-19",
            "27.03 15 19:23": "2027-03-15",
            "2026.04.0771T1": "2026-04-07",
            "025.09.30": "2025-09-30",
            "126.07.19": "2026-07-19",
            "2027W3.02": "2027-03-02",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertIn(
                    expected, [item.value.isoformat() for item in parse_dates(raw)]
                )

    def test_ocr_confusion_is_repaired_only_to_a_valid_date(self):
        parsed = parse_dates("EXP 2O26.O5.29")
        self.assertEqual(parsed[0].value.isoformat(), "2026-05-29")
        self.assertTrue(parsed[0].repaired)

    def test_invalid_or_yearless_values_are_rejected(self):
        for raw in ("2026.13.02", "2025.02.29", "2020.09.20", "12.04", "8801234567890"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_dates(raw), [])


class DateSelectionTest(unittest.TestCase):
    def test_consumption_date_beats_manufacturing_date(self):
        selection = select_date(
            [line("제조 2025.06.26부터 소비기한 2026.06.25까지")], final=True
        )
        self.assertEqual(selection.final_date, "2026-06-25")

    def test_later_endpoint_wins_when_interval_keywords_are_split(self):
        lines = [
            line("2025.09.16", score=0.99, box=(100, 0, 300, 40)),
            line("부터", box=(320, 0, 380, 40)),
            line("2026.07.15", score=0.82, box=(100, 55, 300, 95)),
            line("까지", box=(320, 55, 380, 95)),
        ]
        self.assertEqual(select_date(lines).final_date, "2026-07-15")

    def test_later_endpoint_wins_for_equal_score_interval_without_keywords(self):
        lines = [
            line("2025.08.25", box=(100, 0, 300, 40)),
            line("2026.02.24", box=(100, 55, 300, 95)),
        ]
        self.assertEqual(select_date(lines).final_date, "2026-02-24")

    def test_final_selection_keeps_a_low_score_two_date_interval(self):
        lines = [
            line("제조 25.09.05", score=0.65, box=(100, 0, 300, 40)),
            line("26.03.04", score=0.65, box=(100, 55, 300, 95)),
        ]
        selection = select_date(lines, final=True)
        self.assertEqual(selection.final_date, "2026-03-04")

    def test_old_ocr_outlier_does_not_hide_the_current_interval(self):
        lines = [
            line("2020.11.02", score=0.80, box=(100, 0, 300, 40)),
            line("제조 2025.09.03부터", box=(100, 55, 380, 95)),
            line("소비기한 2026.03.02까지", box=(100, 110, 450, 150)),
        ]
        self.assertEqual(select_date(lines).final_date, "2026-03-02")

    def test_far_future_ocr_outlier_does_not_replace_plausible_interval(self):
        lines = [
            line("제조 2025.09.22부터", box=(100, 0, 380, 40)),
            line("소비기한 2026.05.21까지", score=0.90, box=(100, 55, 450, 95)),
            line("2028.05.21", score=0.99, box=(100, 110, 300, 150)),
        ]
        self.assertEqual(select_date(lines).final_date, "2026-05-21")

    def test_manufacturing_only_is_none(self):
        selection = select_date([line("2025.06.19 제조")], final=True)
        self.assertIsNone(selection.final_date)
        self.assertEqual(selection.reason, "negative-context")

    def test_single_date_with_mixed_interval_context_requests_recovery(self):
        selection = select_date(
            [
                line("2025.06.19", box=(100, 0, 300, 40)),
                line("제조", box=(0, 0, 80, 40)),
                line("소비기한", box=(320, 0, 430, 40)),
            ]
        )
        self.assertEqual(selection.final_date, "2025-06-19")
        self.assertFalse(selection.confident)

    def test_strong_expiry_date_is_not_delayed_by_distant_manufacturing_text(self):
        selection = select_date(
            [
                line("소비기한 2026.06.19까지", box=(100, 0, 430, 40)),
                line("제조", box=(0, 0, 80, 40)),
            ]
        )
        self.assertEqual(selection.final_date, "2026-06-19")
        self.assertTrue(selection.confident)

    def test_nearby_spatial_context_is_used(self):
        lines = [
            line("소비기한", box=(0, 0, 100, 40)),
            line("2027.06.26", box=(120, 0, 310, 40)),
            line("까지", box=(325, 0, 380, 40)),
        ]
        selection = select_date(lines)
        self.assertEqual(selection.final_date, "2027-06-26")
        self.assertTrue(selection.confident)

    def test_split_date_boxes_are_merged(self):
        lines = [
            line("2025.", box=(0, 0, 90, 40)),
            line("12.11", box=(100, 0, 190, 40)),
            line("까지", box=(200, 0, 250, 40)),
        ]
        self.assertEqual(select_date(lines).final_date, "2025-12-11")

    def test_calendar_output_fields_are_consistent(self):
        self.assertEqual(
            submission_fields("2026-05-09"),
            {"year": "2026", "month": "05", "day": "09", "final_date": "2026-05-09"},
        )
        self.assertEqual(set(submission_fields(None).values()), {"NONE"})


if __name__ == "__main__":
    unittest.main()
