import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.date_extraction import OCRLine, ProductDateRule, parse_dates, select_date
from src.pipeline import PipelineConfig, predict_image


def line(text, score=.99, box=(0, 0, 300, 40), variant="original"):
    return OCRLine(text, score, box, "test", variant)


class OrderPolicyTest(unittest.TestCase):
    def test_all_numeric_orders_generated_before_selection(self):
        self.assertEqual({p.value.isoformat() for p in parse_dates("12/01/24")},
                         {"2012-01-24", "2024-01-12", "2024-12-01"})
        self.assertEqual({p.value.isoformat() for p in parse_dates("20-06-21")},
                         {"2020-06-21", "2021-06-20"})

    def test_dmy_fallback_covers_separators_spaces_and_compact(self):
        for text, expected in [("20-06-21", "2021-06-20"), ("26.02.21", "2021-02-26"),
                               ("12/01/24", "2024-01-12"), ("20 06 21", "2021-06-20"),
                               ("200621", "2021-06-20"), ("03-06-2028", "2028-06-03")]:
            with self.subTest(text=text):
                selected = select_date([line(text)])
                self.assertEqual(selected.final_date, expected)
                self.assertTrue(selected.confident)
                self.assertEqual(selected.reason, "fallback_dmy")

    def test_literal_units_and_printed_orders_override_fallback(self):
        for text, expected in [("26년 2월 21일", "2026-02-21"),
                               ("년월일순 26.02.21", "2026-02-21"),
                               ("00일00월00년 26.02.21", "2021-02-26"),
                               ("월/일/년 03-06-2028", "2028-03-06"),
                               ("DD-MM-YY 20-06-21", "2021-06-20")]:
            with self.subTest(text=text):
                selected = select_date([line(text)])
                self.assertEqual(selected.final_date, expected)
                self.assertNotEqual(selected.reason, "fallback_dmy")

    def test_unique_dates_are_never_overwritten_by_dmy(self):
        for raw, expected in [("08/18/21", "2021-08-18"), ("2028.03.06", "2028-03-06"),
                              ("23/02/2024", "2024-02-23"), ("00.01.25", "2000-01-25")]:
            with self.subTest(raw=raw):
                self.assertEqual(select_date([line(raw)]).final_date, expected)
                self.assertTrue(select_date([line(raw)]).confident)

    def test_date_prefix_punctuation_is_not_a_numeric_suffix(self):
        for text, expected in [("EXP.2023/10/21", "2023-10-21"),
                               ("BBE:13.04.2022", "2022-04-13"),
                               ("유통기한:2022.09.13", "2022-09-13")]:
            self.assertEqual(select_date([line(text)]).final_date, expected)

    def test_full_year_date_keeps_printed_clock_and_lot_suffixes_separate(self):
        for raw, expected in [("2020.11.1614:108", "2020-11-16"),
                              ("2025.12.1207", "2025-12-12"),
                              ("2026.04.07721", "2026-04-07"),
                              ("F2-2026.05.14까지", "2026-05-14"),
                              ("2026.08.13714:16", "2026-08-13")]:
            with self.subTest(raw=raw):
                self.assertEqual(select_date([line(raw)], final=True).final_date, expected)

    def test_short_dates_cannot_borrow_lot_digits_or_broken_year_tail(self):
        self.assertEqual(parse_dates("L.0200 1 2"), [])
        self.assertEqual(parse_dates("2-.07-01 1"), [])
        self.assertEqual(select_date([line("F1 01.25 6")], final=True).final_date, "NONE-01-25")

    def test_attached_date_labels_and_joined_end_year(self):
        for raw, expected in [("EXP08/18/21", "2021-08-18"),
                              ("다25.10.10까지A신재명", "2010-10-25"),
                              ("EXP26.02.26", "2026-02-26"),
                              ("18 072021", "2021-07-18")]:
            with self.subTest(raw=raw):
                self.assertEqual(select_date([line(raw)], final=True).final_date, expected)

    def test_positive_context_does_not_turn_uncertain_digits_into_fast_fallback(self):
        self.assertFalse(select_date([line("EXP 20-06-21", score=.55)]).confident)

    def test_nearby_legend_is_scoped_to_its_coordinate_frame(self):
        target = line("12/01/24", box=(0, 50, 300, 90))
        self.assertEqual(select_date([line("MM/DD/YY"), target]).final_date, "2024-12-01")
        for hint in [line("MM/DD/YY", variant="roi-1"), line("MM/DD/YY", box=(5000,5000,5300,5040))]:
            self.assertEqual(select_date([hint, target]).final_date, "2024-01-12")

    def test_inline_legends_do_not_leak_to_another_date(self):
        parsed = parse_dates("MM/DD/YY 03/06/28; DD/MM/YY 20/06/21")
        self.assertEqual({p.value.isoformat() for p in parsed}, {"2028-03-06", "2021-06-20"})

    def test_conflicting_or_invalid_explicit_order_does_not_default(self):
        for raw in ("MM/DD/YY 18/08/21", "YY/MM/DD 03/06/2028", "EXP 2021.02.30"):
            with self.subTest(raw=raw):
                self.assertIsNone(select_date([line(raw)], final=True).final_date)

    def test_corresponding_fully_written_date(self):
        selected = select_date([line("10/09/21"), line("유통기한 2021년10월09일", box=(0,60,300,100))])
        self.assertEqual(selected.final_date, "2021-10-09")
        self.assertNotIn("2021-09-10", {c.iso for c in selected.candidates})

    def test_verified_local_package_rule_and_explicit_priority(self):
        rule = ProductDateRule("test-package-v2", ("TEST OLIVES", "500G VERSION2"), "mdy", "test fixture only")
        package = line("TEST OLIVES 500G VERSION2", box=(0,100,300,140))
        self.assertEqual(select_date([line("03-06-2028"), package], product_rules=(rule,)).final_date, "2028-03-06")
        self.assertEqual(select_date([line("DD/MM/YYYY 03-06-2028"), package], product_rules=(rule,)).final_date, "2028-06-03")
        self.assertEqual(select_date([line("03-06-2028"), line("USA")], product_rules=(rule,)).final_date, "2028-06-03")
        distant_package = line("TEST OLIVES 500G VERSION2", box=(5000,5000,5300,5040))
        self.assertEqual(select_date([line("03-06-2028"), distant_package], product_rules=(rule,)).final_date, "2028-06-03")

    def test_manufacturing_and_partial_are_not_forced_to_full_dmy(self):
        self.assertIsNone(select_date([line("MFG 20-06-21")], final=True).final_date)
        self.assertEqual(select_date([line("EXP 03.31")], final=True).final_date, "NONE-03-31")

    def test_low_confidence_digits_still_allow_recovery(self):
        selected = select_date([line("20-06-21", score=.55)])
        self.assertFalse(selected.confident)

    def test_korean_legend_variants_and_partial_doubled_placeholders(self):
        for legend in ("연.월.일", "년년.월월.일일", "기한(년년.월월..", "기한(년년월월"):
            selected = select_date([line(legend), line("22.04.30", box=(0,60,300,100))])
            self.assertEqual(selected.final_date, "2022-04-30")
            self.assertEqual(selected.candidates[0].order_reason, "explicit_order")
        self.assertEqual(select_date([line("년월 생산"), line("22.04.30", box=(0,200,300,240))]).final_date,
                         "2030-04-22")

    def test_exp_attached_month_name_and_targeted_digit_repair(self):
        for raw in ("EXP04SEP22", "EXPO4SEP22"):
            self.assertEqual(select_date([line(raw)], final=True).final_date, "2022-09-04")
        self.assertTrue(parse_dates("EXPO4SEP22")[0].repaired)
        self.assertEqual(parse_dates("LOT04SEP22"), [])
        selected = select_date([line("220904"), line("EXPO4SEP22", box=(0,60,300,100))])
        self.assertEqual(selected.final_date, "2022-09-04")
        self.assertNotIn("2004-09-22", {c.iso for c in selected.candidates})

    def test_explicit_reference_may_link_only_one_distant_date(self):
        hint = line("소비기한 제품에 별도 표기일까지(읽는법: 년,월,일 순)")
        target = line("26.01.31", box=(0,350,300,390))
        self.assertEqual(select_date([hint, target]).final_date, "2026-01-31")
        for rival in (line("20.06.21", box=(800,350,1100,390)),
                      line("EXP 2028.12.31", box=(800,350,1100,390))):
            candidates = select_date([hint, target, rival], final=True).candidates
            self.assertIn("2031-01-26", {c.iso for c in candidates})
        other_frame = line(hint.text, variant="roi-1")
        self.assertEqual(select_date([other_frame, target]).final_date, "2031-01-26")

    def test_labelled_same_format_pair_removes_impossible_chronology(self):
        start = line("25.09.15부터")
        end = line("26.03.14까지", box=(0,60,300,100))
        selected = select_date([start, end])
        self.assertEqual(selected.final_date, "2026-03-14")
        self.assertEqual(selected.candidates[0].order_reason, "labelled_date_pair")
        self.assertTrue(selected.confident)

    def test_pair_requires_both_roles_same_frame_format_and_clear_digits(self):
        cases = [
            [line("25.09.15"), line("26.03.14", box=(0,60,300,100))],
            [line("25.09.15부터"), line("26.03.14까지", box=(0,60,300,100), variant="roi-1")],
            [line("25.09.15부터"), line("26-03-14까지", box=(0,60,300,100))],
            [line("25.09.15부터", score=.60), line("26.03.14까지", box=(0,60,300,100))],
            [line("25.09.15부터"), line("26.03.14까지", box=(0,1500,300,1540))],
            [line("25.01.24부터"), line("26.02.25까지", box=(0,60,300,100))],
        ]
        for lines in cases:
            with self.subTest(text=[l.text for l in lines]):
                self.assertNotIn("labelled_date_pair", {c.order_reason for c in select_date(lines, final=True).candidates})

    def test_partial_date_does_not_borrow_clock_or_stray_lot_digit(self):
        for raw in ("EXP 03.31 01:31 12B", "1 03.31 01:31 12B"):
            self.assertEqual(select_date([line(raw)], final=True).final_date, "NONE-03-31")
        self.assertEqual(select_date([line("YY.MM.DD 20.03.1119:28")]).final_date, "2020-03-11")

    def test_perspective_skew_matches_role_block_one_to_one(self):
        lines = [line("20.08.11", box=(0,0,160,60)),
                 line("21.08.10", box=(0,62,160,121)),
                 line("부터", box=(245,44,294,82)),
                 line("까지", box=(241,78,297,121))]
        selected = select_date(lines)
        self.assertEqual(selected.final_date, "2021-08-10")
        self.assertTrue(selected.order_resolved)
        self.assertTrue(selected.stop_ocr)
        # Adding a third date makes the two-row/role matching unsafe.
        crowded = select_date(lines + [line("22.08.09", box=(0,125,160,184))], final=True)
        self.assertNotIn("labelled_date_pair", {c.order_reason for c in crowded.candidates})

    def test_digit_order_and_stop_confidence_are_distinct(self):
        fallback = select_date([line("20-06-21")])
        self.assertTrue(fallback.digits_confident)
        self.assertFalse(fallback.order_resolved)
        self.assertTrue(fallback.stop_ocr)
        explicit_blurry = select_date([line("YY-MM-DD 20-06-21", score=.55)])
        self.assertFalse(explicit_blurry.digits_confident)
        self.assertTrue(explicit_blurry.order_resolved)
        self.assertFalse(explicit_blurry.stop_ocr)
        forced = select_date([line("20-06-21", score=.70)], final=True)
        self.assertFalse(forced.digits_confident)
        self.assertFalse(forced.order_resolved)
        self.assertTrue(forced.stop_ocr)

    def test_pipeline_exits_after_one_ocr_and_passes_local_rules(self):
        class Backend:
            def __init__(self):
                self.calls = 0

            def recognize(self, image, *, detector, variant):
                self.calls += 1
                return [line("12/01/24"), line("TEST OLIVES 500G VERSION2", box=(0,100,300,140))]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "any-filename.jpg"
            Image.new("RGB", (400,400)).save(path)
            for rules, expected in [((), None),
                                    ((ProductDateRule("test", ("TEST OLIVES", "500G VERSION2"), "mdy", "fixture"),), "2024-12-01")]:
                backend = Backend()
                result = predict_image(path, backend, PipelineConfig(product_date_rules=rules))
                self.assertEqual(result.final_date, expected)
                self.assertEqual(backend.calls, 1)


if __name__ == "__main__":
    unittest.main()
