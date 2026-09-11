"""Four already-used difficult development images; paired trace on/off smoke test."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.pipeline import PaddleOCRBackend, PipelineConfig, predict_image
from src.ocr_trace import ImageTrace


def main():
    manifest = json.loads((ROOT/'artifacts/date-recognition-repair-20260910/manifest.json').read_text(encoding='utf-8'))
    selected = [r for r in manifest['included'] if r['current_id'] in {'000276', '003645', '003666', '003714'}]
    assert len(selected) == 4
    config = PipelineConfig(progress_every=0)
    started = time.perf_counter()
    backend = PaddleOCRBackend(config)
    initialization = time.perf_counter()-started
    results = []
    for index, item in enumerate(selected):
        path = Path(item['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
        runs = {}
        for enabled in ([False, True] if index % 2 == 0 else [True, False]):
            trace_path = OUT/f"{item['current_id']}.trace.jsonl"
            if enabled:
                with trace_path.open('w', encoding='utf-8') as stream:
                    def emit(event):
                        stream.write(json.dumps(event, ensure_ascii=False)+'\n')
                        stream.flush()
                    prediction = predict_image(path, backend, config, trace=ImageTrace(path.stem, emit))
            else:
                prediction = predict_image(path, backend, replace(config, collect_trace=False))
            runs[str(enabled)] = dict(final_date=prediction.final_date, reason=prediction.selection.reason,
                                     passes=prediction.passes, seconds=prediction.elapsed_seconds,
                                     summary=prediction.trace['summary'] if prediction.trace else None)
        assert runs['True']['final_date'] == runs['False']['final_date'], item['current_id']
        assert runs['True']['passes'] == runs['False']['passes'], item['current_id']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
        results.append(dict(image_id=item['current_id'], expected=item['expected'], runs=runs))
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        (OUT/'live_progress.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    result = dict(scope='Four pre-existing difficult development images, paired on/off runs with reused backend and alternating order. '
                        'Not representative accuracy, not independent 500-image validation. Per-image times exclude shared initialization.',
                  shared_initialization_seconds=initialization, results=results,
                  mean_seconds={key: sum(r['runs'][key]['seconds'] for r in results)/len(results) for key in ('False', 'True')})
    result['trace_on_seconds_over_3'] = result['mean_seconds']['True']-3.
    result['trace_on_exact'] = sum((r['runs']['True']['final_date'] or 'NONE') == r['expected'] for r in results)
    (OUT/'live_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'results'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
