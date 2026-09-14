"""Exercise the current notebook entry policy, alongside retained legacy tests."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from src.date_extraction import OCRLine, DateSelection
from src.pipeline import PipelineConfig, run_pipeline


class Backend:
    def recognize(self, image, **kwargs):
        return [OCRLine('EXP 2026.05.29', .99, (0, 0, 200, 30))]


@patch.dict(os.environ, ITDA_EXECUTION_POLICY='base-first-v2', ITDA_BUDGET_SECONDS='1570')
class PreflightFailureContractTests(unittest.TestCase):
    def test_corrupt_input_keeps_denominator_and_partial_but_no_final_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'broken.jpg').write_bytes(b'not an image')
            Image.new('RGB', (250, 50)).save(root/'valid.jpg')
            output = root/'out.csv'
            result = run_pipeline(root, output, backend=Backend(), config=PipelineConfig(progress_every=0))
            self.assertEqual((result['images'], result['attempted_images'], result['processed_images']), (2, 2, 1))
            self.assertEqual(result['status'], 'failed')
            self.assertFalse(result['output_complete'])
            self.assertFalse(output.exists())
            self.assertEqual([e['image_id'] for e in result['failures']], ['broken'])
            with Path(result['partial_path']).open() as stream:
                rows = {r['image_id']: r for r in csv.DictReader(stream)}
            self.assertEqual(rows['broken']['final_date'], 'NONE')
            self.assertEqual(rows['valid']['final_date'], '2026-05-29')

    def test_invalid_base_date_is_recorded_as_failure_and_does_not_abort_next_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('invalid', 'valid'):
                Image.new('RGB', (250, 50)).save(root/(name+'.jpg'))
            invalid = DateSelection('NONE-02-30', 1., 1., True, 'partial-date', ())
            valid = DateSelection('2026-05-29', 1., 1., True, 'selected', ())
            with patch('src.budget_pipeline.output_selection', side_effect=[invalid, valid]):
                result = run_pipeline(root, root/'out.csv', backend=Backend(),
                                      config=PipelineConfig(progress_every=0))
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['attempted_images'], 2)
            self.assertEqual(result['processed_images'], 1)
            self.assertEqual([e['image_id'] for e in result['failures']], ['invalid'])
            with Path(result['partial_path']).open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r['final_date'] for r in rows], ['NONE', '2026-05-29'])

    def test_recovery_error_keeps_base_observations_and_error_journal(self):
        class WeakBackend:
            def recognize(self, image, **kwargs):
                return [OCRLine('1234..xxxx', .9, (0, 0, 200, 30))]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new('RGB', (250, 50)).save(root/'sample.jpg')
            output = root/'out.csv'
            with patch('src.budget_pipeline.run_stage', side_effect=RuntimeError('recognition failed')):
                result = run_pipeline(root, output, backend=WeakBackend(),
                                      config=PipelineConfig(progress_every=0, collect_trace=True))
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(result['failures'])
            self.assertTrue(all('recognition failed' in e['error'] for e in result['failures']))
            trace = [json.loads(s) for s in Path(str(output)+'.trace.jsonl').read_text(encoding='utf-8').splitlines()]
            passes = [e for e in trace if e['kind'] == 'ocr_pass']
            self.assertEqual(passes[0]['observations'][0]['text'], '1234..xxxx')
            journal = [json.loads(s) for s in Path(result['progress_path']).read_text(encoding='utf-8').splitlines()]
            self.assertTrue(any(e['kind'] == 'recovery_error' for e in journal))
            self.assertEqual(journal[-1]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
