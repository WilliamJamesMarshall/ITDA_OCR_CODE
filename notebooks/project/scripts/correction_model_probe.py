"""Offline, CPU4 exposed-image diagnostics; never training or formal test promotion."""
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
from scripts.operating_environment import enforce, network_probe

SAMPLES = ('AMLT000218', 'AMLT000226', 'AMLT000263', 'BMLT003522', 'AMLT000353',
           'AMLT000355', 'AMLT000368', 'AMLT000375', 'AMLT000378', 'AMLT000515')


def main():
    import psutil
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development-root', type=Path, required=True)
    args = parser.parse_args()
    development = args.development_root.resolve()
    code = development/'round_02/code'
    record = read(development/'development.json')
    if record['training_authorized'] is not False or model_lock(code/'weights/paddle') != record['model']:
        raise ValueError('Invalid fixed model / development scope')
    if psutil.virtual_memory().available < 2.5*1024**3:
        raise RuntimeError('Need 2.5 GiB available for single CPU4 diagnostic')
    with exclusive(BASE/'locks/execution.lock'):
        dest = development/'probes'/uuid.uuid4().hex
        dest.mkdir(parents=True, exist_ok=False)
        before = source_lock(code)
        proof = enforce([0,1,2,3])
        mapping = {r['test_id']: r for r in csv_read(BASE/'test_to_original_mapping.csv')}
        inputs = []
        for i in SAMPLES:
            image = ROOT/'테스트용데이터'/(i+'.jpg')
            if digest(image) != mapping[i]['test_sha256'] or int(mapping[i]['round']) not in (2,3):
                raise ValueError('Unexpected or changed diagnostic image')
            inputs.append(dict(image_id=i, image_path=str(image), sha256=digest(image)))
        write(dest/'binding.json', dict(code=before, model=record['model'], inputs=inputs,
                                       development=evidence(development/'development.json'), environment=proof))
        sys.path.insert(0, str(code/'notebooks/project'))
        from src.pipeline import PipelineConfig, PaddleOCRBackend, _load_bgr
        from src.date_extraction import select_date
        from src.shared_detector import inner_ocr_pipeline
        results = []
        error = None
        try:
            os.environ['ITDA_SHARE_RECOGNIZER'] = '1'
            os.environ['ITDA_PROFILE_PATH'] = str(dest/'equivalence_profile.jsonl')
            config = PipelineConfig(weights_dir=code/'weights/paddle')
            backend = PaddleOCRBackend(config)
            inner = inner_ocr_pipeline(backend._mobile)
            original_det, original_rec = inner.text_det_model, inner.text_rec_model
            shared = []
            for i in ('AMLT000375', 'AMLT000378'):
                image = _load_bgr(ROOT/'테스트용데이터'/(i+'.jpg'))
                backend.profile.image_id = i
                lines = backend.recognize(image, detector='recovery', variant='equivalence')
                assert inner.text_det_model is original_det and inner.text_rec_model is original_rec
                shared.append(lines)
            shared_model = backend._recovery
            backend._recovery = backend._build(config.recovery_detector_name, config.recovery_side_limit)
            equivalence = []
            for i, expected in zip(('AMLT000375', 'AMLT000378'), shared):
                backend.profile.image_id = i
                actual = backend.recognize(_load_bgr(ROOT/'테스트용데이터'/(i+'.jpg')),
                                           detector='recovery', variant='equivalence')
                same = actual == expected
                equivalence.append(dict(image_id=i, identical=same, shared=[asdict(l) for l in expected],
                                        independent=[asdict(l) for l in actual]))
            write(dest/'equivalence.json', dict(cases=equivalence, restored=True,
                                               shared_recognizer_identity=id(original_rec),
                                               secondary_detector_identity=id(shared_model.detector)))
            if not all(r['identical'] for r in equivalence):
                raise RuntimeError('Shared secondary detector differs from independent reference')
            del backend, inner, original_det, original_rec, shared_model
            gc.collect()
            for side, batch in ((1600,8), (1280,8), (1600,4), (1600,16)):
                os.environ['ITDA_PROFILE_PATH'] = str(dest/f'profile_{side}_{batch}.jsonl')
                started = time.perf_counter()
                config = PipelineConfig(weights_dir=code/'weights/paddle', mobile_side_limit=side,
                                        recognition_batch_size=batch)
                backend = PaddleOCRBackend(config)
                init = time.perf_counter()-started
                observed = []
                for item in inputs:
                    backend.profile.image_id = item['image_id']
                    image = _load_bgr(item['image_path'])
                    begin = time.perf_counter()
                    lines = backend.recognize(image, detector='mobile', variant='original')
                    selection = select_date(lines, context=config.date_context, product_rules=config.product_date_rules)
                    observed.append(dict(image_id=item['image_id'], seconds=time.perf_counter()-begin,
                                         lines=[asdict(l) for l in lines], selection=asdict(selection)))
                value = dict(side=side, batch=batch, initialization_seconds=init,
                             total_seconds=time.perf_counter()-started, images=observed)
                # Date objects in candidate dataclasses are serialized explicitly.
                value = json.loads(json.dumps(value, default=str, ensure_ascii=False))
                write(dest/f'variant_{side}_{batch}.json', value)
                results.append(dict(side=side,batch=batch,total_seconds=value['total_seconds']))
                del backend
                gc.collect()
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            unchanged = before == source_lock(code) and record['model'] == model_lock(code/'weights/paddle')
            write(dest/'result.json', dict(status='passed' if error is None and unchanged else 'failed',
                  error=error, variants=results, unchanged=unchanged, environment_after=enforce([0,1,2,3]),
                  memory=psutil.virtual_memory()._asdict(), training_executed=False))
            print(dest, flush=True)


if __name__ == '__main__':
    main()
