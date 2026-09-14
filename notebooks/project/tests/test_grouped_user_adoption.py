import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.prepare_sequential_rounds import digest
from scripts.grouped_user_adoption import validate_user_adoption


class UserAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pool = dict(admitted={}, group_roles={}, samples=[])
        self.evidence = {}
        for name in ('training_release', 'checkpoint', 'epoch0', 'epoch1'):
            self.evidence[name] = self.save(name, {})
        self.evidence['training_result'] = self.save('training_result', dict(exit_code=0))
        self.evidence['training_runtime'] = self.save('training_runtime', dict(status='completed',
            optimizer_steps=46, epochs_completed=1, validation_gate_passed=True))
        self.evidence['comparison_summary'] = self.save('comparison_summary', dict(denominator=3648,retrained_correct=3077))
        self.evidence['pool'] = self.save('pool', self.pool)
        self.evidence['source_equivalence'] = self.save('source_equivalence', dict(sources={}))
        rounds = {}
        for n,count in ((1,216),(2,500),(3,500)):
            fields = (585,1287,1205)[n-1]
            report = dict(images=count,metrics=dict(field_total=3*count,field_correct=fields,
                labels_without_predictions=[],submission_format=dict(all_rows_compliant=True)),
                runtime=dict(status='completed',failures=[]),complete=True,protected_field_losses=1,all_targets_met=False)
            self.evidence[f'round_{n}_report'] = self.save(f'round_{n}', report)
            self.evidence[f'round_{n}_execution_lock'] = self.save(f'lock_{n}', dict(model={}))
            rounds[str(n)] = dict(field_correct=fields,field_total=3*count,protected_field_losses=1,all_targets_met=False)
        review = self.save('review', dict(field_correct=3077,evidence=self.evidence,rounds=rounds))
        self.auth = dict(actor='user',action='adopt_model_close_group',round=2,rounds=[2,3],
            instruction='Adopt this model and close rounds 2 and 3.',source_reference='test user message',
            approved_at='2026-09-15T00:00:00+09:00',model={},code={},report_sha256=review['sha256'],
            scope='adopt_retrained_close_23_prepare_45',accept_recorded_regressions=True,
            accept_target_shortfall=True,start_next_tests=False)
        self.value = dict(status='complete',completion_kind='explicit_user_adoption',rounds=[2,3],
            performance_targets_met=False,evaluation=review,approval=self.save('approval',self.auth),
            weights=str(self.root),code_root=str(self.root),model={},code={},
            training_release=self.save('carry',dict(self.pool,optimizer_execution_authorized=False)))
        self.save('group_roles',{})
        self.addCleanup(patch.stopall)
        patch('scripts.grouped_user_adoption.model_lock',return_value={}).start()
        patch('scripts.grouped_rounds.source_lock',return_value={}).start()

    def save(self,name,value):
        p=self.root/(name+'.json');p.write_text(json.dumps(value),encoding='utf-8')
        return dict(path=str(p),sha256=digest(p))

    def test_explicit_adoption_preserves_failed_targets(self):
        self.assertEqual(validate_user_adoption(self.root,self.value)['field_correct'],3077)
        self.assertFalse(self.value['performance_targets_met'])

    def test_no_silent_regression_waiver(self):
        self.auth['accept_recorded_regressions']=False
        self.value['approval']=self.save('approval',self.auth)
        with self.assertRaises(ValueError):validate_user_adoption(self.root,self.value)

    def test_cannot_claim_performance_pass(self):
        self.value['performance_targets_met']=True
        with self.assertRaises(ValueError):validate_user_adoption(self.root,self.value)

    def test_tampered_training_evidence_rejected(self):
        self.save('training_runtime',dict(status='completed',optimizer_steps=0))
        with self.assertRaises(ValueError):validate_user_adoption(self.root,self.value)

    def test_does_not_authorize_future_tests(self):
        self.auth['start_next_tests']=True
        self.value['approval']=self.save('approval',self.auth)
        with self.assertRaises(ValueError):validate_user_adoption(self.root,self.value)

    def test_wrong_round_rejected(self):
        self.value['rounds']=[4,5]
        with self.assertRaises(ValueError):validate_user_adoption(self.root,self.value)
