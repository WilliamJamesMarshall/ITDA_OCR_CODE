import math
import unittest

from scripts.evaluate_pipeline import assess_targets


def report(n=500, elapsed=1500, correct=475):
    runtime = dict(images=n, total_elapsed_seconds=elapsed, failures=[])
    accuracy = dict(evaluated_labels=n, exact_matches=correct, exact_match_rate=correct / n,
                    accuracy_target_met=correct / n >= .95, labels_without_predictions=[], skipped={},
                    submission_format={'all_rows_compliant': True})
    return runtime, accuracy


class ValidationTargetTest(unittest.TestCase):
    def test_default_500_boundary(self):
        result = assess_targets(*report())
        self.assertEqual(result['internal_seconds_500'], 1500)
        self.assertEqual(result['target_seconds_per_image'], 3)
        self.assertEqual(result['timeout_seconds_500'], 2400)
        self.assertEqual(result['input_images_per_second'], 1 / 3)
        self.assertTrue(result['local_500_joint_target_met'])
        self.assertTrue(result['actual_500_timeout_met'])

    def test_faster_absolute_time_is_not_faster_per_image(self):
        small = assess_targets(*report(n=100, elapsed=400, correct=100))
        large = assess_targets(*report(n=500, elapsed=1500, correct=500))
        self.assertFalse(small['relative_speed_target_met'])
        self.assertTrue(large['relative_speed_target_met'])
        self.assertEqual(small['seconds_500_equivalent'], 2000)
        self.assertIsNone(small['local_500_joint_target_met'])
        self.assertIsNone(small['actual_500_timeout_met'])

    def test_smaller_run_never_claims_actual_500_pass(self):
        result = assess_targets(*report(n=100, elapsed=300, correct=95))
        self.assertTrue(result['local_relative_joint_target_met'])
        self.assertIsNone(result['local_500_joint_target_met'])
        self.assertEqual(result['relative_time_budget_seconds'], 300)

    def test_accuracy_and_speed_must_both_pass(self):
        for args in (report(correct=474), report(elapsed=1500.01)):
            self.assertFalse(assess_targets(*args)['local_500_joint_target_met'])
        self.assertTrue(assess_targets(*report(elapsed=2400))['actual_500_timeout_met'])
        self.assertFalse(assess_targets(*report(elapsed=2400.01))['actual_500_timeout_met'])

    def test_future_tighter_target_is_configurable(self):
        result = assess_targets(*report(), target_seconds_500=1200)
        self.assertEqual(result['target_seconds_per_image'], 2.4)
        self.assertFalse(result['relative_speed_target_met'])
        self.assertEqual(result['timeout_seconds_500'], 2400)

    def test_incomplete_unconfirmed_or_failed_runs_cannot_pass(self):
        for field, value in [('evaluated_labels', 499), ('labels_without_predictions', ['x']),
                             ('skipped', {'unlabelled_predictions': 1})]:
            runtime, accuracy = report()
            accuracy[field] = value
            self.assertFalse(assess_targets(runtime, accuracy)['local_relative_joint_target_met'])
        runtime, accuracy = report()
        runtime['failures'] = [{'image_id': 'x'}]
        self.assertFalse(assess_targets(runtime, accuracy)['local_relative_joint_target_met'])
        self.assertFalse(assess_targets(*report(), confirmed_labels_only=False)['local_relative_joint_target_met'])

    def test_invalid_counts_and_timing_are_rejected(self):
        for n in (0, -1, True, 1.5):
            runtime, accuracy = report()
            runtime['images'] = n
            with self.assertRaises(ValueError):
                assess_targets(runtime, accuracy)
        for elapsed in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                assess_targets(*report(elapsed=elapsed))
        for limit in (0, -1, 2400, math.inf, math.nan):
            with self.assertRaises(ValueError):
                assess_targets(*report(), target_seconds_500=limit)
