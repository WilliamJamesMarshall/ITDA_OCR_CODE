"""Apply the approved 1117 label overlay to saved round-4 output, without OCR."""
import csv
import os
from pathlib import Path
from scripts.audit_cumulative_1_5 import read, rows, sha, write_new
from scripts.grouped_rounds import labels_for
from scripts.evaluate_pipeline import read_labels, score_predictions
from scripts import ocr_annotations as ann


def main():
    run = Path(os.environ['ITDA_CUMULATIVE_RUN']).resolve()
    base = run.parent
    correction = base / 'answer-correction-20260915-v1'
    workbook = ann.ROOT / '학습대상_정답지/answer_000001_002610_manual.xlsx'
    assert sha(workbook) == '765db2f4781ec1975893e66b7c3c755f8a68246c68fc05d302597d36900a4d2d'
    source = correction / 'labels.corrected.csv'
    assert sha(source) == 'd93b009515cca921629932891a76e5a0b103853042df06cf46b97730e0131f07'
    labels = rows(source)
    target = [r for r in labels if r['original_id'] == 'AMLC001117']
    assert len(target) == 1 and target[0]['정답 날짜'] == 'NONE'
    target[0]['정답 날짜'] = '2021-06-26'
    out = run / 'saved-output-rescore'
    out.mkdir(exist_ok=False)
    label_path = out / 'labels.latest.csv'
    with label_path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(labels[0]))
        writer.writeheader()
        writer.writerows(labels)
    ids = [r['image_id'] for r in rows(base / 'test_round_04.csv')]
    assert len(ids) == 394
    prediction_path = base / 'rounds/round_04/submission.csv'
    runtime = read(base / 'rounds/round_04/runtime.json')
    labels = labels_for(base, ids, read_labels(label_path))
    metrics = score_predictions(labels, rows(prediction_path), runtime['failures'], expected_ids=ids)
    previous = read(correction / 'round_04/score.json')['metrics']
    assert metrics['field_correct'] == previous['field_correct'] + 3
    assert metrics['exact_matches'] == previous['exact_matches'] + 1
    write_new(out / 'round_04.score.json', dict(round=4, score_kind='saved_output_rescore_1117_label_amendment',
        metrics=metrics, inference_rerun=False, formal_round_state_changed=False,
        labels=dict(path=str(label_path), sha256=sha(label_path)), workbook=dict(path=str(workbook), sha256=sha(workbook)),
        predictions=dict(path=str(prediction_path), sha256=sha(prediction_path)),
        amendment=dict(path=str(base / 'label-1117-correction-20260915-v1/amendment.json'), sha256=sha(base / 'label-1117-correction-20260915-v1/amendment.json')),
        previous_field_correct=previous['field_correct'], previous_exact_matches=previous['exact_matches'],
        historical_runtime_seconds=runtime.get('total_elapsed_seconds'), round_05_unchanged=True))
    print(dict(field_correct=metrics['field_correct'], field_total=metrics['field_total'], exact=metrics['exact_matches'], inference_rerun=False))


if __name__ == '__main__':
    main()
