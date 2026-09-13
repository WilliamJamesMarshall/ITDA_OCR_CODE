import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.pipeline import PaddleOCRBackend, PipelineConfig, predict_image
from src.date_extraction import OCRLine


class RecoveryExecutionTest(unittest.TestCase):
    def test_exact_cache_separates_models_shapes_pixels_and_images(self):
        backend=object.__new__(PaddleOCRBackend);backend.begin_image()
        image=np.zeros((20,40,3),dtype=np.uint8);models=[object(),object()];calls=[]
        def recognize(model,crops):
            calls.append(len(crops));return [('text',.99,(.99,)*4)]*len(crops)
        with patch.object(backend,'_recognize_with_evidence',side_effect=recognize):
            first=backend._recognize_cached(models[0],[image,image.copy()])
            self.assertEqual(first,backend._recognize_cached(models[0],[image,image.copy()]))
            self.assertEqual(calls,[1])
            backend._recognize_cached(models[1],[image])
            backend._recognize_cached(models[0],[image.reshape(40,20,3)])
            changed=image.copy();changed[0,0,0]=1
            backend._recognize_cached(models[0],[changed])
            backend.begin_image();backend._recognize_cached(models[0],[image])
        self.assertEqual(calls,[1,1,1,1,1])

    def test_cache_is_bounded_and_requires_matching_results(self):
        backend=object.__new__(PaddleOCRBackend);backend.begin_image()
        crops=[np.full((2,2,3),i,dtype=np.uint8) for i in range(140)]
        with patch.object(backend,'_recognize_with_evidence',return_value=[('x',.9,())]*140):
            self.assertEqual(len(backend._recognize_cached(object(),crops)),140)
        self.assertLessEqual(len(backend._crop_cache),128)
        with patch.object(backend,'_recognize_with_evidence',return_value=[]):
            with self.assertRaises(ValueError):backend._recognize_cached(object(),crops)

    def test_early_geometry_strong_date_can_stop_without_detector_retries(self):
        class Backend:
            def __init__(self):self.calls=[]
            def recognize(self,image,*,detector,variant):
                self.calls.append((detector,variant));return []
            def recognize_crops(self,crops):return []
        backend=Backend();image=np.full((120,400,3),255,dtype=np.uint8)
        added=OCRLine('EXP 2028.04.24',.99,(0,0,300,40),original_box=(0,0,300,40))
        with patch('src.pipeline._load_bgr',return_value=image), \
                patch('src.pipeline.recover_geometric_rows',return_value=([added],[added],[],.01)) as geometry:
            result=predict_image(Path('not-an-id.jpg'),backend,PipelineConfig())
        self.assertEqual(result.final_date,'2028-04-24')
        self.assertEqual(backend.calls,[('mobile','original')])
        self.assertEqual(geometry.call_count,1)

    def test_failed_geometry_is_reused_and_does_not_skip_later_detection(self):
        class Backend:
            def __init__(self):self.calls=[]
            def recognize(self,image,*,detector,variant):
                self.calls.append((detector,variant));return []
            def recognize_crops(self,crops):return []
        backend=Backend()
        with patch('src.pipeline._load_bgr',return_value=np.full((120,400,3),255,dtype=np.uint8)), \
                patch('src.pipeline.recover_geometric_rows',return_value=([],[],[],.01)) as geometry:
            result=predict_image(Path('not-an-id.jpg'),backend,PipelineConfig())
        self.assertIsNone(result.final_date)
        self.assertIn(('recovery','original'),backend.calls)
        self.assertEqual(geometry.call_count,1)

    def test_early_conflicting_dates_do_not_short_circuit_detection(self):
        class Backend:
            def __init__(self):self.calls=[]
            def recognize(self,image,*,detector,variant):
                self.calls.append((detector,variant));return []
            def recognize_crops(self,crops):return []
        backend=Backend()
        added=[OCRLine(text,.99,box,original_box=box) for text,box in
               [('EXP 2028.04.24',(0,0,300,40)),('EXP 2029.04.24',(0,70,300,110))]]
        with patch('src.pipeline._load_bgr',return_value=np.full((120,400,3),255,dtype=np.uint8)), \
                patch('src.pipeline.recover_geometric_rows',return_value=(added,added,[],.01)):
            predict_image(Path('not-an-id.jpg'),backend,PipelineConfig())
        self.assertIn(('recovery','original'),backend.calls)


if __name__=='__main__':unittest.main()
