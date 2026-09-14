"""Score finished development runs only; do not modify formal round reports."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path('C:/ITDA_OCR_CODE')
BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2')
DEV = BASE/'paper-ocr-20260914'
OLD = BASE/'retest-stage2-field-accuracy-online-20260914-v15/execution'
sys.path.insert(0, str(ROOT/'notebooks/project'))
from scripts.evaluate_pipeline import read_labels, read_predictions, score_predictions
from src.date_fields import fields_from_date


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def evidence(path):
    return dict(path=str(path),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def write(path, value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    result=read(args.run/'result.json')
    job=read(args.run/'job.json')
    reports=[]
    for n in (2,3):
        folder=args.run/f'round_{n:02}'
        runtime=read(folder/'runtime.json')
        with Path(job['manifests'][str(n)]['path']).open(encoding='utf-8-sig',newline='') as stream:
            ids=[r['image_id'] for r in csv.DictReader(stream)]
        label_path=(Path('C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/scorer_only/labels.csv')
                    if job.get('execution_policy')=='grouped-6-originals-v1' else
                    BASE/f'stage2_initial_20260913/approved_labels_round_{n:02}.csv')
        with label_path.open(encoding='utf-8-sig',newline='') as stream:
            labels={r['image_id']:r for r in csv.DictReader(stream) if r['image_id'] in set(ids)}
        output=folder/'submission.csv'
        predictions=read_predictions(output) if output.exists() else []
        failures=runtime['failures']
        if runtime['status']!='completed':
            failures=[dict(image_id=i,error='Incomplete run') for i in ids]
        metrics=score_predictions(labels,predictions,failures,expected_ids=ids)
        old={r['image_id']:r for r in read_predictions(OLD/f'round_{n:02}/submission.csv')}
        changes=[]
        for row in predictions:
            i=row['image_id']
            expected=fields_from_date(labels[i]['정답 날짜'])
            gained=[k for k in ('year','month','day') if row[k]==expected[k]!=old[i][k]]
            lost=[k for k in ('year','month','day') if row[k]!=expected[k]==old[i][k]]
            if any(row[k]!=old[i][k] for k in ('year','month','day')):
                changes.append(dict(image_id=i,old=old[i],new=row,expected=expected,gained=gained,lost=lost))
        time_met=runtime['status']=='completed' and runtime['total_elapsed_seconds']<=1600
        partial_diagnostic=None
        partial=Path(str(output)+'.partial.csv')
        if runtime['status']!='completed' and partial.exists():
            partial_diagnostic=score_predictions(labels,read_predictions(partial),runtime['failures'],expected_ids=ids)
        report=dict(round=n,images=len(ids),smoke=job['smoke'],metrics=metrics,
            partial_diagnostic=partial_diagnostic,comparison_complete=runtime['status']=='completed',
            runtime=runtime,changes=changes,
            field_gains=sum(len(c['gained']) for c in changes) if runtime['status']=='completed' else None,
            field_losses=sum(len(c['lost']) for c in changes) if runtime['status']=='completed' else None,
            time_target_met=time_met,
            joint_500_target_met=not job['smoke'] and len(ids)==500 and time_met and metrics['accuracy_target_met']
                and metrics['submission_format']['all_rows_compliant'] and not failures,
            input_evidence=dict(labels=evidence(label_path),output=evidence(output) if output.exists() else None,
                runtime=evidence(folder/'runtime.json'),baseline=evidence(OLD/f'round_{n:02}/submission.csv')),
            scope='Repeatedly exposed development images. Not an independent holdout estimate. No promotion.')
        write(folder/'paper-report.json',report)
        reports.append(report)
        print(json.dumps(dict(round=n,images=len(ids),correct=metrics['field_correct'],
            total=metrics['field_total'],seconds=runtime['total_elapsed_seconds'],
            gains=report['field_gains'],losses=report['field_losses'],joint=report['joint_500_target_met'])),flush=True)
    protected=read(DEV/'authorization.json')['protected']
    changed=[path for path,sha in protected.items() if evidence(path)['sha256']!=sha]
    summary=dict(run=evidence(args.run/'result.json'),baseline_changed=changed,
        reports=[evidence(args.run/f'round_{n:02}/paper-report.json') for n in (2,3)],
        joint_target_met=all(r['joint_500_target_met'] for r in reports),promoted=False)
    write(args.run/'paper-summary.json',summary)
    lines=['# 논문 적용 1차 후보 검증','',
        '기준: 연·월·일 정답 필드 / 1,500 ≥ 95%, 각 500장 전체 노트북 ≤ 1,600초.',
        '반복 노출된 2·3회 개발 재평가이며 독립 일반화 성능을 뜻하지 않습니다.','',
        '| 회차 | 정답 필드 | 필드 정확도 | 전체 시간 | v15 대비 획득 / 손실 |',
        '|---|---:|---:|---:|---:|']
    for r in reports:
        m=r['metrics']
        lines.append(f"| {r['round']} | {m['field_correct']}/{m['field_total']} | {m['field_accuracy']:.4%} | "
                     f"{r['runtime']['total_elapsed_seconds']:.3f}초 | {r['field_gains']} / {r['field_losses']} |")
    lines+=['','동시 목표 달성: '+str(summary['joint_target_met']),
        '기존 기준 사본 변경: '+str(len(changed))+'개. 공용 반영·모델 교체·단계 승격 없음.',
        '', '정확한 오답·퇴행·시간·CPU·메모리 증거는 회차별 paper-report.json을 확인합니다.']
    with (args.run/'paper-summary.md').open('x',encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')


if __name__=='__main__':
    main()
