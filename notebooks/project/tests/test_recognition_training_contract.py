import unittest

from scripts.recognition_metrics import compute_metrics, normalize_text, select_checkpoint


class RecognitionMetricTests(unittest.TestCase):
    def test_normalization_is_strict(self):
        self.assertEqual(normalize_text("  exp 2027.06.26\r\n"), "EXP 2027.06.26")
        self.assertNotEqual(normalize_text("2027.06.26"), normalize_text("2027-06-26"))
        self.assertNotEqual(normalize_text("2027 06 26"), normalize_text("20270626"))

    def test_metrics_use_micro_cer(self):
        result = compute_metrics([("AB", "AB"), ("CDEF", "CXEF")])
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.exact_match_count, 1)
        self.assertEqual(result.string_exact_match_rate, 0.5)
        self.assertEqual(result.edit_error_count, 1)
        self.assertEqual(result.ground_truth_character_count, 6)
        self.assertAlmostEqual(result.micro_cer, 1 / 6)
        self.assertAlmostEqual(result.normalized_edit_similarity, (1 + 0.75) / 2)

    def test_checkpoint_order_and_patience(self):
        candidates = [
            {"epoch": 1, "string_exact_match_rate": 0.8, "micro_cer": 0.10, "normalized_edit_similarity": 0.90},
            {"epoch": 2, "string_exact_match_rate": 0.8, "micro_cer": 0.09, "normalized_edit_similarity": 0.90},
            {"epoch": 3, "string_exact_match_rate": 0.8, "micro_cer": 0.09, "normalized_edit_similarity": 0.91},
            {"epoch": 4, "string_exact_match_rate": 0.8, "micro_cer": 0.09, "normalized_edit_similarity": 0.91},
            {"epoch": 5, "string_exact_match_rate": 0.7, "micro_cer": 0.01, "normalized_edit_similarity": 0.99},
            {"epoch": 6, "string_exact_match_rate": 0.7, "micro_cer": 0.01, "normalized_edit_similarity": 0.99},
            {"epoch": 7, "string_exact_match_rate": 0.7, "micro_cer": 0.01, "normalized_edit_similarity": 0.99},
            {"epoch": 8, "string_exact_match_rate": 0.7, "micro_cer": 0.01, "normalized_edit_similarity": 0.99},
            {"epoch": 9, "string_exact_match_rate": 0.95, "micro_cer": 0.01, "normalized_edit_similarity": 0.99},
        ]
        selected = select_checkpoint(candidates, patience=5)
        self.assertEqual(selected["epoch"], 3)
        self.assertEqual(selected["selection_horizon_epoch"], 8)


if __name__ == "__main__":
    unittest.main()
