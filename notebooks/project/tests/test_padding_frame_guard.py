import unittest
import numpy as np
from types import SimpleNamespace
from src.recognizer_padding import mask_padding_frames,GeometryResize,GeometryRunner

class PaddingFrameTests(unittest.TestCase):
    def test_only_frames_beyond_real_pixels_are_blanked(self):
        p=np.zeros((1,40,3));p[:,:,0]=1;p[0,21]=[0,1,0];p[0,29]=[0,0,1]
        before=p.copy();out=mask_padding_frames(p,[193/320])
        np.testing.assert_array_equal(out[0,:25],p[0,:25])
        self.assertEqual(out[0,29].argmax(),0);np.testing.assert_array_equal(p,before)

    def test_real_trailing_zero_and_boundary_frame_are_preserved(self):
        p=np.zeros((1,40,3));p[:,:,0]=1;p[0,24]=[0,0,1]
        self.assertEqual(mask_padding_frames(p,[193/320])[0,24].argmax(),2)
        self.assertIs(mask_padding_frames(p,[1.0]),p)

    def test_different_rows_use_their_own_geometry(self):
        p=np.ones((2,10,3));out=mask_padding_frames(p,[.3,1.])
        np.testing.assert_array_equal(out[1],p[1]);self.assertEqual(out[0,5].argmax(),0)

    def test_bad_geometry_fails(self):
        for ratios in ([0],[1.2],[float('nan')],[]):
            with self.assertRaises(ValueError):mask_padding_frames(np.ones((1,4,3)),ratios)

    def test_resize_proxy_preserves_width_override_and_runner_contract(self):
        class Resize:
            rec_image_shape=[3,48,320];input_shape=None
            def __call__(self,imgs):return [np.zeros((3,48,self.rec_image_shape[2])) for _ in imgs]
        r=GeometryResize(Resize());r([np.zeros((146,585,3))]);self.assertEqual(r.valid_ratios,[193/320])
        runner=GeometryRunner(lambda **kwargs:[np.ones((1,40,3))],r)
        self.assertEqual(runner(x=[])[0][0,29].argmax(),0)
        r.rec_image_shape=[3,48,193];r([np.zeros((146,585,3))]);self.assertEqual(r.valid_ratios,[1.])

if __name__=='__main__':unittest.main()
