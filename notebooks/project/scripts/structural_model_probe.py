"""Bounded exposed-image padding experiment; no training or formal round execution."""
import argparse
import gc
import json
import os
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read, digest
from scripts.grouped_plan import BASE
from scripts.grouped_rounds import source_lock, model_lock, evidence, exclusive
from scripts.operating_environment import enforce
from scripts.correction_model_probe import SAMPLES


def main():
    import psutil
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development-root', type=Path, required=True)
    parser.add_argument('--network-mode', choices=['offline','online'], default='offline')
    args = parser.parse_args()
    development = args.development_root.resolve()
    code = development/'round_02/code'
    record = read(development/'development.json')
    if record['training_authorized'] is not False or model_lock(code/'weights/paddle') != record['model']:
        raise ValueError('Invalid model / development scope')
    if psutil.virtual_memory().available < 2.5*1024**3:
        raise RuntimeError('Need 2.5 GiB available for single CPU4 diagnostic')
    with exclusive(BASE/'locks/execution.lock'):
        dest = development/'structural-probes'/uuid.uuid4().hex
        dest.mkdir(parents=True, exist_ok=False)
        before = source_lock(code)
        if args.network_mode == 'online' and record.get('network_mode') != 'online':
            raise ValueError('Online development instruction binding required')
        from scripts.grouped_rounds import child_environment
        os.environ.update(child_environment([0,1,2,3]))
        proof = enforce([0,1,2,3], args.network_mode)
        mapping = {r['test_id']: r for r in csv_read(BASE/'test_to_original_mapping.csv')}
        inputs = []
        for i in (*SAMPLES, 'AMLT000643'):
            image = ROOT/'테스트용데이터'/(i+'.jpg')
            if digest(image) != mapping[i]['test_sha256'] or int(mapping[i]['round']) not in (2,3):
                raise ValueError('Unexpected or changed diagnostic image')
            inputs.append(dict(image_id=i, image_path=str(image), sha256=digest(image)))
        write(dest/'binding.json', dict(code=before, model=record['model'], inputs=inputs,
              controller=evidence(Path(__file__)), development=evidence(development/'development.json'), environment=proof))
        sys.path.insert(0, str(code/'notebooks/project'))
        from src.pipeline import PipelineConfig, PaddleOCRBackend, _load_bgr, predict_image
        from src.date_extraction import select_date, submission_decision
        from src.shared_detector import inner_ocr_pipeline
        results = []
        error = None
        try:
            for width in (320,192,160):
                os.environ['ITDA_PROFILE_PATH'] = str(dest/f'profile_{width}.jsonl')
                started = time.perf_counter()
                config = PipelineConfig(weights_dir=code/'weights/paddle')
                backend = PaddleOCRBackend(config)
                resize = inner_ocr_pipeline(backend._mobile).text_rec_model.pre_tfs['ReisizeNorm']
                original_shape = list(resize.rec_image_shape)
                if original_shape != [3,48,320]:
                    raise RuntimeError('Unexpected recognizer resize contract: '+str(original_shape))
                resize.rec_image_shape = [3,48,width]
                init = time.perf_counter()-started
                observed = []
                for item in inputs:
                    backend.profile.image_id = item['image_id']
                    image = _load_bgr(item['image_path'])
                    begin = time.perf_counter()
                    lines = backend.recognize(image, detector='mobile', variant='original')
                    selection = select_date(lines, context=config.date_context, product_rules=config.product_date_rules)
                    observed.append(dict(image_id=item['image_id'], seconds=time.perf_counter()-begin,
                         lines=[asdict(l) for l in lines], selection=asdict(selection), decision=asdict(submission_decision(selection))))
                value = dict(minimum_width=width, initialization_seconds=init,
                             total_seconds=time.perf_counter()-started, images=observed)
                write(dest/f'variant_{width}.json', json.loads(json.dumps(value, default=str, ensure_ascii=False)))
                results.append(dict(width=width, total_seconds=value['total_seconds']))
                # The original-width full recovery is a distinct, bounded diagnostic.
                if width == 320:
                    backend.profile.image_id = 'AMLT000643'
                    prediction = predict_image(ROOT/'테스트용데이터/AMLT000643.jpg', backend=backend, config=config)
                    write(dest/'fresh_643.json', json.loads(json.dumps(asdict(prediction),default=str,ensure_ascii=False)))
                del backend
                gc.collect()
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            unchanged = before == source_lock(code) and record['model'] == model_lock(code/'weights/paddle')
            write(dest/'result.json', dict(status='passed' if error is None and unchanged else 'failed',
                  error=error, variants=results, unchanged=unchanged, environment_after=enforce([0,1,2,3], args.network_mode),
                  memory=psutil.virtual_memory()._asdict(), training_executed=False, full_round_executed=False))
            print(dest, flush=True)


if __name__ == '__main__':
    main()
