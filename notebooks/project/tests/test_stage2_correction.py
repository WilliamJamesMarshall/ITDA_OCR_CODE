import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from src.shared_detector import inner_ocr_pipeline, SharedDetectorView
from src.date_extraction import OCRLine, DateSelection, DateContext, parse_dates, select_date, _join_role_headers
from src.selective_recovery import needs_recovery
from src.budget_pipeline import run_budget_pipeline, BudgetExhausted, output_selection
from src.pipeline import PipelineConfig


class CorrectionTests(unittest.TestCase):
    def test_four_digit_terminal_year_not_a_clock_hour(self):
        values = parse_dates('29 05 2025:40')
        self.assertEqual([p.value.isoformat() for p in values], ['2025-05-29'])
        self.assertEqual(values[0].raw, '29 05 2025')
        self.assertFalse(parse_dates('05 20:40'))

    def test_secondary_new_date_rows_are_scheduled_for_recognition(self):
        class Backend:
            def recognize(self, image, **kwargs):
                return []
        actions = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            Image.new('RGB', (250, 80)).save(path/'sample.png')
            def stage(action, image, lines, backend, guard, config, trace, commit):
                actions.append(action)
                if action == 'secondary':
                    return [OCRLine('29 05 2025 B1', .94, (0,0,200,25)),
                            OCRLine('29 05 2026 B1', .94, (0,30,200,55))], [], [], 0.
                if action == 'date-lines':
                    return [OCRLine('29 05 2025 B1', .99, (0,0,200,25)),
                            OCRLine('29 05 2026 B1', .99, (0,30,200,55))], [], [], 0.
                return lines, [], [], 0.
            with patch('src.budget_pipeline.run_stage', side_effect=stage):
                run_budget_pipeline(path,path/'out.csv',backend=Backend(),
                                    config=PipelineConfig(collect_trace=False,progress_every=0))
            self.assertEqual(actions, ['secondary','date-lines'])
            self.assertIn('2026-05-29',(path/'out.csv').read_text())

    def test_two_clear_space_separated_dates_use_existing_local_pair_policy(self):
        lines = [OCRLine('29 05 2025 B1', .99, (0,0,200,25)),
                 OCRLine('29 05 2026 B1', .99, (0,30,200,55))]
        selected = select_date(lines, context=DateContext())
        self.assertEqual(selected.final_date, '2026-05-29')
        self.assertTrue(selected.stop_ocr)

    def test_row_confidence_does_not_replace_aligned_digit_evidence(self):
        from dataclasses import replace
        lines = [OCRLine('29 05 2025 B1', .94, (0,0,200,25)),
                 OCRLine('29 05 2026 B1', .94, (0,30,200,55))]
        self.assertFalse(select_date(lines, context=DateContext()).stop_ocr)
        verified = [replace(l, date_digit_score=.99,date_digit_min_score=.95) for l in lines]
        self.assertTrue(select_date(verified, context=DateContext()).stop_ocr)
        weak = [replace(l, date_digit_score=.8,date_digit_min_score=.6) for l in lines]
        self.assertFalse(select_date(weak, context=DateContext()).stop_ocr)

    def test_nutrition_units_are_not_date_fields(self):
        line = OCRLine('나트륨280mg 14 %탄수화물 44 9 14 %당류22 9 22 %', .99, (0,0,400,30))
        self.assertIsNone(select_date([line], final=True, context=DateContext()).final_date)
        date_line = OCRLine('2025.12.04G09:15', .99, (0,0,400,30))
        self.assertEqual(select_date([date_line], final=True, context=DateContext()).final_date, '2025-12-04')

    def test_deadline_does_not_certify_ambiguous_or_new_unanchored_partial(self):
        selection = DateSelection('2044-09-14', 2., .1, False, 'ambiguous', ())
        self.assertIsNone(output_selection(selection).final_date)
        partial = DateSelection('NONE-04-29', 2., 1., False, 'partial-date', ())
        self.assertEqual(output_selection(partial).final_date, 'NONE-04-29')
        self.assertEqual(output_selection(partial, base_partial=True).final_date, 'NONE-04-29')

    def test_real_style_proxy_and_lazy_failure_restore(self):
        inner = SimpleNamespace(text_det_model='mobile', text_rec_model='rec')
        class Proxy:
            def __init__(self):
                self._pipeline = inner
            def __getattr__(self, name):
                return getattr(self._pipeline, name)
        proxy = Proxy()
        mobile = SimpleNamespace(paddlex_pipeline=proxy)
        def predict(image, **kwargs):
            yield inner.text_det_model
            if image == 'bad':
                raise RuntimeError('native failure')
        mobile.predict = predict
        self.assertIs(inner_ocr_pipeline(mobile), inner)
        view = SharedDetectorView(mobile, 'secondary', 1600)
        self.assertEqual(view.predict('good'), ['secondary'])
        with self.assertRaises(RuntimeError):
            view.predict('bad')
        self.assertEqual(inner.text_det_model, 'mobile')
        self.assertNotIn('text_det_model', vars(proxy))

    def test_unsupported_proxy_fails_closed(self):
        with self.assertRaises(TypeError):
            inner_ocr_pipeline(SimpleNamespace(paddlex_pipeline=SimpleNamespace()))

    def test_partial_not_forced_complete_before_recovery(self):
        lines = [OCRLine('2026.03.U8 L1', .95, (0, 0, 200, 30))]
        selection = select_date(lines, final=False)
        self.assertTrue(selection.is_partial)
        self.assertTrue(needs_recovery(selection, lines))

    def test_explicit_month_year_is_not_given_an_invented_day(self):
        lines = [OCRLine('BEST BEFORE END 05/2026', .99, (0, 0, 200, 30))]
        selection = select_date(lines, final=False)
        self.assertEqual(selection.final_date, '2026-05-NONE')
        self.assertFalse(needs_recovery(selection, lines))

    def test_join_header_preserves_members_and_does_not_join_far_words(self):
        lines = [OCRLine('소비', .99, (0, 0, 30, 20)), OCRLine('기한', .99, (0, 21, 30, 41))]
        joined = _join_role_headers(lines)
        self.assertEqual(joined[-1].text, '소비기한')
        self.assertEqual(joined[-1].members, (0, 1))
        self.assertEqual(len(_join_role_headers([lines[0], OCRLine('기한', .99, (300, 0, 340, 20))])), 2)

    def test_manufacturing_reference_not_erased_by_unlabelled_crop(self):
        lines = [OCRLine('제조연월일', .99, (0, 100, 100, 120)),
                 OCRLine('별도표기', .99, (105, 100, 170, 120)),
                 OCRLine('2020.11.19', .99, (0, 0, 140, 20), variant='recovered')]
        self.assertIsNone(select_date(lines, final=True).final_date)
        lines.append(OCRLine('EXP 2026.03.08', .99, (0, 40, 150, 60)))
        self.assertEqual(select_date(lines, final=True).final_date, '2026-03-08')

    def test_completed_recovery_checkpoint_survives_later_deadline(self):
        class Backend:
            def recognize(self, image, **kwargs):
                return [OCRLine('2026.03.U8 L1', .95, (0, 0, 120, 30))]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            Image.new('RGB', (150, 50)).save(path/'sample.png')
            def recover(action, image, lines, backend, guard, config, trace, commit):
                commit([OCRLine('2026.03.08', .99, (0, 0, 120, 30))], [], [], .1)
                raise BudgetExhausted('deadline_exhausted')
            with patch('src.budget_pipeline.run_stage', side_effect=recover):
                result = run_budget_pipeline(path, path/'out.csv', backend=Backend(),
                    config=PipelineConfig(collect_trace=False, progress_every=0))
            self.assertEqual(result['status'], 'completed')
            self.assertIn('2026-03-08', (path/'out.csv').read_text())
            self.assertIn('deadline_exhausted', (path/'out.csv.progress.jsonl').read_text())


if __name__ == '__main__':
    unittest.main()
