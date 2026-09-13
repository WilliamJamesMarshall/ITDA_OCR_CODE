import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.restart_grouped_tests import prepare, check, check_submission_gate
from scripts.grouped_rounds import evidence
from scripts.prepare_sequential_rounds import write


class RestartAuthorizationTests(unittest.TestCase):
    def test_non_user_or_wrong_scope_is_rejected(self):
        for value in ({}, {'actor':'assistant','action':'restart_tests','rounds':[2,3]},
                      {'actor':'user','action':'train','rounds':[2,3]},
                      {'actor':'user','action':'restart_tests','rounds':[4,5]}):
            with tempfile.TemporaryDirectory() as folder, patch('scripts.restart_grouped_tests.preflight',return_value={}):
                root=Path(folder)
                write(root/'authorization.json',value)
                with self.assertRaises(ValueError): check(root)

    def test_preparation_never_overwrites_existing_attempt(self):
        with tempfile.TemporaryDirectory() as folder, patch('scripts.restart_grouped_tests.preflight',return_value={}):
            with self.assertRaises(FileExistsError): prepare(Path(folder),'fixture','synthetic fixture')

    def test_submission_gate_is_required_and_rejects_failure_or_stale_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root/'development.json', dict(submission_validation_required=True))
            with self.assertRaises(ValueError): check_submission_gate(root, {})
            write(root/'input.json', dict(synthetic=True))
            code = {'predict.ipynb':'synthetic'}
            proof = dict(copies={n:dict(code=code) for n in ('2','3')})
            results = [dict(run=run, round=n, images=500,
                            predictions=[dict(image_id=str(i),final_date='NONE') for i in range(500)],
                            regressions=[], report_output_mismatches=[])
                       for run in ('retest-stage2-20260913','retest-stage2-corrected-20260914-v6') for n in (2,3)]
            gate = dict(code=code, results=results, gate_passed=True, input_evidence=[evidence(root/'input.json')])
            def bind():
                write(root/'gate.json',gate)
                write(root/'development.json',dict(submission_validation_required=True,
                                                  submission_gate=evidence(root/'gate.json')))
            bind()
            check_submission_gate(root,proof)
            gate['results'][0]['regressions'] = ['synthetic regression']
            bind()
            with self.assertRaises(ValueError): check_submission_gate(root,proof)
            gate['results'][0]['regressions'] = []
            gate['code'] = {'predict.ipynb':'changed'}
            bind()
            with self.assertRaises(ValueError): check_submission_gate(root,proof)
            gate['code'] = code
            bind()
            # Embedding is a separate contract, not implied by modular replay.
            write(root/'development.json',dict(submission_validation_required=True,
                  embedded_validation_required=True,submission_gate=evidence(root/'gate.json')))
            with self.assertRaises(ValueError): check_submission_gate(root,proof)
            write(root/'predict.ipynb',dict(synthetic=True))
            notebook = evidence(root/'predict.ipynb')
            code['predict.ipynb'] = notebook['sha256']
            gate['embedded_equivalence'] = dict(notebook=notebook, comparisons=2000,
                                               mismatches=[], project_imports_blocked=True)
            def bind_embedded():
                write(root/'gate.json',gate)
                write(root/'development.json',dict(submission_validation_required=True,
                      embedded_validation_required=True,submission_gate=evidence(root/'gate.json')))
            bind_embedded()
            check_submission_gate(root,proof)
            gate['embedded_equivalence']['mismatches'] = ['synthetic mismatch']
            bind_embedded()
            with self.assertRaises(ValueError): check_submission_gate(root,proof)
            gate['embedded_equivalence']['mismatches'] = []
            bind_embedded()
            write(root/'input.json',dict(synthetic='changed'))
            with self.assertRaises(ValueError): check_submission_gate(root,proof)
