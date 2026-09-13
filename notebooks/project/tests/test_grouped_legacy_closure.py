import copy
import tempfile
import unittest
import sys
from pathlib import Path
from scripts.prepare_sequential_rounds import write, digest, read
from scripts.grouped_rounds import evidence
from scripts.prepare_grouped_stage2 import canonical, validate_legacy_completion
from unittest.mock import Mock, patch
from scripts.run_round_groups import is_coordinator_child
from scripts.prepare_sequential_rounds import ROOT


class LegacyClosureTests(unittest.TestCase):
    def fixture(self, root):
        code = {'predict.ipynb': 'notebook', 'notebooks/project/src/pipeline.py': 'pipeline'}
        model = {'inference.pdiparams': 'weights'}
        protected = [f'AMLT{i:06d}' for i in range(1, 205)]
        closure = dict(status='closed_by_user', selected_baseline='remediation_12',
            round1_testing_ended=True, round1_machine_learning_ended=True, model_manifest_sha256=canonical(model))
        carry = dict(admitted={'original': {'group_id': 'g'}}, group_roles={'g': 'inner_validation'},
                     optimizer_execution_authorized=False)
        write(root/'closure.json', closure)
        write(root/'runtime.json', dict(code=code))
        write(root/'legacy_release.json', carry)
        write(root/'group_roles.json', carry['group_roles'])
        write(root/'carry.json', carry)
        write(root/'fixture.json', dict(test_fixture_only=True))
        names = ['comparison', 'predictions', 'trace', 'initial_report', 'legacy_approval', 'legacy_review',
                 'legacy_pool', 'legacy_groups', 'training_summary', 'selected_checkpoint',
                 'selected_parameters', 'optimizer_train', 'inner_validation']
        names += [f'{a}_{n}' for a in ('A', 'B') for n in ('runtime.json', 'selected_checkpoint.json',
                  'epoch_001.pdparams', 'effective_config.yml', 'validation_001.json', 'export_equivalence.json', 'train.log')]
        ev = {k:evidence(root/'fixture.json') for k in names}
        ev.update(closure=evidence(root/'closure.json'), development_runtime=evidence(root/'runtime.json'),
                  legacy_training_release=evidence(root/'legacy_release.json'))
        history = dict(evidence=ev, protected_correct=protected, reviewed_status_sha256='reviewed')
        write(root/'review.json', history)
        write(root/'approval.json', dict(actor='user', action='adopt_round1_closure', round=1,
            instruction='Synthetic preparation instruction', source_reference='test fixture only',
            approved_at='2026-09-13T21:00:00+09:00', scope='close_legacy_round1_and_prepare_stage2_only',
            closure_sha256=digest(root/'closure.json'), reviewed_status_sha256='reviewed', code=code, model=model))
        return dict(completion_kind='legacy_user_closure', rounds=[1], code=code, model=model,
            protected_correct=protected, approval=evidence(root/'approval.json'),
            evaluation=evidence(root/'review.json'), training_release=evidence(root/'carry.json'))

    def test_closed_history_can_be_carried_without_claiming_a_new_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); value=self.fixture(root)
            self.assertEqual(len(validate_legacy_completion(root,value)['protected_correct']),204)

    def test_not_a_bypass_for_other_rounds_or_changed_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); value=self.fixture(root)
            for field, replacement in [('rounds',[2,3]), ('model',{'inference.pdiparams':'other'}),
                                        ('code',{'predict.ipynb':'changed'}), ('protected_correct',[])]:
                bad=copy.deepcopy(value);bad[field]=replacement
                with self.subTest(field=field), self.assertRaises(ValueError):validate_legacy_completion(root,bad)

    def test_missing_training_evidence_and_changed_history_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); value=self.fixture(root)
            history=read(root/'review.json');del history['evidence']['A_epoch_001.pdparams']
            write(root/'review.json',history);value['evaluation']=evidence(root/'review.json')
            with self.assertRaises(ValueError):validate_legacy_completion(root,value)
            value=self.fixture(root);write(root/'closure.json',dict(status='not_closed'))
            with self.assertRaises(ValueError):validate_legacy_completion(root,value)

    def test_preparation_does_not_authorize_optimizer_or_change_group_role(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);value=self.fixture(root)
            write(root/'group_roles.json',{'g':'optimizer_train'})
            with self.assertRaises(ValueError):validate_legacy_completion(root,value)
            value=self.fixture(root);carry=read(root/'carry.json');carry['optimizer_execution_authorized']=True
            write(root/'carry.json',carry);value['training_release']=evidence(root/'carry.json')
            with self.assertRaises(ValueError):validate_legacy_completion(root,value)

    def test_wrong_transition_approval_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);value=self.fixture(root)
            approved=read(root/'approval.json');approved['action']='start_test'
            write(root/'approval.json',approved);value['approval']=evidence(root/'approval.json')
            with self.assertRaises(ValueError):validate_legacy_completion(root,value)


class WindowsWorkerParentTests(unittest.TestCase):
    def test_only_the_exact_venv_redirector_is_accepted(self):
        job=dict(parent_pid=123,base=str(ROOT),rounds=[2,3])
        job_path=ROOT/'fixture_job.json'
        launcher=Mock()
        launcher.ppid.return_value=123
        launcher.exe.return_value=sys.executable
        expected=[sys.executable,str(ROOT/'notebooks/project/run.py'),'scripts.run_round_groups','_worker',
                  '--workspace',str(ROOT.resolve()),'--round','2','--job',str(job_path)]
        launcher.cmdline.return_value=expected
        with patch('scripts.run_round_groups.os.getppid',return_value=456), patch('psutil.Process',return_value=launcher):
            self.assertTrue(is_coordinator_child(job,job_path,2))
            launcher.ppid.return_value=999
            self.assertFalse(is_coordinator_child(job,job_path,2))
            launcher.ppid.return_value=123
            launcher.cmdline.return_value=expected[:-1]+['unrelated_job.json']
            self.assertFalse(is_coordinator_child(job,job_path,2))


if __name__ == '__main__': unittest.main()
