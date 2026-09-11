import unittest
import numpy as np
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace

from src.date_extraction import OCRLine
from src.line_recovery import recover_lines, recovery_targets
from src.pipeline import PipelineConfig, predict_image


class LineRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((120,400,3),180,dtype=np.uint8)
        self.line = OCRLine('a0E1.0R0EH', .80,(10,20,210,50),original_box=(10,20,210,50))

    def recover(self, results, lines=None):
        return recover_lines(self.image, lines or [self.line],lambda crops:results)

    def test_visual_recovery_not_digit_substitution(self):
        active,obs,decisions,_ = self.recover([('20210902R',.92)]*3)
        self.assertEqual(active[0].text,'20210902R')
        self.assertEqual(active[0].box,self.line.box)
        self.assertEqual(len(obs),3)
        self.assertEqual(decisions[0]['original_text'],self.line.text)

    def test_two_views_from_same_model_are_not_selector_votes(self):
        active,_,_,_ = self.recover([('20210902R',.92),('20210902R',.89),('garbled',.6)])
        self.assertEqual(len(active),1)
        self.assertEqual(active[0].score,.89)

    def test_competing_readings_keep_original(self):
        active,_,_,_ = self.recover([('20210902',.92),('20210902',.92),('20210903',.92)])
        self.assertEqual(active[0],self.line)

    def test_low_confidence_votes_do_not_repair(self):
        active,_,_,_ = self.recover([('20210902',.80)]*3)
        self.assertEqual(active[0],self.line)

    def test_weak_heading_and_clear_date_are_separated(self):
        text = 'EXP 2021.09.02'
        scores = tuple(.4 if c.isalpha() else .97 for c in text)
        active,obs,_,_ = self.recover([(text,.8,scores)]*3)
        self.assertEqual(active[0].text,text)
        self.assertEqual(active[0].score,.8)
        self.assertAlmostEqual(active[0].date_digit_score,.97)
        self.assertEqual(obs[0].character_scores,scores)

    def test_weak_digit_is_not_hidden_by_average_score(self):
        text = 'EXP 2021.09.02'
        scores = tuple(.3 if i==7 else .99 for i in range(len(text)))
        active,_,_,_ = self.recover([(text,.8,scores)]*3)
        self.assertEqual(active[0],self.line)

    def test_unchanged_reading_does_not_inflate_score(self):
        original = OCRLine('2021.09.02',.9,self.line.box)
        active,_,_,_ = self.recover([('2021.09.02',.99)]*3,[original])
        self.assertEqual(active[0],original)

    def test_max_two_regions(self):
        self.assertEqual(len(recovery_targets([self.line]*5)),2)

    def test_nutrition_time_and_unknown_geometry_excluded(self):
        rows = [OCRLine(t,.9,self.line.box) for t in ['영양 20.06.21%','19:25','TEL 080-123-4567']]
        rows.append(OCRLine('2026.09.25',.9,self.line.box,geometry_valid=False))
        self.assertEqual(recovery_targets(rows),[])

    def test_result_count_mismatch_is_error(self):
        with self.assertRaises(ValueError):
            self.recover([])

    def test_trace_switch_does_not_change_recovery(self):
        class Backend:
            def recognize(inner, image, **kwargs):
                return [self.line]

            def recognize_crops(inner, crops):
                return [('2021.09.02R',.92)]*len(crops)
        config = PipelineConfig(enable_clahe=False,enable_recovery_fallback=False,enable_tile_fallback=False)
        with patch('src.pipeline._load_bgr',return_value=self.image):
            on = predict_image(Path('sample.jpg'),Backend(),config)
            off = predict_image(Path('sample.jpg'),Backend(),replace(config,collect_trace=False))
        self.assertEqual(on.final_date,'2021-09-02')
        self.assertEqual(on.final_date,off.final_date)
        self.assertEqual(on.passes,off.passes)
        self.assertEqual(on.trace['summary']['line_recovery_changes'],1)

    def test_optional_recognition_error_preserves_base_output(self):
        class Backend:
            def recognize(inner, image, **kwargs):
                return [OCRLine('EXP 2026.09.25',.99,self.line.box)]

            def recognize_crops(inner, crops):
                raise RuntimeError('injected')
        with patch('src.pipeline._load_bgr',return_value=self.image):
            result = predict_image(Path('sample.jpg'),Backend(),PipelineConfig())
        self.assertEqual(result.final_date,'2026-09-25')
        self.assertEqual(result.trace['summary']['failed_passes'],1)


if __name__ == '__main__':
    unittest.main()
