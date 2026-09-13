import json
import tempfile
import unittest
from pathlib import Path
from scripts.grouped_rounds import embedded_source_manifest
from scripts.prepare_sequential_rounds import digest


class EmbeddedSourceManifestTests(unittest.TestCase):
    def test_legacy_has_no_embedded_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'predict.ipynb').write_text('{"metadata":{}}')
            self.assertIsNone(embedded_source_manifest(root))

    def test_exact_sources_required_and_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src = root/'notebooks/project/src'
            src.mkdir(parents=True)
            code = src/'pipeline.py'
            code.write_text('VALUE = 1')
            expected = {'pipeline': digest(code)}
            metadata = dict(schema=1, sources=expected, external_project_source_required=False)
            (root/'predict.ipynb').write_text(json.dumps(dict(metadata=dict(itda_embedded=metadata))))
            self.assertEqual(embedded_source_manifest(root), expected)
            code.write_text('VALUE = 2')
            with self.assertRaises(ValueError):
                embedded_source_manifest(root)
            code.write_text('VALUE = 1')
            (src/'new_module.py').write_text('VALUE = 3')
            with self.assertRaises(ValueError):
                embedded_source_manifest(root)


if __name__ == '__main__':
    unittest.main()
