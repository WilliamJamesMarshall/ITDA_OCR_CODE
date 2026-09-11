import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from src.date_extraction import OCRLine, select_date
from src.ocr_trace import ImageFrame, ImageTrace, box_polygon
from src.pipeline import (PaddleOCRBackend, PipelineConfig, _crop_fragment, _fragment_bounds,
                          _overlapping_tiles, _tile_bounds, predict_image, run_pipeline)
from scripts.validation_runner import run_timed_pipeline, _supervise
from scripts.evaluate_pipeline import assess_targets


def line(text='EXP 2E.03.25', box=(10, 20, 110, 40), **kwargs):
    return OCRLine(text, .8, box, **kwargs)


def _trace_hung_worker(journal, trace_path):
    def emit(event):
        with open(trace_path, 'a', encoding='utf-8') as stream:
            stream.write(json.dumps(event)+'\n')
    trace = ImageTrace('sample', emit)
    frame = ImageFrame(200, 200)
    trace.start(200, 200)
    trace.start_pass(frame, 'mobile', 'original')
    trace.record_pass([line('1234..xxxx')], [], frame, 'mobile', 'original', .1)
    trace.start_pass(frame, 'recovery', 'original')
    time.sleep(60)


class RegionTraceTest(unittest.TestCase):
    def test_roi_and_rotation_associate_only_after_coordinate_mapping(self):
        trace = ImageTrace('sample')
        original = line(box=(110, 120, 210, 140))
        trace.record_pass([original], [], ImageFrame(300, 200), 'mobile', 'original', .1)
        trace.record_pass([line(box=(20, 40, 220, 80), variant='roi-1')], [],
                          ImageFrame.crop((100, 100, 250, 180), (160, 300, 3)), 'mobile', 'roi-1', .1)
        trace.record_pass([line(box=(60, 110, 80, 210), variant='rot90')], [],
                          ImageFrame.rotated(300, 200, 90), 'mobile', 'rot90', .1)
        self.assertEqual(len(trace.regions), 1)
        for observation in trace.observations:
            self.assertEqual(observation['original_box'], original.box)

    def test_no_parse_or_no_text_does_not_erase_region(self):
        trace = ImageTrace('sample')
        values = [line('소비기한'), line('a0E1.0R0EH', box=(10, 50, 110, 70))]
        trace.record_pass(values, [line('', box=(10, 80, 110, 100))], ImageFrame(200, 200),
                          'mobile', 'original', .1, select_date(values))
        self.assertEqual(len(trace.observations), 3)
        self.assertEqual(trace.observations[0]['role_hints'][0]['role'], 'expiry')
        self.assertEqual(trace.observations[0]['full_parses'], [])
        self.assertEqual(trace.observations[1]['parse_status'], 'unparsed')
        self.assertEqual(trace.summary()['detected_without_text'], 1)
        self.assertEqual(trace.summary()['unparsed_date_like'], 2)

    def test_role_history_survives_changed_text_but_is_not_propagated(self):
        trace = ImageTrace('sample')
        for text, variant in [('제조일자 25.09.26', 'original'), ('레조일차 25.09.23', 'clahe')]:
            trace.record_pass([line(text, variant=variant)], [], ImageFrame(200, 200), 'mobile', variant, .1)
        self.assertEqual(len(trace.regions), 1)
        self.assertTrue(trace.observations[0]['role_hints'])
        self.assertEqual(trace.observations[1]['role_hints'], [])
        self.assertEqual(trace.observations[1]['association'], 'geometric_overlap_hypothesis')

    def test_lexical_manufacture_description_is_not_a_confirmed_role(self):
        trace = ImageTrace('sample')
        trace.record_pass([line('같은 제조시설에서 제조하고 있습니다')], [], ImageFrame(200, 200), 'mobile', 'original', .1)
        self.assertTrue(all(h['basis'] == 'lexical_only' for h in trace.observations[0]['role_hints']))

    def test_partial_fields_are_kept_without_inventing_a_year(self):
        trace = ImageTrace('sample')
        trace.record_pass([line('소비기한 02월 14일')], [], ImageFrame(200, 200), 'mobile', 'original', .1)
        self.assertEqual(trace.observations[0]['partial_parses'], ['NONE-02-14'])

    def test_same_value_at_different_positions_is_not_one_region(self):
        trace = ImageTrace('sample')
        trace.record_pass([line('2026.09.05'), line('2026.09.05', box=(10, 100, 110, 120))],
                          [], ImageFrame(200, 200), 'mobile', 'original', .1)
        self.assertEqual(len(trace.regions), 2)

    def test_unknown_or_synthetic_coordinates_never_match(self):
        for frame, geometry_valid in [(None, True), (ImageFrame(200, 200), False)]:
            trace = ImageTrace('sample')
            for variant in ['original', 'roi-1']:
                trace.record_pass([line(variant=variant, geometry_valid=geometry_valid)], [], frame, 'mobile', variant, .1)
            self.assertEqual(len(trace.regions), 2)
            self.assertEqual(trace.summary()['unknown_geometry'], 2)

    def test_ambiguous_overlap_does_not_merge_two_rows(self):
        trace = ImageTrace('sample')
        trace.record_pass([line(box=(0, 0, 100, 20)), line(box=(0, 2, 100, 22))], [], ImageFrame(200, 200), 'mobile', 'original', .1)
        trace.record_pass([line(box=(0, 1, 100, 21))], [], ImageFrame(200, 200), 'recovery', 'original', .1)
        self.assertEqual(len(trace.regions), 3)
        self.assertEqual(trace.observations[-1]['association'], 'ambiguous_new')

    def test_anchor_does_not_drift_transitively(self):
        trace = ImageTrace('sample')
        for offset in (0, 10, 20):
            trace.record_pass([line(box=(offset, 0, offset+100, 20))], [], ImageFrame(200, 200), 'mobile', str(offset), .1)
        self.assertEqual(len(trace.regions), 2)
        self.assertEqual(trace.regions[0]['anchor_box'], (0, 0, 100, 20))

    def test_crop_mapping_uses_actual_resized_dimensions(self):
        image = np.zeros((237, 431, 3), dtype=np.uint8)
        fragment = line(box=(170, 110, 203, 128))
        bounds = _fragment_bounds(image, fragment)
        crop = _crop_fragment(image, fragment)
        frame = ImageFrame.crop(bounds, crop.shape)
        mapped = frame.map_polygon(box_polygon((0, 0, crop.shape[1], crop.shape[0])))
        np.testing.assert_allclose(mapped, box_polygon(bounds))

    def test_rotation_transforms_non_square_image_edges(self):
        width, height = 300, 200
        for angle, point, expected in [(90, (30, 40), (40, 170)),
                                       (180, (30, 40), (270, 160)),
                                       (270, (30, 40), (260, 30))]:
            frame = ImageFrame.rotated(width, height, angle)
            self.assertEqual(frame.map_polygon((point,))[0], expected)
            mapped = frame.map_polygon(box_polygon((0, 0, frame.width, frame.height)))
            self.assertEqual(set(mapped), set(box_polygon((0, 0, width, height))))

    def test_all_tile_corners_map_back_to_original(self):
        image = np.zeros((203, 317, 3), dtype=np.uint8)
        for tile, bounds in zip(_overlapping_tiles(image, .62), _tile_bounds(image, .62)):
            frame = ImageFrame.crop(bounds, tile.shape)
            self.assertEqual(frame.map_polygon(box_polygon((0, 0, frame.width, frame.height))), box_polygon(bounds))

    def test_polygon_and_candidate_provenance_are_kept(self):
        trace = ImageTrace('sample')
        polygon = ((10, 22), (110, 20), (111, 38), (11, 40))
        values = [line('EXP 2026.09.05', polygon=polygon)]
        trace.record_pass(values, [], ImageFrame(200, 200), 'mobile', 'original', .1, select_date(values))
        self.assertEqual(trace.observations[0]['original_polygon'], polygon)
        self.assertEqual(trace.outcomes[0]['selection']['candidates'][0]['observation_ids'], ['p001:o0001'])


