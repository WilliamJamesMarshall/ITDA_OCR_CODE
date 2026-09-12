import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.manual_validation_guard import CSV_REL, INSPECT_REL, LOCK_REL, WORKBOOK_REL, check_repository
from scripts.manual_validation_guard import WorkbookState, HEADERS, csv_bytes, inspect_bytes, lock_bytes


ROOT = Path(__file__).parents[3]


class ManualValidationGuardTest(unittest.TestCase):
    def setUp(self):
        # Unit tests must not package actual answer workbooks into the submission.
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        state=WorkbookState([HEADERS,['1','NONE','NONE','True','manual','','','']],
                            [['']*8,['','','','=IF(B2=C2,"True","False")','','','','']],
                            'synthetic-workbook-hash','synthetic-content-hash')
        for relative,data in [(CSV_REL,csv_bytes(state)),(INSPECT_REL,inspect_bytes(state)),(LOCK_REL,lock_bytes(state))]:
            target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        mocked=patch('scripts.manual_validation_guard.read_workbook',return_value=state)
        mocked.start();self.addCleanup(mocked.stop)

    def test_repository_artifacts_match_the_lock(self):
        self.assertEqual(check_repository(self.root), [])

    def test_stale_csv_is_rejected(self):
        with (self.root / CSV_REL).open("a", encoding="utf-8") as output:
            output.write("tampered\n")
        self.assertIn(f"stale synchronized file: {CSV_REL.as_posix()}",check_repository(self.root))


if __name__ == "__main__":
    unittest.main()
