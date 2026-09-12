import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.prepare_sequential_rounds import round_for, write, digest
from scripts.sequential_rounds import approval, cumulative_partition, build_admission, checked_evidence, require_training_release
from scripts.train_sequential_cpu import PolicyMetric

class SequentialRoundTests(unittest.TestCase):
    def test_all_round_boundaries(self):
        counts = [0] * 8
        for n in range(1, 3717): counts[round_for(f'AMLT{n:06d}') - 1] += 1
        self.assertEqual(counts, [216] + [500] * 7)
        self.assertEqual(round_for('BMLT003716'), 8)

    def test_invalid_round_ids(self):
        for value in ['AMLC000001', 'AMLT000000', 'BMLT003717', 'AMLT1']:
            with self.assertRaises(ValueError): round_for(value)

    def test_partition_is_permanent_and_order_independent(self):
        rows = [dict(original_id=str(i), group_id=str(i // 2)) for i in range(100)]
        first = cumulative_partition(rows, {})
        self.assertEqual(first, cumulative_partition(list(reversed(rows)), {}))
        self.assertEqual(list(first.values()).count('inner_validation'), 5)
        later = cumulative_partition(rows + [dict(original_id='new', group_id='new')], first)
        self.assertTrue(all(later[g] == role for g, role in first.items()))

    def test_invalid_permanent_role_rejected(self):
        with self.assertRaises(ValueError): cumulative_partition([], {'g': 'test'})

    def test_unresolved_mapping_blocks_admission(self):
        with self.assertRaises(ValueError): build_admission([{'round': '1', 'original_id': ''}], 1, {}, {})

    def test_unreviewed_group_blocks_admission(self):
        with self.assertRaises(ValueError): build_admission([{'round': '1', 'original_id': 'AMLC000001'}], 1, {}, {})

    def test_approval_requires_actual_user_and_exact_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'approval.json'
            value = dict(actor='user', action='train', round=1, instruction='회차 1 학습 승인',
                         source_reference='synthetic test fixture, not real approval',
                         approved_at='2026-09-12T10:00:00+09:00', report_sha256='abc')
            write(path, value)
            self.assertEqual(approval(path, 'train', 1, {'report_sha256': 'abc'}), value)
            for action, number, bindings in [('train', 2, {}), ('start_test', 1, {}), ('train', 1, {'report_sha256': 'changed'})]:
                with self.assertRaises(ValueError): approval(path, action, number, bindings)
            for key, replacement in [('actor', 'assistant'), ('instruction', ''), ('source_reference', ''),
                                     ('approved_at', '2026-09-12T10:00:00')]:
                write(path, {**value, key: replacement})
                with self.assertRaises(ValueError): approval(path, 'train', 1, {})

    def test_evidence_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            write(path, {'accuracy': .9})
            record = {'path': str(path), 'sha256': digest(path)}
            checked_evidence(record)
            write(path, {'accuracy': .95})
            with self.assertRaises(ValueError): checked_evidence(record)

    def test_missing_release_blocks_training(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((ValueError, FileNotFoundError)):
                require_training_release(Path(directory), 8, Path('train'), Path('validation'))

    def test_policy_metric_uses_full_text_not_date_labels(self):
        metric = PolicyMetric()
        metric(([('2027.07.08', .9), ('ABC', .9)], [('2027-07-08', 1), ('abc', 1)]))
        result = metric.get_metric()
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['string_exact_match_rate'], .5)
        self.assertGreater(result['micro_cer'], 0)

    def test_no_ninth_round(self):
        from scripts.sequential_rounds import round_dir
        with self.assertRaises(ValueError): round_dir(Path('.'), 9)

    def test_direct_training_adapter_cannot_bypass_approval(self):
        from scripts.train_sequential_cpu import main
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(KeyError): main()

    def test_windows_epoch_adapter_preserves_last_batch(self):
        from scripts.train_sequential_cpu import WindowsEpochLoader
        source = [[1, 2], [3, 4], [5]]
        loader = WindowsEpochLoader(source)
        consumed = [batch for index, batch in enumerate(loader) if index < len(loader) - 1]
        self.assertEqual(consumed, source)

    def test_score_is_separate_and_failure_report_is_retained(self):
        from scripts.prepare_sequential_rounds import csv_write
        from scripts.sequential_rounds import score, evidence
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            dest = base / 'rounds/round_01'
            dest.mkdir(parents=True)
            manifest = base / 'test_round_01.csv'
            csv_write(manifest, [{'image_id': 'AMLT000001', 'image_path': 'not-opened.jpg'}], ['image_id', 'image_path'])
            csv_write(base / 'test_to_original_mapping.csv',
                      [dict(test_id='AMLT000001', original_id='AMLC000001', augmented='false',
                            group_id='g', group_verified='false', seen_in_development='true')],
                      ['test_id', 'original_id', 'augmented', 'group_id', 'group_verified', 'seen_in_development'])
            labels = base / 'labels.csv'
            csv_write(labels, [{'image_id': '000001', '정답 날짜': '2027-07-08', '라벨 상태': 'approved'}],
                      ['image_id', '정답 날짜', '라벨 상태'])
            write(dest / 'runtime.json', dict(status='failed', total_elapsed_seconds=10, images=1, failures=[]))
            state = dict(status='inference_running', manifest=evidence(manifest), runtime=evidence(dest / 'runtime.json'),
                         predictions=None, code={}, model={})
            write(dest / 'state.json', state)
            with self.assertRaises(ValueError): score(base, 1, labels)
            write(dest / 'state.json', {**state, 'status': 'inference_complete'})
            score(base, 1, labels)
            report = json.loads((dest / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['metrics']['exact_match_rate'], 0)
            self.assertFalse(report['time_target_met'])
            self.assertFalse(report['training_approved'])
            self.assertEqual(json.loads((dest / 'state.json').read_text(encoding='utf-8'))['status'], 'awaiting_user_review')

    def test_unverified_environment_blocks_formal_inference(self):
        from scripts.sequential_rounds import infer
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            write(base / 'manifest_lock.json', {})
            write(base / 'execution_readiness.json', {'formal_environment_verified': False})
            with self.assertRaisesRegex(ValueError, 'environment'):
                infer(base, 1, base / 'nonexistent-approval.json')

    def test_duplicate_original_is_admitted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / '학습대상데이터/AMLC000001.jpg'
            original.parent.mkdir()
            original.write_bytes(b'original fixture')
            annotation = root / 'annotation.json'
            write(annotation, {'review': {'status': 'approved'}, 'image_sha256': digest(original)})
            row = dict(round=1, original_id=original.stem, original_path=str(original),
                       original_sha256=digest(original), annotation_path=str(annotation), annotation_sha256=digest(annotation))
            groups = {original.stem: {'group_id': 'product', 'verified': True, 'evidence': 'synthetic fixture'}}
            with patch('scripts.sequential_rounds.ROOT', root):
                admitted = build_admission([row, row], 1, {}, groups)
                self.assertEqual(len(admitted), 1)
                self.assertEqual(build_admission([{**row, 'round': 2}], 2, admitted, groups), admitted)
                with self.assertRaises(ValueError):
                    build_admission([{**row, 'original_path': str(root / 'test.jpg')}], 1, {}, groups)

if __name__ == '__main__': unittest.main()
