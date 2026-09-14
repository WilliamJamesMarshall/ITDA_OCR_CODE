import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.grouped_plan import round_for, time_target_seconds, time_target_met
from scripts.grouped_rounds import original_inputs, labels_for, exclusive, inherited_execution
from scripts.grouped_training import validate_samples
from scripts.prepare_sequential_rounds import csv_write, digest, write


class OriginalPolicyTests(unittest.TestCase):
    def fixture(self, root):
        folder = root / '학습대상데이터'
        folder.mkdir()
        original = folder / 'BMLC002247.jpg'
        original.write_bytes(b'original image fixture')
        row = dict(test_id='BMLT003353', original_id=original.stem, original_path=str(original),
                   test_sha256=digest(original), original_sha256=digest(original), augmented='false')
        csv_write(root / 'test_to_original_mapping.csv', [row], list(row))
        return original, dict(image_id=row['test_id'], image_path=str(original)), row

    def test_invalid_or_augmented_id_cannot_assign_an_original_round(self):
        for i in ('AMLT000853', 'AMLC002247', 'BMLC002246', 'BMLC002611', 'AMLC000000'):
            with self.subTest(i=i), self.assertRaises(ValueError): round_for(i)

    def test_small_round_time_boundaries_and_incomplete_runs(self):
        for count, target in ((216, 691.2), (394, 1260.8), (500, 1600)):
            self.assertEqual(time_target_seconds(count), target)
            runtime = dict(status='completed', images=count, failures=[], total_elapsed_seconds=target)
            self.assertTrue(time_target_met(runtime, count))
            for fields in (dict(total_elapsed_seconds=target + .01), dict(images=count - 1),
                           dict(status='timeout'), dict(failures=[dict(image_id='failed')])):
                with self.subTest(count=count, fields=fields):
                    self.assertFalse(time_target_met({**runtime, **fields}, count))
        with self.assertRaises(ValueError): time_target_seconds(0)

    def test_input_can_keep_historical_alias_only_with_bound_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, row, _ = self.fixture(root)
            with patch('scripts.grouped_rounds.ROOT', root):
                self.assertEqual(original_inputs(root, [row]), [row])
                # Even byte-identical historical copies cannot supply new inference.
                copied = root / '테스트用.jpg'
                copied.write_bytes(original.read_bytes())
                with self.assertRaises(ValueError):
                    original_inputs(root, [{**row, 'image_path': str(copied)}])
                with self.assertRaises(ValueError): original_inputs(root, [row, row])
                original.write_bytes(b'changed original')
                with self.assertRaises(ValueError): original_inputs(root, [row])

    def test_augmented_mapping_is_rejected_even_inside_original_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _, row, mapping = self.fixture(root)
            mapping['augmented'] = 'true'
            csv_write(root / 'test_to_original_mapping.csv', [mapping], list(mapping))
            with patch('scripts.grouped_rounds.ROOT', root), self.assertRaises(ValueError):
                original_inputs(root, [row])

    def test_training_label_serial_is_not_historical_test_serial(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root)
            labels = {'002247': {'정답 날짜': '2026-01-01'}, '003353': {'정답 날짜': 'wrong'}}
            self.assertEqual(labels_for(root, ['BMLT003353'], labels)['BMLT003353'], labels['002247'])
            labels['BMLT003353'] = {'정답 날짜': 'alias label'}
            self.assertEqual(labels_for(root, ['BMLT003353'], labels)['BMLT003353'], labels['BMLT003353'])

    def test_excluded_derivative_bytes_stay_blocked_after_removal_from_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root)
            crop = root / 'renamed_crop.png'
            crop.write_bytes(b'excluded derivative')
            csv_write(root / 'excluded_derivatives.csv', [dict(test_sha256=digest(crop))], ['test_sha256'])
            sample = dict(image_id='BMLC002247', crop_path=str(crop), crop_sha256=digest(crop),
                          record_sha256='record', transcription='2026.01.01')
            with patch('scripts.grouped_training.ROOT', root), self.assertRaises(ValueError):
                validate_samples(root, {'BMLC002247': dict(annotation_sha256='record')}, [sample])

    def test_previous_workspace_execution_blocks_new_coordinator(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch('scripts.grouped_rounds.inherited_execution', return_value=[dict(pid=123)]):
                with self.assertRaisesRegex(ValueError, 'Previous workspace'):
                    with exclusive(root / 'locks/execution.lock'): pass
            self.assertFalse((root / 'locks/execution.lock').exists())

    def test_unknown_old_lock_is_reported_without_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            previous = root / 'old'
            write(root / 'plan.json', dict(previous_workspace=str(previous)))
            write(previous / 'locks/execution.lock', dict(unreadable_owner=True))
            self.assertEqual(len(inherited_execution(root)), 1)
            self.assertTrue((previous / 'locks/execution.lock').exists())


if __name__ == '__main__': unittest.main()
