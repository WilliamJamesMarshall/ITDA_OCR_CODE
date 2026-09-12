import unittest
import numpy as np

from src.recognition_evidence import CTCEvidence
from src.pipeline import PaddleOCRBackend
from types import SimpleNamespace


class Decoder:
    character = ['blank','1','2']

    def get_ignored_tokens(self):
        return [0]

    def __call__(self, pred, *args, **kwargs):
        return ['112'],[.92]


class RecognitionEvidenceTests(unittest.TestCase):
    def test_ctc_blank_duplicate_alignment(self):
        probabilities = np.array([[[.01,.98,.01],[.01,.97,.02],[.99,.005,.005],
                                  [.01,.95,.04],[.01,.01,.98]]])
        capture = CTCEvidence(Decoder())
        self.assertEqual(capture([probabilities]),(['112'],[.92]))
        self.assertEqual(capture.rows,[('112',(.98,.95,.98))])

    def test_wrong_text_alignment_is_not_guessed(self):
        capture = CTCEvidence(Decoder())
        capture([np.array([[[0.,1.,0.]]])])
        self.assertEqual(capture.rows,[('112',())])

    def test_unknown_shape_keeps_original_decoder_output(self):
        capture = CTCEvidence(Decoder())
        self.assertEqual(capture([np.zeros((1,3))]),(['112'],[.92]))
        self.assertEqual(capture.rows,[('112',())])

    def test_adapter_restores_decoder_on_model_error(self):
        class BrokenModel:
            post_op = Decoder()

            def __call__(self, crops):
                raise RuntimeError('recognizer failed')
        model = BrokenModel()
        original = model.post_op
        backend = object.__new__(PaddleOCRBackend)
        backend._mobile = SimpleNamespace(paddlex_pipeline=SimpleNamespace(text_rec_model=model))
        with self.assertRaises(RuntimeError):
            backend.recognize_crops([np.zeros((10,10,3))])
        self.assertIs(model.post_op,original)


if __name__ == '__main__':
    unittest.main()
