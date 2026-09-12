import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class RepositoryLayoutTests(unittest.TestCase):
    def test_submission_entrypoints_remain_at_root(self):
        for name in ('predict.ipynb','requirements.txt','README.md','.gitignore','download_weights.sh','src/pipeline.py'):
            self.assertTrue((ROOT/name).is_file(),name)
        notebook=json.loads((ROOT/'predict.ipynb').read_text(encoding='utf-8'))
        self.assertIn('ITDA_INPUT_DIR',''.join(notebook['cells'][0]['source']))
        self.assertIn('from src.pipeline import run_pipeline',''.join(notebook['cells'][1]['source']))

    def test_training_environment_location_is_consistent(self):
        self.assertTrue((ROOT/'notebooks/environment/requirements-train-cpu.lock.txt').is_file())
        script=(ROOT/'scripts/prepare_training_runtime.ps1').read_text(encoding='utf-8')
        self.assertIn('notebooks\\environment\\requirements-train-cpu.lock.txt',script)
        self.assertTrue((ROOT/'notebooks/README.md').is_file())
