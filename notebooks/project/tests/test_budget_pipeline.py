import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
import numpy as np

from src.budget_pipeline import run_budget_pipeline, RecoveryGuard, BudgetExhausted, recovery_queue
from src.pipeline import PipelineConfig
from src.date_extraction import OCRLine
from src.performance_profile import Profile, TimedPredictor
from src.shared_detector import SharedDetectorView


class Clock:
    def __init__(self):
        self.value = 0.
    def __call__(self):
        return self.value


class Backend:
    def __init__(self, clock, cost=1, error_at=None, no_date=False):
        self.clock, self.cost, self.error_at, self.no_date = clock, cost, error_at, no_date
        self.calls = 0
    def recognize(self, image, **kwargs):
        self.calls += 1
        self.clock.value += self.cost
        if self.calls == self.error_at:
            raise RuntimeError('synthetic inference failure')
        return [] if self.no_date else [OCRLine('2026.05.29', .99, (0,0,20,10))]


class BudgetPipelineTests(unittest.TestCase):
    def test_error_classes_are_interleaved_without_reordering_each_class(self):
        items = [dict(priority=0,index=0),dict(priority=0,index=1),dict(priority=1,index=2),
                 dict(priority=2,index=3),dict(priority=2,index=4)]
        self.assertEqual([item['index'] for item in recovery_queue(items)], [0,2,3,1,4])
        self.assertEqual(recovery_queue([]), [])

    def run_case(self, count=3, budget=20., cost=1, error_at=None, no_date=False):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        inputs = root/'inputs'
        inputs.mkdir()
        for i in range(count):
            Image.new('RGB',(16,16),'white').save(inputs/f'{i:06d}.png')
        clock = Clock()
        backend = Backend(clock, cost, error_at, no_date)
        output = root/'submission.csv'
        config = PipelineConfig(collect_trace=False, progress_every=0)
        result = run_budget_pipeline(inputs, output, backend=backend, config=config,
                                     budget_seconds=budget, reserve_seconds=2, clock=clock)
        return root, result, backend, inputs, config

    def test_all_500_receive_base_ocr(self):
        root, result, backend, _, _ = self.run_case(count=500, budget=1500.)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['processed_images'], 500)
        self.assertEqual(backend.calls, 500)
        with (root/'submission.csv').open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 500)

    def test_no_unprocessed_none_padding_on_deadline(self):
        root, result, backend, _, _ = self.run_case(count=5, budget=5., cost=2)
        self.assertEqual(result['status'], 'timeout')
        self.assertEqual(result['processed_images'], 2)
        self.assertEqual(result['unprocessed_ids'], ['000002','000003','000004'])
        self.assertFalse((root/'submission.csv').exists())
        with (root/'submission.csv.partial.csv').open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 2)

    def test_failed_base_is_retained_and_not_complete(self):
        root, result, _, _, _ = self.run_case(error_at=2)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['processed_images'], 2)
        self.assertEqual(result['attempted_images'], 3)
        self.assertEqual(len(result['failures']), 1)
        self.assertFalse((root/'submission.csv').exists())
        self.assertTrue((root/'submission.csv.partial.csv').exists())

    def test_recovery_only_after_last_base_and_reuses_observations(self):
        events = []
        clock = Clock()
        backend = Backend(clock, no_date=True)
        backend.recognize_crops = lambda crops: []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for i in range(3):
                Image.new('RGB',(16,16)).save(root/f'{i}.png')
            def recover(action, image, lines, backend, guard, config, trace, commit):
                events.append(backend.calls)
                return [OCRLine('2026.05.29', .99, (0,0,20,10))], [], [], 0.
            with patch('src.budget_pipeline.run_stage', side_effect=recover):
                result = run_budget_pipeline(root, root/'out.csv', backend=backend,
                    config=PipelineConfig(collect_trace=False,progress_every=0),
                    budget_seconds=20, reserve_seconds=2, clock=clock)
            self.assertEqual(events, [3,3,3])
            self.assertEqual(backend.calls, 3)
            self.assertEqual(result['processed_images'], 3)

    def test_existing_outputs_not_overwritten(self):
        root, _, backend, inputs, config = self.run_case()
        original = (root/'submission.csv').read_bytes()
        with self.assertRaises(FileExistsError):
            run_budget_pipeline(inputs, root/'submission.csv', backend=backend, config=config)
        self.assertEqual(original, (root/'submission.csv').read_bytes())

    def test_native_call_can_overrun_but_is_not_reported_within_budget(self):
        _, result, _, _, _ = self.run_case(count=1, budget=5, cost=8)
        self.assertEqual(result['status'], 'timeout')
        self.assertEqual(result['processed_images'], 1)
        self.assertGreater(result['total_elapsed_seconds'], result['budget_seconds'])

    def test_recovery_guard_checks_clock_call_count_and_crop_size(self):
        clock = Clock()
        backend = SimpleNamespace(recognize_crops=lambda crops: ['x']*len(crops))
        guard = RecoveryGuard(backend, 2, clock, max_calls=1, max_crops=2)
        with self.assertRaises(BudgetExhausted):
            guard.recognize_crops([1,2,3])
        self.assertEqual(guard.recognize_crops([1]), ['x'])
        with self.assertRaises(BudgetExhausted):
            guard.recognize_crops([1])
        clock.value = 3
        with self.assertRaises(BudgetExhausted):
            RecoveryGuard(backend, 2, clock).recognize_crops([1])

    def test_invalid_budget(self):
        for budget in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                run_budget_pipeline('unused','unused',budget_seconds=budget)

    def test_each_image_has_cumulative_recovery_allowance(self):
        clock = Clock()
        backend = Backend(clock, no_date=True)
        actions = []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for i in range(2):
                Image.new('RGB',(16,16)).save(root/f'{i}.png')
            def recover(action, image, lines, backend, guard, config, trace, commit):
                actions.append(action)
                clock.value += 3
                return lines, [], [], 3.
            with patch('src.budget_pipeline.run_stage', side_effect=recover):
                result = run_budget_pipeline(root, root/'out.csv', backend=backend,
                    config=PipelineConfig(collect_trace=False,progress_every=0),
                    budget_seconds=100, reserve_seconds=2, recovery_image_seconds=2, clock=clock)
            self.assertEqual(len(actions), 2)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['recovery_image_seconds'], 2)
            self.assertIn('image_allowance_exhausted', (root/'out.csv.progress.jsonl').read_text())

    def test_new_explicit_contradiction_retracts_previously_selected_date(self):
        clock = Clock()
        class WeakBackend(Backend):
            def recognize(self, image, **kwargs):
                self.calls += 1
                return [OCRLine('2026.05.29',.8,(0,0,200,30))]
        backend = WeakBackend(clock)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new('RGB',(250,100)).save(root/'sample.png')
            def recover(action, image, lines, backend, guard, config, trace, commit):
                return [OCRLine('제조일자 2026.05.29',.99,(0,0,200,30))], [], [], 0.
            with patch('src.budget_pipeline.run_stage', side_effect=recover):
                run_budget_pipeline(root, root/'out.csv', backend=backend,
                    config=PipelineConfig(collect_trace=False,progress_every=0), clock=clock)
            with (root/'out.csv').open() as stream:
                self.assertEqual(next(csv.DictReader(stream))['final_date'], 'NONE')
            events = [json.loads(line) for line in (root/'out.csv.progress.jsonl').read_text(encoding='utf-8').splitlines()]
            checkpoint = next(e for e in events if e['kind']=='recovery_checkpoint')
            self.assertEqual(checkpoint['previous_row']['final_date'], '2026-05-29')
            self.assertTrue(checkpoint['output_changed'])


