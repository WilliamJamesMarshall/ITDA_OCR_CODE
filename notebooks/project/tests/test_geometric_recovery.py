import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.date_extraction import OCRLine
from src.date_region_recovery import (rectified_crop, split_row_polygon,
                                      numeric_region_proposals, dot_row_proposals,
                                      recover_geometric_rows)
from src.line_recovery import recover_lines
from src.pipeline import PipelineConfig, predict_image


def reading(text, score=.98):
    return text, score, (score,) * len(text)


class GeometricRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((200, 600, 3), 255, dtype=np.uint8)
        self.quad = ((30., 40.), (500., 40.), (500., 120.), (30., 120.))
        self.line = OCRLine('2028.04.21', .95, (30, 40, 500, 120),
                            polygon=self.quad, original_box=(30, 40, 500, 120))

    def test_rectification_requires_valid_horizontal_quad(self):
        self.assertEqual(rectified_crop(self.image, self.quad).shape, (80, 470, 3))
        for polygon in [(), ((0, 0),), ((0, 0), (5, 0), (5, 90), (0, 90)),
                        ((0, 0), (float('nan'), 0), (50, 40), (0, 40))]:
            self.assertIsNone(rectified_crop(self.image, polygon))

    def test_split_two_ink_rows_not_one(self):
        cv2.putText(self.image, '2028.04.24', (40, 69), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0), 2)
        cv2.putText(self.image, '10:43 F3', (40, 108), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0), 2)
        self.assertEqual(len(split_row_polygon(self.image, self.quad)), 2)
        self.assertEqual(split_row_polygon(np.full_like(self.image, 255), self.quad), [self.quad])

    def test_numeric_proposals_keep_large_weak_fragments_but_not_phone(self):
        lines = [replace(self.line, text='7지', score=.6),
                 replace(self.line, text='080-123-4567'), replace(self.line, text='10:43')]
        self.assertEqual(numeric_region_proposals(self.image, lines), [self.quad])
        self.assertLessEqual(len(numeric_region_proposals(self.image, [self.line]*10)), 4)

    def test_dot_search_blank_and_bounded_synthetic_rows(self):
        self.assertEqual(dot_row_proposals(self.image), [])
        for y in (50, 54, 58, 62, 66):
            for x in range(60, 400, 8):
                cv2.circle(self.image, (x, y), 1, (0, 0, 0), -1)
        proposals = dot_row_proposals(self.image)
        self.assertGreater(len(proposals), 0)
        self.assertLessEqual(len(proposals), 4)

    def conflict(self, secondary):
        primary = lambda crops: [reading('2028.04.21'), reading('2028.04.24'), reading('noise', .6)]
        return recover_lines(self.image, [self.line], primary, lambda crops: secondary)

    def test_rectified_conflict_two_strong_views_can_replace(self):
        active, _, decisions, _ = self.conflict([reading('2028.04.24')]*2)
        self.assertEqual(active[0].text, '2028.04.24')
        self.assertEqual(active[0].box, self.line.box)
        self.assertEqual(decisions[-1]['stage'], 'rectified-conflict-recheck')

    def test_rectified_conflict_disagreement_or_weak_digit_keeps_original(self):
        for results in [[reading('2028.04.24'), reading('2028.04.25')],
                        [reading('2028.04.24', .7)]*2]:
            self.assertEqual(self.conflict(results)[0][0], self.line)

    def test_unchanged_primary_does_not_load_secondary(self):
        def forbidden(crops):
            self.fail('No conflict, secondary must not load')
        active, _, _, _ = recover_lines(self.image, [self.line],
            lambda crops: [reading(self.line.text)]*len(crops), forbidden)
        self.assertEqual(active[0], self.line)

    def geometric(self, primary, secondary=None, polygons=None):
        with patch('src.date_region_recovery.numeric_region_proposals', return_value=polygons or [self.quad]), \
                patch('src.date_region_recovery.dot_row_proposals', return_value=[]):
            return recover_geometric_rows(self.image, [], primary, secondary)

    def test_new_row_needs_two_aligned_unrepaired_views(self):
        for text, score, accepted in [('2028.04.24', .98, 1), ('2028.04.24', .7, 0), ('2028.04.24', .9, 0)]:
            result = self.geometric(lambda crops: [reading(text, score)]*len(crops))
            # Repeated .90 character support meets complementary evidence gate.
            self.assertEqual(len(result[0]), 1 if score == .9 else accepted)
        self.assertEqual(self.geometric(lambda crops: [('2028.04.24', .99)]*len(crops))[0], [])

    def test_cross_recognizer_conflict_and_overlap_never_create_votes(self):
        p = lambda crops: [reading('2028.04.24')]*len(crops)
        s = lambda crops: [reading('2028.04.25')]*len(crops)
        self.assertEqual(self.geometric(p, s)[0], [])
        self.assertEqual(len(self.geometric(p, polygons=[self.quad]*4)[0]), 1)

    def test_optional_failure_is_audited(self):
        def broken(crops):
            raise RuntimeError('injected')
        added, _, decisions, _ = self.geometric(broken)
        self.assertEqual(added, [])
        self.assertEqual(decisions[0]['reason'], 'geometric-recognition-error')

    def test_pipeline_only_abstentions_and_trace_equivalence(self):
        class Backend:
            def recognize(inner, image, **kwargs):
                return []
            def recognize_crops(inner, crops):
                return []
        cfg = PipelineConfig(enable_line_recovery=False, enable_clahe=False,
                             enable_recovery_fallback=False, enable_tile_fallback=False)
        added = replace(self.line, text='EXP 2028.04.24')
        with patch('src.pipeline._load_bgr', return_value=self.image), \
                patch('src.pipeline.recover_geometric_rows', return_value=([added], [added], [], .01)) as recovery:
            on = predict_image(Path('anonymous.jpg'), Backend(), cfg)
            off = predict_image(Path('different.jpg'), Backend(), replace(cfg, collect_trace=False))
            self.assertEqual(on.final_date, '2028-04-24')
            self.assertEqual(on.final_date, off.final_date)
            self.assertEqual(recovery.call_count, 2)
            with patch.object(Backend, 'recognize', return_value=[added]):
                predict_image(Path('correct.jpg'), Backend(), cfg)
            self.assertEqual(recovery.call_count, 2)
            predict_image(Path('disabled.jpg'), Backend(), replace(cfg, enable_geometric_recovery=False))
            self.assertEqual(recovery.call_count, 2)


if __name__ == '__main__':
    unittest.main()
