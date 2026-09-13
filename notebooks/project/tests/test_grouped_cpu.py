import unittest
from pathlib import Path
from scripts.grouped_cpu import validate_topology
from scripts.grouped_rounds import qualification_dir


class GroupedCpuTests(unittest.TestCase):
    def fixture(self):
        return [dict(group=0, logical_processor=i, core_index=i, efficiency_class=1 if i < 4 else 0)
                for i in range(8)]

    def test_qualified_topology(self):
        self.assertEqual(validate_topology(self.fixture())['p_cores'], [0,1,2,3])

    def test_topology_drift_rejected(self):
        for field, value in [('group',1), ('logical_processor',1), ('core_index',1), ('efficiency_class',0)]:
            rows = self.fixture()
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_topology(rows)
        with self.assertRaises(ValueError):
            validate_topology(self.fixture()[:4])

    def test_old_qualification_not_reused(self):
        path = qualification_dir(Path('workspace'), 2)
        self.assertEqual(path.name, 'qualification_02_mixed-p2e2-v1')
        self.assertNotEqual(path.name, 'qualification_02')
