import json
import io
from contextlib import redirect_stdout
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts.validation_runner import _supervise, run_timed_pipeline
from scripts.evaluate_pipeline import assess_targets, main


def _record():
    return {'kind': 'image', 'row': {'image_id': '000001', 'year': '2026', 'month': '01',
                                    'day': '02', 'final_date': '2026-01-02'},
            'seconds': .1, 'error': None, 'passes': ['mobile:original']}


def _hung_worker(journal):
    Path(journal).write_text(json.dumps(_record()) + '\n', encoding='utf-8')
    time.sleep(60)


def _fast_worker(journal):
    Path(journal).write_text(json.dumps(_record()) + '\n' + json.dumps(
        {'kind': 'completed', 'runtime': {'images': 1, 'failures': []}}) + '\n', encoding='utf-8')


def _crashed_worker(journal):
    Path(journal).write_text(json.dumps(_record()) + '\n{"kind":', encoding='utf-8')
    os._exit(7)


def accuracy(n=500, correct=475):
    return {'evaluated_labels': n, 'exact_matches': correct, 'exact_match_rate': correct / n,
            'accuracy_target_met': correct / n >= .95, 'labels_without_predictions': [], 'skipped': {},
            'submission_format': {'all_rows_compliant': True}}


class ValidationTimeoutTest(unittest.TestCase):
    def test_soft_target_miss_is_not_hard_timeout(self):
        for elapsed in (1500.01, 2000, 2400):
            runtime = {'images': 500, 'completed_images': 500, 'status': 'completed',
                       'total_elapsed_seconds': elapsed, 'failures': []}
            result = assess_targets(runtime, accuracy())
            self.assertFalse(result['local_500_joint_target_met'])
            self.assertTrue(result['actual_500_timeout_met'])
            self.assertEqual(result['time_assessment'], 'internal_target_missed_within_hard_limit')
            self.assertEqual(result['actual_seconds_per_completed_image'], elapsed / 500)
            self.assertAlmostEqual(result['seconds_per_image_over_target'], elapsed / 500 - 3)

    def test_partial_timeout_never_divides_by_unprocessed_images(self):
        runtime = {'images': 500, 'completed_images': 300, 'status': 'timeout',
                   'total_elapsed_seconds': 2400.1, 'failures': []}
        result = assess_targets(runtime, accuracy())
        self.assertAlmostEqual(result['actual_seconds_per_completed_image'], 2400.1 / 300)
        self.assertIsNone(result['total_seconds_per_input_image'])
        self.assertIsNone(result['seconds_500_equivalent'])
        self.assertFalse(result['local_relative_joint_target_met'])
        self.assertFalse(result['actual_500_timeout_met'])
        self.assertEqual(result['time_assessment'], 'timeout')
        self.assertEqual(result['unprocessed_images'], 200)

    def test_timeout_before_first_image_has_no_fabricated_rate(self):
        runtime = {'images': 500, 'completed_images': 0, 'status': 'timeout',
                   'total_elapsed_seconds': 2400.1, 'failures': []}
        result = assess_targets(runtime, accuracy())
        self.assertIsNone(result['actual_seconds_per_completed_image'])
        self.assertFalse(result['relative_speed_target_met'])

    def test_failed_worker_cannot_pass_even_with_all_rows(self):
        runtime = {'images': 500, 'completed_images': 500, 'status': 'failed',
                   'total_elapsed_seconds': 1000, 'failures': []}
        self.assertFalse(assess_targets(runtime, accuracy())['local_relative_joint_target_met'])

    def test_hung_process_is_stopped_and_completed_checkpoint_survives(self):
        result = _supervise(_hung_worker, (), hard_timeout_seconds=3)
        self.assertEqual(result['status'], 'timeout')
        self.assertGreaterEqual(result['elapsed_seconds'], 3)
        self.assertLess(result['elapsed_seconds'], 6)
        self.assertIsNotNone(result['exit_code'])
        self.assertEqual([e['row']['image_id'] for e in result['events']], ['000001'])

    def test_completed_process_is_not_a_timeout(self):
        result = _supervise(_fast_worker, (), hard_timeout_seconds=10)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['exit_code'], 0)

    def test_process_crash_preserves_only_complete_journal_records(self):
        result = _supervise(_crashed_worker, (), hard_timeout_seconds=10)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(len(result['events']), 1)

    def test_timeout_replaces_stale_output_without_filling_missing_rows(self):
        result = {'status': 'timeout', 'elapsed_seconds': 2400.1, 'exit_code': -1,
                  'hard_timeout_seconds': 2400, 'events': [_record()]}
        with tempfile.TemporaryDirectory() as directory, patch(
            'scripts.validation_runner._supervise', return_value=result,
        ):
            output = Path(directory) / 'predictions.csv'
            output.write_text('stale output', encoding='utf-8')
            runtime = run_timed_pipeline(directory, output, config=None,
                                         expected_images=[Path('000001.jpg'), Path('000002.jpg')])
            self.assertEqual(runtime['completed_images'], 1)
            self.assertEqual(runtime['unprocessed_images'], 1)
            data = output.read_text(encoding='utf-8')
            self.assertIn('000001', data)
            self.assertNotIn('000002', data)
            self.assertNotIn('stale', data)

    def test_timeout_preserves_completed_missing_result_and_failure_reason(self):
        record = _record()
        record['row'].update(year='NONE', month='NONE', day='NONE', final_date='NONE')
        record['error'] = 'OCR error'
        result = {'status': 'timeout', 'elapsed_seconds': 2400.1, 'exit_code': -1,
                  'hard_timeout_seconds': 2400, 'events': [record]}
        with tempfile.TemporaryDirectory() as directory, patch(
            'scripts.validation_runner._supervise', return_value=result,
        ):
            output = Path(directory) / 'predictions.csv'
            runtime = run_timed_pipeline(directory, output, config=None,
                                         expected_images=[Path('000001.jpg'), Path('000002.jpg')])
            self.assertIn('NONE,NONE,NONE,NONE', output.read_text(encoding='utf-8'))
            self.assertNotIn('000002', output.read_text(encoding='utf-8'))
            self.assertEqual(runtime['failures'], [{'image_id': '000001', 'error': 'OCR error'}])

    def test_cli_reports_timeout_or_failure_before_nonzero_exit(self):
        for status, exit_code in [('timeout', 124), ('failed', 1)]:
            runtime = {'images': 1, 'completed_images': 0, 'status': status,
                       'total_elapsed_seconds': 2400.1, 'failures': []}
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / 'report.json'
                argv = ['evaluate_pipeline', directory, 'labels.csv', 'out.csv', '--report-json', str(report)]
                with patch('sys.argv', argv), patch('scripts.evaluate_pipeline.read_labels', return_value={
                    '000001': {'정답 날짜': 'NONE', '라벨 상태': 'manual'},
                }), patch('scripts.evaluate_pipeline.discover_images', return_value=[Path('000001.jpg')]), patch(
                    'scripts.evaluate_pipeline.run_timed_pipeline', return_value=runtime,
                ), patch('scripts.evaluate_pipeline.read_predictions', return_value=[]), redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main()
                self.assertEqual(error.exception.code, exit_code)
                self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['runtime']['status'], status)

    def test_cli_soft_goal_miss_completes_normally(self):
        runtime = {'images': 500, 'completed_images': 500, 'status': 'completed',
                   'total_elapsed_seconds': 2000, 'failures': []}
        with patch('sys.argv', ['evaluate_pipeline', '.', 'labels.csv', 'out.csv']), patch(
            'scripts.evaluate_pipeline.read_labels', return_value={},
        ), patch('scripts.evaluate_pipeline.discover_images', return_value=[Path(f'{i:06}.jpg') for i in range(500)]), patch(
            'scripts.evaluate_pipeline.run_timed_pipeline', return_value=runtime,
        ), patch('scripts.evaluate_pipeline.read_predictions', return_value=[]), patch(
            'scripts.evaluate_pipeline.score_predictions', return_value=accuracy(),
        ), redirect_stdout(io.StringIO()):
            main()  # No timeout/nonzero exit at the 1,500-second soft target.


if __name__ == '__main__':
    unittest.main()
