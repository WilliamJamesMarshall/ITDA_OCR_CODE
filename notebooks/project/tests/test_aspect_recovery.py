import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import numpy as np

from src.date_extraction import OCRLine, DateSelection
from src.date_region_recovery import recognition_views
from src.line_recovery import recover_lines, recovery_targets
from src.pipeline import PipelineConfig, predict_image


def read(text):
    return text, .98, (.98,)*len(text)


class AspectRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.image=np.full((200,800,3),255,dtype=np.uint8)
        self.quad=((20,40),(720,40),(720,100),(20,100))

    def test_wide_rows_two_different_bounded_aspects(self):
        views=recognition_views(self.image,self.quad)
        self.assertEqual([v[0] for v in views],['aspect-4.8','aspect-5.2'])
        self.assertNotEqual(views[0][1].shape,views[1][1].shape)
        for (_,crop),ratio in zip(views,(4.8,5.2)):
            self.assertAlmostEqual(crop.shape[1]/crop.shape[0],ratio,delta=.02)

    def test_short_rows_do_not_count_identical_resize_as_two_views(self):
        views=recognition_views(self.image,((20,40),(220,40),(220,100),(20,100)))
        self.assertEqual([v[0] for v in views],['padding-0.0','padding-0.16'])
        self.assertNotEqual(views[0][1].shape,views[1][1].shape)
        self.assertEqual(recognition_views(self.image,()),[])

    def test_unparsed_secondary_axis_failure_can_use_rectified_aspects(self):
        line=OCRLine('EO27.0R2028',.7,(20,40,720,100),polygon=self.quad)
        calls=[]
        def secondary(crops):
            calls.append(len(crops))
            return [read('garbled')]*len(crops) if len(calls)==1 else [read('ED 27.04.2028')]*len(crops)
        active,_,decisions,_=recover_lines(self.image,[line],lambda crops:[read('noise')]*len(crops),secondary)
        self.assertEqual(calls,[3,2])
        self.assertEqual(active[0].text,'ED 27.04.2028')
        self.assertEqual(decisions[-1]['stage'],'rectified-unparsed-recheck')

    def test_middle_dot_damaged_date_is_a_recovery_hint_not_a_date_rewrite(self):
        line=OCRLine('EP 309·2922',.7,(20,40,720,100),polygon=self.quad)
        self.assertEqual(recovery_targets([line]),[0])
        active,_,_,_=recover_lines(self.image,[line],lambda crops:[read('noise')]*len(crops))
        self.assertEqual(active[0].text,line.text)

    def test_review_order_can_search_but_explicit_omission_cannot(self):
        class Backend:
            def recognize(self,image,**kwargs):return []
            def recognize_crops(self,crops):return []
        cfg=PipelineConfig(enable_line_recovery=False)
        for reason,called in [('review_order:unknown_context',True),('expiry-not-printed',False),('negative-context',False)]:
            selection=DateSelection(None,2.,1.,True,reason,())
            with patch('src.pipeline._load_bgr',return_value=self.image), \
                    patch('src.pipeline._append_pass',return_value=selection), \
                    patch('src.pipeline.recover_geometric_rows',return_value=([],[],[],.01)) as recovery:
                predict_image(Path('anonymous.jpg'),Backend(),cfg)
                self.assertEqual(recovery.called,called)


if __name__=='__main__':unittest.main()
