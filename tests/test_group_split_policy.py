import tempfile
import unittest
from pathlib import Path
from scripts.prepare_group_splits import assign_folds,leakage
from scripts.training_release_gate import validate_partition,require_release

class GroupSplitTests(unittest.TestCase):
    def rows(self):
        return [dict(image_id=str(i),group_id=str(i//2),image_sha256=str(i),seen_in_development=i<6,
            date_type='full' if i%2 else 'partial',difficulty='easy',source_dataset='product') for i in range(30)]
    def test_repeatable_and_exposure_group_closure(self):
        rows=self.rows();rows[7]['seen_in_development']=True
        a=assign_folds(rows);self.assertEqual(a,assign_folds(list(reversed(rows))));leakage(rows,a)
        self.assertNotEqual(a['6'],5)
    def test_group_and_hash_leaks_rejected(self):
        rows=self.rows();a=assign_folds(rows);a['0']=1;a['1']=2
        with self.assertRaises(ValueError):leakage(rows,a)
        rows=[dict(image_id='a',group_id='a',image_sha256='same',seen_in_development=False),dict(image_id='b',group_id='b',image_sha256='same',seen_in_development=False)]
        with self.assertRaises(ValueError):leakage(rows,{'a':1,'b':5})
    def test_runtime_future_and_group_leakage(self):
        rows=[dict(image_id=str(i),group_id=str(i),image_sha256=str(i),fold=i) for i in range(1,6)]
        validate_partition(rows,['1'],['2'],2)
        with self.assertRaises(ValueError):validate_partition(rows,['1'],['5'],4)
        rows[4]['group_id']='1'
        with self.assertRaises(ValueError):validate_partition(rows,['1'],['2'],2)
    def test_no_release_blocks_training(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):require_release(Path(directory),1,Path('train'),Path('validation'))

if __name__=='__main__':unittest.main()
