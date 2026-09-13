import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch, Mock
from scripts.grouped_plan import round_for, members, previous_group, cpu_set, GROUPS
from scripts.grouped_rounds import report_approval, exclusive, require_pair_scored, evidence, prior_completion
from scripts.grouped_training import validate_samples, create_training_release, validate_training, training_bindings, integration_review
from scripts.grouped_review import evaluation_gate
from scripts.prepare_sequential_rounds import write, digest, csv_write
from scripts.operating_environment import cpu_list
from scripts.run_round_groups import status, worker, already_finished


class GroupedPlanTests(unittest.TestCase):
    def test_all_images_once_and_new_boundaries(self):
        counts = Counter(round_for(f'AMLT{i:06d}') for i in range(1,3717))
        self.assertEqual(counts, {1:216, **{n:500 for n in range(2,9)}})
        for i,n in [(216,1),(217,2),(263,2),(352,2),(353,3),(852,3),(853,4),
                    (1352,4),(1353,5),(1852,5),(1853,6),(2352,6),(2353,7),
                    (2852,7),(2853,8),(3352,8),(3353,2),(3716,2)]:
            self.assertEqual(round_for(f'AMLT{i:06d}'),n)
        self.assertEqual(round_for('BMLT003716'),2)

    def test_dependencies_are_between_groups_not_peer_rounds(self):
        self.assertEqual(previous_group(2),(1,))
        self.assertEqual(previous_group(3),(1,))
        self.assertEqual(previous_group(4),(2,3))
        self.assertEqual(previous_group(5),(2,3))
        self.assertEqual(previous_group(8),(6,7))
        self.assertEqual(len(GROUPS),5)

    def test_cpu_assignments_do_not_overlap(self):
        for a,b in ((2,3),(4,5),(6,7)):
            self.assertFalse(set(cpu_set(a)) & set(cpu_set(b)))
            self.assertEqual(set(cpu_set(a)+cpu_set(b)),set(range(8)))
        self.assertEqual(cpu_set(1),[0,1,2,3])
        self.assertEqual(cpu_set(8),[0,1,2,3])

    def test_invalid_round_and_cpu_set(self):
        for value in (0,9,-1):
            with self.assertRaises(ValueError): members(value)
        for value in ('0,1,2','0,1,2,2','0,1,2,64','-1,0,1,2'):
            with self.assertRaises(ValueError): cpu_list(value)
        self.assertEqual(cpu_list('4,5,6,7'),[4,5,6,7])


class GroupedApprovalTests(unittest.TestCase):
    def test_feedback_report_hash_and_temporal_order_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); report=root/'report.json'; approval=root/'approval.json'
            write(report,dict(created_at='2026-09-13T10:00:00+09:00'))
            value=dict(actor='user',action='train',round=2,instruction='Synthetic fixture',
                       source_reference='test fixture only',approved_at='2026-09-13T10:01:00+09:00',
                       feedback='Synthetic no further comments',report_sha256=digest(report))
            write(approval,value)
            self.assertEqual(report_approval(approval,'train',2,report,{}),value)
            for fields in ({'feedback':''},{'feedback':None},{'approved_at':'2026-09-13T09:59:59+09:00'},
                           {'report_sha256':'wrong'},{'round':3},{'actor':'assistant'}):
                with self.subTest(fields=fields):
                    write(approval,{**value,**fields})
                    with self.assertRaises(ValueError): report_approval(approval,'train',2,report,{})

    def test_training_waits_for_both_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            for n in (2,3):
                dest=base/'rounds'/f'round_{n:02d}'
                write(dest/'report.json',dict(created_at='2026-09-13T10:00:00+09:00'))
                write(dest/'state.json',dict(status='awaiting_user_review',report=evidence(dest/'report.json')))
            require_pair_scored(base,2)
            dest=base/'rounds/round_03'
            value=json.loads((dest/'state.json').read_text())
            write(dest/'state.json',{**value,'status':'inference_running'})
            with self.assertRaises(ValueError): require_pair_scored(base,2)

    def test_shared_execution_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lock'
            with exclusive(path):
                with self.assertRaises(FileExistsError):
                    with exclusive(path): pass
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())

    def test_worker_cannot_be_started_outside_coordinator(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'job.json';write(path,dict(parent_pid=-999,rounds=[2,3]))
            with self.assertRaises(ValueError): worker(path,2)

    def test_previous_group_needs_completion_not_only_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError): prior_completion(Path(folder),4)

    def test_completed_peer_is_skipped_but_interrupted_output_is_not(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder); dest=base/'rounds/round_02'; dest.mkdir(parents=True)
            self.assertFalse(already_finished(base,2,'test'))
            write(dest/'runtime.json',dict(status='completed'))
            write(dest/'manifest.json',dict(round=2))
            write(dest/'state.json',dict(status='inference_complete',runtime=evidence(dest/'runtime.json'),
                  manifest=evidence(dest/'manifest.json'),predictions=None))
            self.assertTrue(already_finished(base,2,'test'))
            self.assertFalse(already_finished(base,3,'test'))
            write(dest/'runtime.json',dict(status='changed'))
            with self.assertRaises(ValueError): already_finished(base,2,'test')


