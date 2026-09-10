"""Fresh bounded development comparison using the real batch/evaluation path."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

from validate import ROOT, OUT, manifest, load_before, save
from src import pipeline
from src import date_extraction as current
from scripts.evaluate_pipeline import assess_targets, score_predictions, read_predictions


class RecordingBackend(pipeline.PaddleOCRBackend):
    def __init__(self, config):
        super().__init__(config)
        self.events = []

    def recognize(self, image, *, detector, variant):
        lines = super().recognize(image, detector=detector, variant=variant)
        self.events.append(dict(detector=detector, variant=variant, lines=[asdict(v) for v in lines]))
        return lines


def main():
    rows = manifest()
    comparison = json.loads((OUT / 'comparison.json').read_text(encoding='utf-8'))
    affected = {r['historical_id'] for r in comparison['changed']}
    selected = [r for r in rows if r['historical_id'] in affected]
    # Fixed controls cover labelled pairs, partials, order fallback and NONE.
    controls = {'000063', '000180', '000014', '000315', '000276', '003421', '003611',
                '003645', '003654', '003734', '003519', '003676', '003693'}
    selected += [r for r in rows if r['historical_id'] in controls and r not in selected]
    inputs = OUT / 'live_inputs'
    inputs.mkdir(exist_ok=True)
    for r in selected:
        assert hashlib.sha256(Path(r['path']).read_bytes()).hexdigest() == r['sha256']
        dest = inputs / (r['current_id'] + Path(r['path']).suffix)
        if not dest.exists():
            os.link(r['path'], dest)  # Read-only inference; no original bytes are edited.
        assert hashlib.sha256(dest.read_bytes()).hexdigest() == r['sha256']
    assert len(list(inputs.iterdir())) == len(selected)
    labels = {r['current_id']: {'정답 날짜': r['expected'], '라벨 상태': 'manual'} for r in selected}
    names = ('src/date_extraction.py', 'src/pipeline.py', 'scripts/evaluate_pipeline.py')
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    save('live_manifest.json', dict(code_sha256=hashes, scope='Targeted development cases; no independent accuracy claim',
                                    images=[{k: r[k] for k in ('historical_id', 'current_id', 'path', 'sha256', 'expected')} for r in selected]))
    before = load_before()
    original_predict = pipeline.predict_image
    original_backend = pipeline.PaddleOCRBackend
    results = {}
    try:
        pipeline.PaddleOCRBackend = RecordingBackend
        for key, policy in (('before', before), ('after', current)):
            pipeline.select_date = policy.select_date
            records = []

            def recording_predict(path, backend, config):
                backend.events = []
                pred = original_predict(path, backend, config)
                records.append(dict(image_id=path.stem, prediction=pred.final_date or 'NONE', passes=pred.passes,
                                    seconds=pred.elapsed_seconds, reason=pred.selection.reason, events=backend.events))
                return pred

            pipeline.predict_image = recording_predict
            runtime = pipeline.run_pipeline(inputs, OUT / (key + '_predictions.csv'), config=pipeline.PipelineConfig(progress_every=1))
            score = score_predictions(labels, read_predictions(OUT / (key + '_predictions.csv')), runtime['failures'], expected_ids=list(labels))
            results[key] = dict(runtime=runtime, accuracy=score, targets=assess_targets(runtime, score), records=records)
            save('live_progress.json', results)
    finally:
        pipeline.PaddleOCRBackend = original_backend
        pipeline.predict_image = original_predict
        pipeline.select_date = current.select_date
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h for name, h in hashes.items())
    assert all(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest() == r['sha256'] for r in selected)
    save('live_result.json', dict(results=results, code_sha256=hashes,
                                  scope='Fresh batch for each policy, including lazy backend initialization and CSV output. Python/import startup excluded. Before then after; single runs, not a repeated timing study.'))
    for key, result in results.items():
        print(key, result['accuracy']['exact_matches'], result['runtime']['ocr_calls'], result['targets'], flush=True)


if __name__ == '__main__':
    main()