class BackendTraceTest(unittest.TestCase):
    def backend(self, data):
        backend = PaddleOCRBackend.__new__(PaddleOCRBackend)
        backend._mobile = SimpleNamespace(predict=lambda image: [SimpleNamespace(json={'res': data})])
        return backend

    def test_filtered_detection_is_preserved_but_not_a_selector_input(self):
        poly = box_polygon((10, 20, 110, 40))
        missing = box_polygon((10, 60, 110, 80))
        backend = self.backend(dict(rec_texts=['EXP 2026.09.05'], rec_scores=[.99],
                                    rec_polys=[poly], dt_polys=[poly, missing]))
        result = backend.recognize(np.zeros((200, 200, 3)), detector='mobile', variant='original')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].polygon, poly)
        self.assertEqual(len(backend.last_unrecognized_regions), 1)
        self.assertEqual(backend.last_unrecognized_regions[0].polygon, missing)
        backend._mobile = SimpleNamespace(predict=lambda image: [])
        self.assertEqual(backend.recognize(np.zeros((1, 1, 3)), detector='mobile', variant='original'), [])
        self.assertEqual(backend.last_unrecognized_regions, [])

    def test_empty_recognition_without_detector_polygons_is_retained(self):
        backend = self.backend(dict(rec_texts=[''], rec_scores=[.2], rec_polys=[box_polygon((1, 2, 10, 12))]))
        self.assertEqual(backend.recognize(np.zeros((20, 20, 3)), detector='mobile', variant='original'), [])
        self.assertEqual(len(backend.last_unrecognized_regions), 1)

    def test_missing_geometry_does_not_become_a_real_location(self):
        backend = self.backend(dict(rec_texts=['2026.09.05'], rec_scores=[.99]))
        result = backend.recognize(np.zeros((20, 20, 3)), detector='mobile', variant='original')
        self.assertFalse(result[0].geometry_valid)
        self.assertEqual(result[0].geometry_source, 'synthetic_index')


