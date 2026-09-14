import ast
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]

class RepositoryLayoutTests(unittest.TestCase):
    def test_submission_entrypoints_remain_at_root(self):
        for name in ('predict.ipynb','requirements.txt','README.md','.gitignore','download_weights.sh','notebooks/project/src/pipeline.py'):
            self.assertTrue((ROOT/name).is_file(),name)
        notebook=json.loads((ROOT/'predict.ipynb').read_text(encoding='utf-8'))
        self.assertIn('ITDA_INPUT_DIR',''.join(notebook['cells'][0]['source']))
        source='\n'.join(''.join(cell.get('source',[])) for cell in notebook['cells'])
        if notebook.get('metadata',{}).get('itda_embedded'):
            from scripts.grouped_rounds import embedded_source_manifest
            self.assertTrue(embedded_source_manifest(ROOT))
            entry=ast.parse(''.join(notebook['cells'][-1]['source']))
            calls=[node for node in ast.walk(entry) if isinstance(node,ast.Call)
                   and isinstance(node.func,ast.Attribute) and node.func.attr=='run_pipeline']
            self.assertEqual(len(calls),1)
            self.assertEqual([arg.id for arg in calls[0].args],['INPUT_DIR','OUTPUT_PATH'])
            self.assertIn('notebook_started',[kw.arg for kw in calls[0].keywords])
        else:
            self.assertIn('from src.pipeline import run_pipeline',source)

    def test_training_environment_location_is_consistent(self):
        self.assertTrue((ROOT/'notebooks/environment/requirements-train-cpu.lock.txt').is_file())
        script=(ROOT/'notebooks/project/scripts/prepare_training_runtime.ps1').read_text(encoding='utf-8')
        self.assertIn('notebooks\\environment\\requirements-train-cpu.lock.txt',script)
        self.assertTrue((ROOT/'notebooks/README.md').is_file())
