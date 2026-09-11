import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.date_extraction import OCRLine
from src.pipeline import PipelineConfig, _date_fragment_lines, predict_image


def line(text, score=.99, box=(100, 100, 300, 140)):
    return OCRLine(text, score, box)


class ROIRecoveryTest(unittest.TestCase):
    def test_damaged_date_precedes_nutrition_and_phone(self):
        damaged = line("a0E1.0R0EH", .65)
        result = _date_fragment_lines([
            line("레드자몽농축액3%(자몽과즙으로17.4%,"),
            line("고객상담실:080-024-2311"), damaged,
        ])
        self.assertEqual(result[0], damaged)
        self.assertEqual(damaged.text, "a0E1.0R0EH")  # Crop hint is not a digit repair.

    def test_full_date_precedes_weaker_fragment(self):
        full = line("2026.07.15.B F2", .75)
        self.assertEqual(_date_fragment_lines([line("3/0/정/점"), full])[0], full)

    def test_missing_digits_can_still_anchor_recovery(self):
        damaged = line("2..1 F.9", .56)
        self.assertIn(damaged, _date_fragment_lines([
            line("1일 영양성분 기준치는 2.000kcal"), line("2:465", .68), damaged,
        ]))

    def test_labels_alone_do_not_spend_an_additional_ocr_call(self):
        phone = line("전화:080-123-4567")
        self.assertEqual(_date_fragment_lines([phone, line("Best before:")]), [phone])
        self.assertEqual(_date_fragment_lines([line("소비기한")]), [])

    def test_instructions_are_not_standalone_date_labels(self):
        for text in ("소비기한 상단표시일까지", "유통기한을 꼭 확인후 사용하십시오", "BEST BEFORE SEE BOTTOM"):
            self.assertEqual(_date_fragment_lines([line(text)]), [])
        self.assertEqual(_date_fragment_lines([line("EXP", .4)]), [])

    def test_new_anchors_do_not_include_short_nutrition_or_barcode(self):
        for text in ("0.5g", "0.5mg", "1.5", "180497311306198", "2/2", "지방0.18"):
            self.assertEqual(_date_fragment_lines([line(text)]), [])

    def test_valid_date_precedes_clock_and_address(self):
        date = line("2025.09.30", .8)
        self.assertEqual(_date_fragment_lines([line("16:20"), line("로1길48-60"), date])[0], date)

    def test_legacy_fallback_is_retained_when_no_better_hint(self):
        legacy = [line("080-024-2311"), line("1일 기준 2.000kcal", .9)]
        self.assertEqual(_date_fragment_lines(legacy), legacy)

    def test_cap_stability_and_no_input_mutation(self):
        lines = [line("2021.02.03", .8), line("2021.04.05", .8), line("2021.06.07", .8)]
        original = list(lines)
        self.assertEqual(_date_fragment_lines(lines), lines[:2])
        self.assertEqual(lines, original)

    def test_clear_order_ambiguity_still_uses_one_pass(self):
        class Backend:
            def __init__(self):
                self.calls = []

            def recognize(self, image, *, detector, variant):
                self.calls.append((detector, variant))
                return [line("EXP 20-06-21")]

        backend = Backend()
        with patch("src.pipeline._load_bgr", return_value=np.zeros((500, 500, 3), dtype=np.uint8)):
            prediction = predict_image(Path("unrelated.jpg"), backend, PipelineConfig())
        self.assertIsNone(prediction.final_date)
        self.assertEqual(prediction.selection.policy_details['status'], 'REVIEW_REQUIRED')
        self.assertEqual(backend.calls, [("mobile", "original")])

    def test_pipeline_crops_damaged_date_before_readable_nutrition(self):
        damaged = line("a0E1.0R0EH", .65)

        class Backend:
            def recognize(self, image, *, detector, variant):
                if variant == "original":
                    return [line("자몽과즙17.4%"), line("전화:080-123-4567"), damaged]
                return [OCRLine("EXP 2021.09.02", .99, (0, 0, 300, 40), detector, variant)]

        pixels = np.zeros((500, 500, 3), dtype=np.uint8)
        with patch("src.pipeline._load_bgr", return_value=pixels), patch(
            "src.pipeline._crop_fragment", return_value=pixels,
        ) as crop:
            prediction = predict_image(Path("unrelated.jpg"), Backend(), PipelineConfig())
        self.assertEqual(crop.call_args.args[1].text, damaged.text)
        self.assertEqual(crop.call_args.args[1].box, damaged.box)
        self.assertEqual(prediction.final_date, "2021-09-02")
        self.assertEqual(prediction.passes, ("mobile:original", "mobile:roi-1"))


if __name__ == "__main__":
    unittest.main()
