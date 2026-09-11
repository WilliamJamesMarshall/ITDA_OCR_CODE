import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.manual_validation_guard import CSV_REL, INSPECT_REL, LOCK_REL, WORKBOOK_REL, check_repository


ROOT = Path(__file__).parents[1]


class ManualValidationGuardTest(unittest.TestCase):
    def test_repository_artifacts_match_the_lock(self):
        self.assertEqual(check_repository(ROOT), [])

    def test_stale_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            for relative_path in (WORKBOOK_REL, CSV_REL, INSPECT_REL, LOCK_REL):
                target = temporary_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative_path, target)
            with (temporary_root / CSV_REL).open("a", encoding="utf-8") as output:
                output.write("tampered\n")
            self.assertIn(
                f"stale synchronized file: {CSV_REL.as_posix()}",
                check_repository(temporary_root),
            )


if __name__ == "__main__":
    unittest.main()