class PipelineTraceTest(unittest.TestCase):
    def test_backend_time_is_diagnostic_not_a_replacement_for_total_time(self):
        runtime = dict(images=10, total_elapsed_seconds=40., failures=[],
                       ocr_backend_seconds_per_completed_image=2.)
        accuracy = dict(evaluated_labels=10, exact_matches=10, accuracy_target_met=True,
                        labels_without_predictions=[], skipped={}, submission_format={'all_rows_compliant': True})
        targets = assess_targets(runtime, accuracy)
        self.assertEqual(targets['ocr_backend_seconds_per_image_over_target'], -1.)
        self.assertEqual(targets['seconds_per_image_over_target'], 1.)
        self.assertFalse(targets['local_relative_joint_target_met'])

    def test_hard_termination_preserves_passes_and_pending_call(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory)/'trace.jsonl'
            result = _supervise(_trace_hung_worker, (str(trace_path),), hard_timeout_seconds=3)
            self.assertEqual(result['status'], 'timeout')
            events = [json.loads(raw) for raw in trace_path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(events[-1]['kind'], 'ocr_start')
            self.assertEqual(events[-1]['detector'], 'recovery')
            self.assertEqual(len([event for event in events if event['kind'] == 'ocr_pass']), 1)
            self.assertFalse(any(event['kind'] == 'image_end' for event in events))

    def test_trace_does_not_change_selection_or_pass_schedule(self):
        class Backend:
            def recognize(self, image, *, detector, variant):
                return [line('EXP 2026.09.05' if variant == 'tile-4' else '1234..xxxx',
                             source=detector, variant=variant)]

        config = PipelineConfig(enable_rotation_fallback=True)
        with patch('src.pipeline._load_bgr', return_value=np.zeros((200, 300, 3), dtype=np.uint8)):
            before = predict_image(Path('sample.jpg'), Backend(), replace(config, collect_trace=False))
            after = predict_image(Path('sample.jpg'), Backend(), config)
        self.assertEqual(before.selection, after.selection)
        self.assertEqual(before.passes, after.passes)
        self.assertIsNone(before.trace)
        self.assertEqual(len(after.trace['frames']), len(after.passes))
        variants = {frame['variant'] for frame in after.trace['frames']}
        self.assertTrue({'roi-1', 'clahe', 'rot90', 'rot180', 'rot270', 'tile-4'} <= variants)

    def test_trace_uses_exif_oriented_input_space(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.jpg'
            exif = Image.Exif()
            exif[274] = 6
            Image.new('RGB', (100, 200), 'white').save(path, exif=exif)
            backend = SimpleNamespace(recognize=lambda *args, **kwargs: [line('EXP 2026.09.05')])
            result = predict_image(path, backend, PipelineConfig())
            geometry = result.trace['frames'][0]['geometry']
            self.assertEqual((geometry['width'], geometry['height']), (200, 100))

    def test_backend_error_keeps_previous_evidence_and_error_event(self):
        class Backend:
            def recognize(self, image, *, detector, variant):
                if variant == 'original':
                    return [line('1234..xxxx')]
                raise RuntimeError('recognition failed')

        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            Image.new('RGB', (200, 200), 'white').save(root / 'sample.jpg')
            result = run_pipeline(root, root/'out.csv', backend=Backend(), config=PipelineConfig(progress_every=0))
            events = [json.loads(raw) for raw in Path(result['trace_path']).read_text(encoding='utf-8').splitlines()]
            passes = [event for event in events if event['kind'] == 'ocr_pass']
            self.assertEqual(passes[0]['observations'][0]['text'], '1234..xxxx')
            self.assertIn('recognition failed', passes[1]['outcome']['error'])
            self.assertIn('recognition failed', events[-1]['error'])
            self.assertEqual(result['trace_summary']['failed_passes'], 1)
            self.assertEqual(len(result['failures']), 1)

    def test_initialization_timeout_clears_stale_trace(self):
        result = dict(status='timeout', elapsed_seconds=2400.1, exit_code=-1, events=[], hard_timeout_seconds=2400)
        with tempfile.TemporaryDirectory() as directory, patch('scripts.validation_runner._supervise', return_value=result):
            output = Path(directory) / 'out.csv'
            trace = Path(str(output)+'.trace.jsonl')
            trace.write_text('old run', encoding='utf-8')
            runtime = run_timed_pipeline(directory, output, config=PipelineConfig(), expected_images=[Path('1.jpg')])
            self.assertEqual(trace.read_text(encoding='utf-8'), '')
            self.assertEqual(runtime['trace_path'], str(trace.resolve()))
            self.assertIsNone(runtime['ocr_backend_seconds_per_completed_image'])


if __name__ == '__main__':
    unittest.main()
