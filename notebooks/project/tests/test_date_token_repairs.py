import unittest

from src.date_extraction import OCRLine, parse_dates, select_date


def line(text, box=(0, 0, 400, 40)):
    return OCRLine(text, .99, box)


class DateTokenRepairsTest(unittest.TestCase):
    def test_joined_day_month_with_explicit_year(self):
        for raw, expected in (("ENF:2106/2022", "2022-06-21"),
                              ("0907/2022", "2022-07-09"),
                              ("2212/21", "2021-12-22")):
            self.assertEqual(select_date([line(raw)], final=True).final_date, expected)
        self.assertEqual({p.order for p in parse_dates("0306/2028")}, {"dmy", "mdy"})

    def test_joined_short_dates_do_not_parse_street_or_partial_year(self):
        self.assertEqual(parse_dates("주소 교하로1312-23"), [])
        self.assertEqual(parse_dates("2001.19"), [])
        self.assertEqual(select_date([line("EXP 2021.11")], final=True).final_date, "2021-11-NONE")

    def test_overlapping_lot_fragment_cannot_consume_a_complete_date(self):
        self.assertEqual({str(p.value) for p in parse_dates("LE01 19/07/2022")}, {"2022-07-19"})
        self.assertEqual({str(p.value) for p in parse_dates("LOT 01 23/02/2024")}, {"2024-02-23"})

    def test_space_inside_month_requires_both_separators(self):
        dates = parse_dates("2021.1 1.26A")
        self.assertEqual({str(p.value) for p in dates}, {"2021-11-26"})
        self.assertTrue(all(p.repaired for p in dates))
        self.assertEqual(select_date([line("2021 1 1")], final=True).final_date, "2021-01-01")
        self.assertEqual(parse_dates("2021.1 3.26"), [])

    def test_ocr_extra_punctuation_requires_four_digit_year(self):
        self.assertEqual(select_date([line("EXP:14-11.,2022")]).final_date, "2022-11-14")
        self.assertEqual(parse_dates("2-.07-01 1"), [])

    def test_month_letter_and_year_glyph_repairs_are_recorded(self):
        for raw, expected in (("04/0ct2021", "2021-10-04"), ("2U25.06.17", "2025-06-17"),
                              ("2D21.11.06", "2021-11-06"), ("2026.06.2$", "2026-06-25")):
            parsed = parse_dates(raw)
            self.assertEqual({str(p.value) for p in parsed}, {expected})
            self.assertTrue(all(p.repaired for p in parsed))
        # Ambiguous E could mean 2 or 6; no blanket guess is implemented.
        self.assertEqual(parse_dates("17.03.E0E2"), [])

    def test_month_translation_legend_is_not_a_date(self):
        legend = "JAN-1월 FEB-2월 MAR-3월 APR-4월 MAY-5월 JUN-6월 JUL-7월 AUG-8월 SEP-9월 OCT-10월 NOV-11월 DEC-12월"
        self.assertEqual(parse_dates(legend), [])
        self.assertEqual(select_date([line(legend), line("EXP 09 OCT 21", (0,80,300,120))]).final_date, "2021-10-09")
        self.assertEqual({str(p.value) for p in parse_dates(legend + " EXP 09 OCT 21")}, {"2021-10-09"})

    def test_corrected_year_with_roles_selects_expiry_not_manufacturing(self):
        selected = select_date([line("2U25.06.17부터"), line("2026.06.16까지", (0,60,400,100))])
        self.assertEqual(selected.final_date, "2026-06-16")

    def test_month_year_only_preserves_missing_day(self):
        for raw, expected in (("EXP 10/2022 L0900337", "2022-10-NONE"),
                              ("09.2023 D0374", "2023-09-NONE"),
                              ("10-2020", "2020-10-NONE")):
            self.assertEqual(select_date([line(raw)], final=True).final_date, expected)
            self.assertFalse(select_date([line(raw)]).stop_ocr)
        for raw in ("EXP 13/2022", "MFG 10/2022", "LOT NO 10/2022", "31/02/2022", "31 / 02/2022"):
            self.assertIsNone(select_date([line(raw)], final=True).final_date)

    def test_explicit_month_year_legend_can_stop_without_inventing_day(self):
        for hint in ("제품 별도 표시일까지(읽는법: 월년순)", "Best before end: see side", "MM/YYYY"):
            selected = select_date([line(hint), line("10/2022", (0,60,400,100))])
            self.assertEqual(selected.final_date, "2022-10-NONE")
            self.assertTrue(selected.stop_ocr)
            self.assertTrue(selected.digits_confident)
            self.assertTrue(selected.order_resolved)

    def test_partial_fast_path_rejects_low_confidence_other_frames_and_competing_dates(self):
        from dataclasses import replace
        target = line("10/2022", (0,60,400,100))
        hint = line("MM/YYYY")
        for inputs in ([hint, replace(target, score=.7)],
                       [replace(hint, variant="roi-1"), target],
                       [replace(hint, box=(5000,5000,5400,5040)), target],
                       [hint, target, line("11/2022", (600,60,1000,100))],
                       [line("DD/MM/YYYY"), target],
                       [line("읽는법: 일.월년순"), target]):
            self.assertFalse(select_date(inputs).stop_ocr)

    def test_pipeline_stops_on_explicit_partial_after_one_call(self):
        import numpy as np
        from pathlib import Path
        from unittest.mock import patch
        from src.pipeline import PipelineConfig, predict_image

        class Backend:
            calls = 0

            def recognize(self, image, *, detector, variant):
                self.calls += 1
                return [line("MM/YYYY"), line("10/2022", (0,60,400,100))]

        backend = Backend()
        with patch("src.pipeline._load_bgr", return_value=np.zeros((200,400,3), dtype=np.uint8)):
            result = predict_image(Path("unseen-name.jpg"), backend, PipelineConfig())
        self.assertEqual(result.final_date, "2022-10-NONE")
        self.assertEqual(backend.calls, 1)


if __name__ == "__main__":
    unittest.main()
