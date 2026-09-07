import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.date_extraction import OCRLine
from src.pipeline import OUTPUT_COLUMNS, PipelineConfig, discover_images, run_pipeline


class FakeBackend:
    def recognize(self, image, *, detector, variant):
        return [
            OCRLine(
                "소비기한 2026.05.29까지",
                0.99,
                (0, 0, 300, 40),
                f"fake-{detector}",
                variant,
            )
        ]


class PipelineContractTest(unittest.TestCase):
    def test_discovery_filters_extensions_and_preserves_stems(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("0001.JPG", "alpha.jpeg", "한글.PNG"):
                Image.new("RGB", (16, 16), "white").save(root / name)
            (root / "notes.txt").write_text("not an image", encoding="utf-8")
            self.assertEqual(
                [path.stem for path in discover_images(root)], ["0001", "alpha", "한글"]
            )

    def test_duplicate_stems_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (16, 16), "white").save(root / "same.jpg")
            Image.new("RGB", (16, 16), "white").save(root / "same.png")
            with self.assertRaisesRegex(ValueError, "Duplicate image_id"):
                discover_images(root)

    def test_empty_input_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "No supported images"),
        ):
            discover_images(directory)

    def test_pipeline_writes_exact_submission_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_dir = root / "images"
            image_dir.mkdir()
            Image.new("RGB", (32, 24), "white").save(image_dir / "000001.jpg")
            output = root / "nested" / "submission.csv"
            config = PipelineConfig(
                enable_clahe=False,
                enable_recovery_fallback=False,
                enable_rotation_fallback=False,
                enable_tile_fallback=False,
                progress_every=1,
            )
            summary = run_pipeline(
                image_dir, output, config=config, backend=FakeBackend()
            )
            with output.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
                self.assertEqual(source.seek(0), 0)
            self.assertEqual(list(rows[0]), OUTPUT_COLUMNS)
            self.assertEqual(
                rows[0],
                {
                    "image_id": "000001",
                    "year": "2026",
                    "month": "05",
                    "day": "29",
                    "final_date": "2026-05-29",
                },
            )
            self.assertEqual(summary["images"], 1)
            self.assertEqual(summary["failures"], [])

    def test_corrupt_image_becomes_none_without_aborting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_dir = root / "images"
            image_dir.mkdir()
            (image_dir / "broken.jpg").write_bytes(b"not an image")
            Image.new("RGB", (32, 24), "white").save(image_dir / "valid.jpg")
            output = root / "submission.csv"
            config = PipelineConfig(
                enable_clahe=False,
                enable_recovery_fallback=False,
                enable_rotation_fallback=False,
                enable_tile_fallback=False,
                progress_every=0,
            )
            summary = run_pipeline(
                image_dir, output, config=config, backend=FakeBackend()
            )
            with output.open(encoding="utf-8", newline="") as source:
                rows = {row["image_id"]: row for row in csv.DictReader(source)}
            self.assertEqual(rows["broken"]["final_date"], "NONE")
            self.assertEqual(rows["valid"]["final_date"], "2026-05-29")
            self.assertEqual(len(summary["failures"]), 1)

    def test_notebook_keeps_environment_contract(self):
        notebook = json.loads(
            (Path(__file__).parents[1] / "predict.ipynb").read_text(encoding="utf-8")
        )
        first_source = "".join(notebook["cells"][0]["source"])
        all_source = "\n".join(
            "".join(cell.get("source", [])) for cell in notebook["cells"]
        )
        self.assertIn('os.environ.get("ITDA_INPUT_DIR"', first_source)
        self.assertIn('os.environ.get("ITDA_OUTPUT_PATH"', first_source)
        self.assertNotIn("input(", all_source)
        self.assertIn("run_pipeline(INPUT_DIR, OUTPUT_PATH)", all_source)


if __name__ == "__main__":
    unittest.main()