class ProfileTests(unittest.TestCase):
    def test_generator_consumer_time_excluded_and_mutations_forwarded(self):
        clock = Clock()
        class Model:
            post_op = 'original'
            def __call__(self, values):
                clock.value += 2
                yield 'a'
                clock.value += 3
                yield 'b'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'profile.jsonl'
            model = Model()
            wrapper = TimedPredictor(model, Profile(path), 'rec')
            wrapper.post_op = 'temporary'
            self.assertEqual(model.post_op, 'temporary')
            with patch('src.performance_profile.time.perf_counter', clock), patch('src.performance_profile.time.process_time', clock):
                iterator = wrapper([np.zeros((2,3,3))])
                self.assertEqual(next(iterator), 'a')
                clock.value += 100
                self.assertEqual(next(iterator), 'b')
                self.assertEqual(list(iterator), [])
            event = json.loads(path.read_text())
            self.assertEqual(event['wall_seconds'], 5)
            self.assertEqual(event['results'], 2)
            self.assertEqual(event['shapes'], [[2,3,3]])

    def test_shared_detector_restores_on_success_and_failure(self):
        pipeline = SimpleNamespace(text_det_model='base',text_rec_model='same-recognizer')
        mobile = SimpleNamespace(paddlex_pipeline=pipeline)
        def predict(image, **kwargs):
            self.assertEqual(pipeline.text_det_model,'secondary')
            self.assertEqual(pipeline.text_rec_model,'same-recognizer')
            self.assertEqual(kwargs['text_det_limit_side_len'],1280)
            if image == 'bad':
                raise RuntimeError('synthetic')
            return ['result']
        mobile.predict = predict
        view = SharedDetectorView(mobile,'secondary',1280)
        self.assertEqual(view.predict('good'), ['result'])
        self.assertEqual(pipeline.text_det_model,'base')
        with self.assertRaises(RuntimeError):
            view.predict('bad')
        self.assertEqual(pipeline.text_det_model,'base')


if __name__ == '__main__':
    unittest.main()
