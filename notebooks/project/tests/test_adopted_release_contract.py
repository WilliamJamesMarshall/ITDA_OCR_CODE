"""The deployed model reference must match the explicit final adoption record."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


class AdoptedReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT/'weights/adopted_model.json').read_text(encoding='utf-8-sig'))

    def test_adoption_record_hash_and_model(self):
        proof = self.manifest['adoption_approval']
        raw = (ROOT/proof['path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), proof['sha256'])
        record = json.loads(raw)
        self.assertEqual(record['inference_pdiparams_sha256'], self.manifest['inference_files']['inference.pdiparams'])
        self.assertEqual(record['checkpoint_sha256'], self.manifest['checkpoint_sha256'])
        self.assertEqual(record['status'], 'complete')
        self.assertEqual(record['completion_kind'], 'explicit_user_adoption')
        self.assertFalse(record['automatic_performance_gate_passed'])

    def test_download_references_exact_release_and_hashes(self):
        script = (ROOT/'download_weights.sh').read_text(encoding='utf-8-sig')
        tag = self.manifest['distribution']['tag']
        self.assertIn('/releases/download/'+tag+'/', script)
        self.assertIn('/releases/tag/'+tag, (ROOT/'README.md').read_text(encoding='utf-8-sig'))
        for name, digest in self.manifest['inference_files'].items():
            self.assertIn(f'verify_adopted "{name}" "{digest}"', script)
            self.assertEqual(self.manifest['full_bundle'][self.manifest['model']+'/'+name], digest)

    def test_round_totals_and_regressions_are_preserved(self):
        evaluation = self.manifest['evaluation']
        self.assertEqual(set(evaluation['rounds']), {str(n) for n in range(1,7)})
        for field in ('field_correct','field_total','historical_field_correct','historical_gains','historical_losses'):
            self.assertEqual(sum(r[field] for r in evaluation['rounds'].values()), evaluation[field])
        self.assertEqual(evaluation['field_correct']-evaluation['historical_field_correct'],
                         evaluation['historical_gains']-evaluation['historical_losses'])
        self.assertFalse(evaluation['performance_targets_met'])
        self.assertFalse(evaluation['same_code_comparison'])


if __name__ == '__main__':
    unittest.main()
