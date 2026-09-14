import unittest
from types import SimpleNamespace
from src.pipeline import configure_recognizer_width


class RecognizerPaddingTests(unittest.TestCase):
    def test_only_minimum_width_changes(self):
        resize = SimpleNamespace(rec_image_shape=[3,48,320])
        model = SimpleNamespace(pre_tfs={'ReisizeNorm':resize})
        configure_recognizer_width(model,160)
        self.assertEqual(resize.rec_image_shape,[3,48,160])

    def test_unsupported_width_or_model_shape_fails_closed(self):
        model = SimpleNamespace(pre_tfs={'ReisizeNorm':SimpleNamespace(rec_image_shape=[3,32,320])})
        with self.assertRaises(ValueError): configure_recognizer_width(model,160)
        with self.assertRaises(ValueError): configure_recognizer_width(model,1)
