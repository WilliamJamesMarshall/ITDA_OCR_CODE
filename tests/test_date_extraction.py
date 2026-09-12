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
        for raw in ("2026.13.02", "2025.02.29", "2100.09.20", "12.04", "8801234567890"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_dates(raw), [])

    def test_historical_and_explicit_order_formats(self):
        for raw, expected in {
            "2020.09.20": "2020-09-20",
            "YY.MM.DD 19.09.03": "2019-09-03",
            "08/18/21": "2021-08-18",
            "MM/DD/YY 07/12/22": "2022-07-12",
            "월/일/년 07/12/22": "2022-07-12",
            "DD/MM/YYYY 07/12/2022": "2022-12-07",
            "2021 AUG 18": "2021-08-18",
        }.items():
            with self.subTest(raw=raw):
                self.assertEqual({item.value.isoformat() for item in parse_dates(raw)}, {expected})

    def test_invalid_explicit_order_does_not_fall_back(self):
        self.assertEqual(parse_dates("MM/DD/YY 18/08/21"), [])

    def test_order_parser_does_not_borrow_clock_or_date_suffix_digits(self):
        self.assertEqual(parse_dates("4 14:06"), [])
        self.assertEqual({p.value.isoformat() for p in parse_dates("2025.09.16/20:52")}, {"2025-09-16"})

    def test_clock_tail_does_not_become_a_two_digit_year_date(self):
        for raw in (".31 01:31", "03.31 01:31", "EXP 11.28 22:15", "03.31 01:3"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_dates(raw), [])
        self.assertEqual({p.value.isoformat() for p in parse_dates("2026.03.31 01:31")}, {"2026-03-31"})
        selected = select_date([line("유통기한 03.31 01:31")], final=True)
        self.assertEqual(selected.final_date, "NONE-03-31")


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
            line("제조 YY.MM.DD 25.09.05", score=0.65, box=(100, 0, 300, 40)),
            line("YY.MM.DD 26.03.04", score=0.65, box=(100, 55, 300, 95)),
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
        for value in (None, "NONE", "NONE-NONE-NONE"):
            self.assertEqual(submission_fields(value), {
                "year": "NONE", "month": "NONE", "day": "NONE", "final_date": "NONE"})

    def test_partial_dates_and_output_contract(self):
        for raw, expected in {
            "소비기한 02월 14일": "NONE-02-14",
            "EXP 02.29": "NONE-02-29",
            "소비기한 2021년 05월": "2021-05-NONE",
            "EXP MAY 2021": "2021-05-NONE",
        }.items():
            with self.subTest(raw=raw):
                interim = select_date([line(raw)])
                self.assertEqual(interim.final_date, expected)
                self.assertTrue(interim.is_partial)
                self.assertFalse(interim.confident)
                final = select_date([line(raw)], final=True)
                self.assertEqual(final.final_date, expected)
                fields = submission_fields(expected)
                self.assertEqual('-'.join(fields[k] for k in ('year','month','day')), expected)

    def test_partial_dates_do_not_salvage_invalid_full_dates_or_measurements(self):
        for raw in ("EXP 2021.02.30", "EXP 2100.05.29", "EXP 2021년 05월 32일", "EXP 02.30", "보관 02.14℃", "제조 05.12", "LOT NO 05.12"):
            with self.subTest(raw=raw):
                self.assertIsNone(select_date([line(raw)], final=True).final_date)

    def test_partial_output_rejects_malformed_values(self):
        for value in ("NONE-02-30", "2021-13-NONE", "2100-01-NONE", "NONE-NONE-01", "NONE-2-14"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                submission_fields(value)

    def test_different_coordinate_frames_cannot_merge_dates(self):
        values = [line("2021.", box=(0,0,90,40)), line("05.29", box=(100,0,190,40), variant="roi-1")]
        self.assertNotEqual(select_date(values, final=True).final_date, "2021-05-29")

    def test_distant_or_different_frame_context_does_not_change_selection(self):
        for text in ("제조", "소비기한"):
            for other in (line(text, box=(10000,10000,10100,10040)), line(text, variant="roi-1")):
                base = select_date([line("2021.05.29")])
                selected = select_date([line("2021.05.29"), other])
                self.assertEqual((selected.final_date, selected.score, selected.confident), (base.final_date, base.score, base.confident))

    def test_historical_local_low_confidence_interval(self):
        selected = select_date([line("제조 YY.MM.DD 20.09.05", .65, (100,0,300,40)), line("YY.MM.DD 21.03.04", .65, (100,55,300,95))], final=True)
        self.assertEqual(selected.final_date, "2021-03-04")

    def test_unrelated_dates_do_not_form_a_latest_date_interval(self):
        first = line("2021.01.02", .99, (0,0,300,40))
        for last in (line("2021.07.05", .95, (10000,10000,10300,10040)),
                     line("2021.07.05", .95, (0,55,300,95), variant="roi-1")):
            with self.subTest(last=last):
                self.assertEqual(select_date([first,last],final=True).final_date,"2021-01-02")

    def test_split_interval_roles_survive_overlapping_ocr_boxes(self):
        selected = select_date([
            line("2025.10.01/12.47", .9881, (342,888,926,997)),
            line("부터", .9968, (1030,886,1176,985)),
            line("2026.03.31/A", .9964, (343,976,808,1088)),
            line("까지", .9974, (1026,978,1173,1075)),
        ], final=True)
        self.assertEqual(selected.final_date, "2026-03-31")

    def test_interval_comparison_uses_scores_with_agreement_bonus(self):
        values = []
        for variant in ('original', 'roi-1', 'roi-2', 'clahe'):
            values.extend([line('YY.MM.DD 25.08.25', .999, (0,0,300,40), variant=variant),
                           line('YY.MM.DD 26.02.24', .998, (0,55,300,95), variant=variant)])
        self.assertEqual(select_date(values, final=True).final_date, '2026-02-24')

    def test_closer_until_role_beats_an_overlapping_merged_window(self):
        values = []
        for variant in ('original', 'roi-1', 'roi-2', 'clahe'):
            values.extend([line('YY.MM.DD 25.09.03', .999, (0,0,670,207), variant=variant),
                           line('YY.MM.DD 26.03.02', .998, (0,171,670,380), variant=variant),
                           line('까지', .90, (700,167,940,370), variant=variant)])
        self.assertEqual(select_date(values, final=True).final_date, '2026-03-02')

    def test_indirect_manufacturing_context_does_not_stop_recovery(self):
        selected = select_date([line('부터', .99, (1635,258,1806,511)),
                                line('2027W3.02', .8388, (1096,780,1874,1069))])
        self.assertIsNone(selected.final_date)
        self.assertFalse(selected.confident)

    def test_overlapping_parses_do_not_form_a_date_interval(self):
        for raw,expected in [('EXP 22/03/2021', '2021-03-22'),
                             ('유통기한 2022.04.23.10:17까지', '2022-04-23')]:
            with self.subTest(raw=raw):
                self.assertEqual(select_date([line(raw)], final=True).final_date, expected)


if __name__ == "__main__":
    unittest.main()
