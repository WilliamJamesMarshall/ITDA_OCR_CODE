import csv
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from src.date_extraction import OCRLine, DateSelection
from src.pipeline import OUTPUT_COLUMNS, PipelineConfig, ImagePrediction, discover_images, run_pipeline, predict_image, _write_submission


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
    def test_writer_normalizes_legacy_missing_and_preserves_partial_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'out.csv'
            _write_submission(output, [
                {'image_id': 'empty', 'final_date': 'NONE-NONE-NONE'},
                {'image_id': 'partial', 'final_date': 'NONE-02-14'},
                {'image_id': 'month', 'final_date': '2026-09-NONE'},
            ])
            with output.open(encoding='utf-8', newline='') as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(list(rows[0]), OUTPUT_COLUMNS)
            self.assertEqual(rows[0]['final_date'], 'NONE')
            self.assertEqual([rows[0][key] for key in ('year', 'month', 'day')], ['NONE'] * 3)
            for row in rows[1:]:
                self.assertEqual('-'.join(row[key] for key in ('year', 'month', 'day')), row['final_date'])
            self.assertEqual(rows[1]['year'], 'NONE')
            self.assertEqual(rows[2]['day'], 'NONE')

    def test_no_date_is_canonical_in_output_and_checkpoint_without_failure(self):
        class EmptyBackend:
            def recognize(self, image, *, detector, variant):
                return []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (32, 24), 'white').save(root / 'empty.jpg')
            records = []
            summary = run_pipeline(root, root / 'out.csv', backend=EmptyBackend(),
                                   config=PipelineConfig(progress_every=0), on_image=records.append)
            self.assertEqual(summary['failures'], [])
            self.assertEqual(summary['predicted_none'], 1)
            self.assertEqual(records[0]['row']['final_date'], 'NONE')
            self.assertIsNone(records[0]['error'])

    def test_partial_detection_does_not_skip_recovery_or_tiles(self):
        class PartialBackend:
            def __init__(self):
                self.calls = []

            def recognize(self, image, *, detector, variant):
                self.calls.append((detector, variant))
                if variant == "tile-1":
                    return [OCRLine("EXP 2021.02.14", .99, (0,0,200,40), detector, variant)]
                return [OCRLine("EXP 02.14", .99, (0,0,200,40), detector, variant)]

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory)/'sample.jpg'
            Image.new('RGB',(400,400),'white').save(image)
            backend = PartialBackend()
            result = predict_image(image, backend, PipelineConfig(enable_rotation_fallback=True))
            self.assertEqual(result.final_date, '2021-02-14')
            self.assertIn(('recovery','original'), backend.calls)
            self.assertIn(('mobile','rot180'), backend.calls)
            self.assertIn(('mobile','tile-1'), backend.calls)

    def test_partial_submission_survives_all_passes(self):
        class PartialBackend:
            def recognize(self, image, *, detector, variant):
                return [OCRLine('EXP 2021.05', .99, (0,0,200,40), detector, variant)]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB',(400,400),'white').save(root/'sample.jpg')
            output = root/'result.csv'
            summary = run_pipeline(root, output, backend=PartialBackend(), config=PipelineConfig(progress_every=0))
            with output.open(encoding='utf-8', newline='') as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row, {'image_id':'sample','year':'2021','month':'05','day':'NONE','final_date':'2021-05-NONE'})
            self.assertEqual(summary['failures'], [])

    def test_serialization_error_is_an_image_failure_not_a_batch_abort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB',(24,24),'white').save(root/'sample.jpg')
            selection = DateSelection('NONE-02-30', 1., 1., True, 'partial-date', ())
            prediction = ImagePrediction('sample','NONE-02-30',selection,0.01,())
            with patch('src.pipeline.predict_image', return_value=prediction):
                summary = run_pipeline(root,root/'out.csv',backend=FakeBackend(),config=PipelineConfig(progress_every=0))
            self.assertEqual(len(summary['failures']),1)
            self.assertEqual(summary['predicted_none'],1)

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