class OriginalCropTests(unittest.TestCase):
    def fixture(self, root):
        test=root/'테스트용데이터';test.mkdir()
        augmented=test/'AMLT000853.jpg';augmented.write_bytes(b'augmented data')
        crop=root/'crop.png';crop.write_bytes(b'approved original crop')
        csv_write(root/'test_to_original_mapping.csv',
                  [dict(test_sha256=digest(augmented),augmented='true')],['test_sha256','augmented'])
        sample=dict(image_id='AMLC000001',crop_path=str(crop),crop_sha256=digest(crop),
                    record_sha256='record',transcription='2027.01.01')
        return {'AMLC000001':dict(annotation_sha256='record')},sample,augmented

    def test_only_approved_original_crops_are_admitted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);admitted,sample,_=self.fixture(root)
            with patch('scripts.grouped_training.ROOT',root):
                self.assertEqual(validate_samples(root,admitted,[sample,sample]),[sample])
                self.assertEqual(validate_samples(root,{},[sample]),[])
                with self.assertRaises(ValueError):validate_samples(root,admitted,[{**sample,'record_sha256':'wrong'}])

    def test_augmented_bytes_cannot_be_disguised_by_a_different_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);admitted,sample,augmented=self.fixture(root)
            copied=root/'fake_crop.png';copied.write_bytes(augmented.read_bytes())
            with patch('scripts.grouped_training.ROOT',root):
                with self.assertRaises(ValueError):validate_samples(root,admitted,[{**sample,'crop_path':str(copied),'crop_sha256':digest(copied)}])
                with self.assertRaises(ValueError):validate_samples(root,admitted,[{**sample,'crop_path':str(augmented),'crop_sha256':digest(augmented)}])

    def test_changed_crop_and_conflicting_transcriptions_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);admitted,sample,_=self.fixture(root)
            with patch('scripts.grouped_training.ROOT',root):
                with self.assertRaises(ValueError):validate_samples(root,admitted,[sample,{**sample,'transcription':'2028.01.01'}])
                Path(sample['crop_path']).write_bytes(b'changed')
                with self.assertRaises(ValueError):validate_samples(root,admitted,[sample])


class GroupedCompletionTests(unittest.TestCase):
    def report(self, errors=(), state='completed', compliant=True):
        return dict(ids=['a','b'],runtime=dict(status=state,failures=[]),
                    metrics=dict(errors=[dict(image_id=i) for i in errors],submission_format=dict(all_rows_compliant=compliant)))

    def test_better_total_does_not_erase_protected_regression(self):
        gate=evaluation_gate([self.report(errors=['a'])],['a'])
        self.assertEqual(gate['regressions'],['a']);self.assertFalse(gate['eligible'])

    def test_failure_and_format_are_not_success(self):
        self.assertFalse(evaluation_gate([self.report(state='timeout')],[])['eligible'])
        self.assertFalse(evaluation_gate([self.report(compliant=False)],[])['eligible'])
        self.assertTrue(evaluation_gate([self.report()],['a'])['eligible'])

    def test_status_does_not_create_workspace_or_claim_round1_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'missing'
            result=status(path)
            self.assertEqual(result['total_stages'],5)
            self.assertEqual(result['current_stage'],1)
            self.assertEqual(result['current_rounds'],[1])
            self.assertFalse(path.exists())


