import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts.grouped_rounds import infer, validate_output, evidence
from scripts.prepare_sequential_rounds import csv_write, write
from scripts.run_round_groups import already_finished


class GroupedFailureTests(unittest.TestCase):
    def test_timeout_preserves_state_and_raises_to_controller(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as mocks:
            base = Path(folder)
            dest = base/'rounds/round_02'
            runtime = dict(status='timeout', failures=[])
            write(dest/'runtime.json',runtime)
            csv_write(base/'test_round_02.csv',[dict(image_id='a',image_path='fixture')],['image_id','image_path'])
            write(base/'approval.json',dict(synthetic_fixture=True))
            for name in ('verify','check_qualification','prior_completion','approval'):
                mocks.enter_context(patch('scripts.grouped_rounds.'+name))
            mocks.enter_context(patch('scripts.grouped_rounds.execution_release', return_value=dict(code={},model={})))
            mocks.enter_context(patch('scripts.grouped_rounds.run_notebook', return_value=(dest,runtime)))
            with self.assertRaisesRegex(RuntimeError,'Inference failed'):
                infer(base,2,base/'approval.json')
            self.assertEqual(json.loads((dest/'state.json').read_text())['status'],'inference_failed')
            self.assertTrue((dest/'runtime.json').exists())

    def test_old_scored_timeout_is_not_completed_test(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); dest = base/'rounds/round_02'
            write(dest/'runtime.json',dict(status='timeout',failures=[]))
            write(dest/'manifest.json',dict(fixture=True))
            write(dest/'state.json',dict(status='awaiting_user_review',runtime=evidence(dest/'runtime.json'),
                                        manifest=evidence(dest/'manifest.json'),predictions=None))
            self.assertFalse(already_finished(base,2,'test'))

    def test_output_coverage_and_partial_date_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'output.csv'
            fields = ['image_id','year','month','day','final_date']
            rows = [dict(image_id='a',year='NONE',month='02',day='29',final_date='NONE-02-29'),
                    dict(image_id='b',year='2026',month='02',day='NONE',final_date='2026-02-NONE')]
            csv_write(path,rows,fields)
            self.assertEqual(validate_output(path,['a','b']),2)
            with self.assertRaisesRegex(ValueError,'coverage'): validate_output(path,['a'])
            csv_write(path,[rows[0],rows[0]],fields)
            with self.assertRaisesRegex(ValueError,'coverage'): validate_output(path,['a','b'])
            csv_write(path,[dict(image_id='a',year='2026',month='02',day='30',final_date='2026-02-30')],fields)
            with self.assertRaises(ValueError): validate_output(path,['a'])
