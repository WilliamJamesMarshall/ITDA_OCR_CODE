"""Preparation contract tests. Written only; execute in the separately authorized session."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.grouped_plan import GROUPS, cpu_set, time_target_met, HARD_TIMEOUT_SECONDS
from scripts.grouped_rounds import notebook_budget_seconds, inherited_execution
from scripts.grouped_training import validate_samples
from scripts.prepare_sequential_rounds import write, csv_write


class PreparationPolicyTests(unittest.TestCase):
    def test_six_round_cpu_policy(self):
        self.assertEqual(GROUPS, ((1,), (2, 3), (4, 5), (6,)))
        for n in (2, 4): self.assertEqual(cpu_set(n), [0, 1, 4, 5])
        for n in (3, 5): self.assertEqual(cpu_set(n), [2, 3, 6, 7])
        for n in range(1, 7): self.assertEqual(cpu_set(n, integration=True), [0, 1, 2, 3])
        for n in (1, 6): self.assertEqual(cpu_set(n), [0, 1, 2, 3])
        for n in (7, 8):
            with self.assertRaises(ValueError): cpu_set(n)

    def test_internal_budget_is_not_target_or_watchdog(self):
        self.assertEqual(HARD_TIMEOUT_SECONDS, 2400)
        for count, budget in ((216, 661.2), (394, 1230.8), (500, 1570.0)):
            self.assertAlmostEqual(notebook_budget_seconds(count), budget)
        self.assertEqual(notebook_budget_seconds(1, qualification=True), 90)
        runtime = dict(status='completed', images=500, failures=[], total_elapsed_seconds=1601)
        self.assertFalse(time_target_met(runtime, 500))
        self.assertEqual(runtime['status'], 'completed')

    def test_draft_crop_cannot_be_admitted_as_none_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            csv_write(root / 'test_to_original_mapping.csv', [], ['augmented', 'test_sha256'])
            csv_write(root / 'excluded_derivatives.csv', [], ['test_sha256'])
            with patch('scripts.grouped_training.ROOT', root):
                with self.assertRaisesRegex(ValueError, 'draft'):
                    validate_samples(root, {}, [dict(review_status='pending')])

    def test_nested_legacy_lock_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'plan.json', dict(previous_workspace=str(root / 'old')))
            lock = root / 'old/paper/full-new/execution.lock'
            write(lock, dict(owner='unknown'))
            self.assertEqual(len(inherited_execution(root)), 1)
            self.assertTrue(lock.exists())


if __name__ == '__main__': unittest.main()