class TrainingReleaseLifecycleTests(unittest.TestCase):
    def test_pair_releases_share_roles_and_integration_requires_separate_review(self):
        from contextlib import ExitStack
        import yaml
        with tempfile.TemporaryDirectory() as folder, ExitStack() as patches:
            root=Path(folder); base=root/'workspace';base.mkdir()
            for name in ('predict.ipynb','requirements.txt','download_weights.sh'):(root/name).write_text('fixture')
            (root/'notebooks/project').mkdir(parents=True)
            original_dir=root/'학습대상데이터';original_dir.mkdir()
            (root/'테스트용데이터').mkdir()
            checkpoint=root/'initial.pdparams';checkpoint.write_bytes(b'initial fixture')
            dictionary=root/'dict.txt';dictionary.write_text('0\n1')
            config=root/'config.yml'
            config.write_text(yaml.safe_dump(dict(Global=dict(epoch_num=1),Train=dict(dataset={},loader={}),
                                                      Eval=dict(dataset={},loader={}))),encoding='utf-8')
            rows,samples,groups=[],[],{}
            for i in range(20):
                n=2 if i<10 else 3;oid=f'AMLC{i:06d}'
                original=original_dir/(oid+'.jpg');original.write_bytes(f'original{i}'.encode())
                annotation=root/(oid+'.json')
                write(annotation,dict(review=dict(status='approved'),image_sha256=digest(original)))
                crop=root/(oid+'.png');crop.write_bytes(f'crop{i}'.encode())
                gid=f'g{i if i!=10 else 0}'
                groups[oid]=dict(group_id=gid,verified=True,evidence='Synthetic provenance')
                rows.append(dict(test_id=f'AMLT{i:06d}',round=n,original_id=oid,original_path=str(original),
                    original_sha256=digest(original),test_sha256=digest(original),annotation_path=str(annotation),
                    annotation_sha256=digest(annotation),augmented='false'))
                samples.append(dict(image_id=oid,crop_path=str(crop),crop_sha256=digest(crop),
                                    record_sha256=digest(annotation),transcription='2027.01.01'))
            csv_write(base/'test_to_original_mapping.csv',rows,list(rows[0]))
            group_path=root/'groups.json';write(group_path,groups)
            pool=root/'pool.jsonl';pool.write_text('\n'.join(json.dumps(s) for s in samples),encoding='utf-8')
            for module in ('scripts.grouped_training','scripts.sequential_rounds'):
                patches.enter_context(patch(module+'.ROOT',root))
            patches.enter_context(patch('scripts.grouped_training.verify'))
            patches.enter_context(patch('scripts.grouped_training.prior_completion',return_value=None))
            patches.enter_context(patch('scripts.grouped_training.execution_release',return_value=dict(code={},model={})))
            patches.enter_context(patch('scripts.train_recognition_cpu.CHECKPOINT',checkpoint))
            patches.enter_context(patch('scripts.train_recognition_cpu.CHECKPOINT_SHA256',digest(checkpoint)))
            patches.enter_context(patch('scripts.train_recognition_cpu.DICTIONARY',dictionary))
            for n in (2,3):
                dest=base/'rounds'/f'round_{n:02d}'
                report=dest/'initial_report.json'
                write(report,dict(created_at='2026-09-13T10:00:00+09:00',images=500,metrics=dict(exact_match_rate=.9),
                                  runtime=dict(total_elapsed_seconds=100),mean_seconds=.2,time_target_seconds=1500))
                write(dest/'state.json',dict(status='awaiting_user_review',report=evidence(report)))
                csv_write(base/f'test_round_{n:02d}.csv',[dict(image_id='fixture',image_path='unused')],['image_id','image_path'])
            releases=[]
            for n in (2,3):
                dest=base/'rounds'/f'round_{n:02d}';ap=root/f'approval{n}.json'
                write(ap,dict(actor='user',action='train',round=n,instruction='Synthetic test fixture',
                    source_reference='fixture, not real authorization',approved_at='2026-09-13T10:01:00+09:00',
                    feedback='Synthetic review',report_sha256=digest(dest/'initial_report.json'),
                    **training_bindings(base,n,config,group_path,pool)))
                result=create_training_release(base,n,ap,config,group_path,pool)
                self.assertEqual(len(result['admitted']),10)
                self.assertEqual(len(validate_training(dest/'training_release.json')['samples']),10)
                releases.append(result)
                write(dest/'selection.json',dict(epoch=1))
                write(dest/'candidate_complete.json',dict(selection=evidence(dest/'selection.json')))
                write(dest/'evaluation/review.json',dict(synthetic_fixture=True,round=n))
                state=json.loads((dest/'state.json').read_text())
                write(dest/'state.json',{**state,'status':'candidate_complete','candidate':evidence(dest/'candidate_complete.json')})
            self.assertEqual(releases[0]['group_roles']['g0'],releases[1]['group_roles']['g0'])
            with self.assertRaises(ValueError):create_training_release(base,2,root/'missing.json',config,integration=True)
            review=integration_review(base,2)
            review_path=base/'groups/group_02_03/integration/review.json'
            ap=root/'integration_approval.json'
            write(ap,dict(actor='user',action='train_integration',round=2,instruction='Synthetic integration fixture',
                source_reference='fixture only',approved_at='2099-01-01T00:00:00+09:00',feedback='Synthetic feedback',
                report_sha256=digest(review_path),rounds=[2,3],round_reports=review['round_reports'],
                input_releases=review['input_releases'],**training_bindings(base,2,config)))
            result=create_training_release(base,2,ap,config,integration=True)
            self.assertEqual(len(result['admitted']),20)
            self.assertEqual(len(result['samples']),20)
            self.assertTrue(validate_training(base/'groups/group_02_03/integration/training_release.json')['integration'])


if __name__=='__main__': unittest.main()
