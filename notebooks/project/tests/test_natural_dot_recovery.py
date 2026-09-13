import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.thin_dot_recovery import thin_views, recover_thin_dots
from src.pipeline import predict_image, PipelineConfig
from src.date_extraction import OCRLine, DateContext, select_date


class NaturalDotTest(unittest.TestCase):
    def setUp(self):
        self.image=np.full((120,1000,3),220,np.uint8)
        self.image[30:34,40:44]=0
        self.quad=((0.,0.),(999.,0.),(999.,119.),(0.,119.))

    def test_natural_views_keep_wide_geometry_and_change_pixels(self):
        views=thin_views(self.image,self.quad,natural=True)
        self.assertEqual(len(views),2)
        self.assertGreater(views[0][1].shape[1],624)
        self.assertFalse(np.array_equal(views[0][1],views[1][1]))

    def test_bounded_low_contrast_regions_and_strict_repeated_digits(self):
        reading=('2028.07.29',.90,(.97,)*10)
        with patch('src.thin_dot_recovery.dot_row_proposals',return_value=[self.quad]) as p:
            added,_,decisions,_=recover_thin_dots(self.image,[],lambda c:[reading]*2,natural=True)
        self.assertEqual(p.call_args.kwargs,dict(limit=6,thin=True,contrast=8))
        self.assertEqual(added[0].variant,'natural-dot-rows')
        self.assertEqual(decisions[0]['stage'],'natural-dot-rows')
        self.assertEqual(select_date(added,final=True,context=DateContext()).final_date,'2028-07-29')

    def test_natural_geometry_does_not_relax_confidence_or_conflicts(self):
        for readings in ([('2028.07.29',.6,(.6,)*10)]*2,
                         [('2028.07.29',.99,(.99,)*10),('2029.07.29',.99,(.99,)*10)]):
            with patch('src.thin_dot_recovery.dot_row_proposals',return_value=[self.quad]):
                self.assertFalse(recover_thin_dots(self.image,[],lambda c:readings,natural=True)[0])

    def run_pipeline(self,text):
        class Backend:
            def recognize(self,image,*,detector,variant):
                return [OCRLine(text,.99,(0,0,700,70),variant=variant)] if text else []
            def recognize_crops(self,crops):return []
        with patch('src.pipeline._load_bgr',return_value=self.image), \
                patch('src.pipeline.recover_lines',side_effect=lambda image,lines,*a:(lines,[],[],0.)), \
                patch('src.pipeline.recover_geometric_rows',return_value=([],[],[],0.)), \
                patch('src.pipeline.recover_printed_context',return_value=([],[],[],0.)), \
                patch('src.pipeline.recover_thin_dots',return_value=([],[],[],0.)) as rec:
            result=predict_image(Path('generic-package.jpg'),Backend(),PipelineConfig())
        return result,rec.call_args_list

    def test_natural_retry_only_for_unresolved_order(self):
        result,calls=self.run_pipeline('26.07.29')
        self.assertIsNone(result.final_date)
        self.assertEqual([c.kwargs['natural'] for c in calls],[False,True])

    def test_existing_full_date_negative_and_missing_evidence_do_not_enter_natural_retry(self):
        for text in ('EXP 2028.07.29','MFG 2028.07.29',''):
            _,calls=self.run_pipeline(text)
            self.assertFalse(any(c.kwargs.get('natural') for c in calls))

if __name__=='__main__':unittest.main()
