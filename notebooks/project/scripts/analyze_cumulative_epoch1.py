"""Post-process completed saved outputs only; never launch OCR or training."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from scripts.evaluate_cumulative_epoch1 import BASE, RUN, REPORTS, COUNTS, verify_release
from scripts.prepare_sequential_rounds import read, write, digest, csv_read
from scripts.evaluate_pipeline import read_labels, read_predictions, score_predictions
from scripts.grouped_rounds import labels_for

ROUTES = {
    'unavailable': ('실패·누락', '실행 로그·시간 제한·출력 저장을 먼저 점검', '학습으로 실행 실패를 해결하지 않음'),
    'none_false_positive': ('NONE 정답에 날짜 필드 출력', '제조일·로트·비날짜 역할과 후보 수용 조건 검토', '표제 문자 인식이 부족한 경우에만 승인 crop 검토'),
    'candidate_withheld': ('정답 후보 관측·필드 보류', '수용 임계값·부분 필드 보존·역할 충돌 경로 재현', '후보가 이미 있어 추가 학습만의 우선순위는 낮음'),
    'candidate_other': ('정답 후보 관측·다른 값 선택', '후보 순위·역할·날짜 순서 선택을 재현', '표제 오인식이 확인되면 인식기 보완을 검토'),
    'context_mixed': ('정답 후보 미관측·순서/역할 문맥 경합', '후보 생성과 순서/역할 해석을 분리 검토', '인식 오류 증거가 있는 승인 crop만 후속 학습 후보'),
    'candidate_absent': ('정답 후보 미관측', '검출·잘림·문자인식·파싱 중 실패 지점을 원본과 대조', '인식 오류면 누적 학습 검토; 검출 누락은 인식기 학습만으로 해결 불가'),
}


def analyze(number):
    verify_release()
    folder=RUN/'evaluation'/f'round_{number:02d}'
    report=read(folder/'report.json');metrics=report['metrics']
    target=folder/'analysis.json'
    if target.exists():raise FileExistsError(target)
    ids=[r['image_id'] for r in csv_read(RUN/'control'/f'test_round_{number:02d}.csv')]
    labels=labels_for(RUN/'control',ids,read_labels(RUN/'labels.csv'))
    baseline=(BASE/'joint123-20260914-v1/targeted-retrain-code-20260914-v1/comparison/retrained'/f'round_{number:02d}'/'submission.csv'
              if number<=3 else BASE/'rounds'/f'round_{number:02d}'/'submission.csv')
    previous=score_predictions(labels,read_predictions(baseline),[],expected_ids=ids)
    changes=[]
    for image_id in ids:
        before=previous['field_results'][image_id];after=metrics['field_results'][image_id]
        gained=[f for f in before if not before[f] and after[f]]
        lost=[f for f in before if before[f] and not after[f]]
        if gained or lost:changes.append(dict(image_id=image_id,gained=gained,lost=lost))
    wrong={e['image_id']:e for e in report['errors']}
    evidence=defaultdict(lambda:dict(matches=[],reasons=[],observations=[]))
    trace=folder/'submission.csv.trace.jsonl'
    if trace.exists():
        with trace.open(encoding='utf-8') as stream:
            for line_number,line in enumerate(stream,1):
                try:event=json.loads(line)
                except ValueError:continue
                image_id=event.get('image_id')
                if image_id not in wrong or event.get('kind') not in ('ocr_pass','image_end'):continue
                item=evidence[image_id];selection=event.get('selection') or event.get('outcome') or {}
                if isinstance(selection,dict):
                    if selection.get('reason'):item['reasons'].append(selection['reason'])
                    for candidate in selection.get('candidates',[]):
                        if candidate.get('value')==wrong[image_id]['expected']:
                            item['matches'].append(dict(trace_line=line_number,phase=event.get('phase'),candidate=candidate))
                for observed in event.get('observations',[]):
                    text=observed.get('text','')
                    if any(c.isdigit() for c in text) and text not in item['observations']:item['observations'].append(text)
    failed={e['image_id'] for e in report['runtime'].get('failures',[])}
    unavailable=failed|set(metrics['labels_without_predictions'])
    categories=Counter();field_counts=Counter();cases=[]
    for image_id,error in wrong.items():
        item=evidence[image_id];actual=(error.get('prediction') or {}).get('final_date','NONE')
        kind=('unavailable' if image_id in unavailable else 'none_false_positive' if error['expected']=='NONE' else
              ('candidate_withheld' if 'NONE' in actual else 'candidate_other') if item['matches'] else
              'context_mixed' if any(any(token in reason for token in ('review_order','manufactur','context')) for reason in item['reasons']) else 'candidate_absent')
        categories[kind]+=1;field_counts[kind]+=len(error['fields'])
        cases.append(dict(error,category=kind,matching_candidate_evidence=item['matches'],
            selection_reasons=sorted(set(item['reasons'])),numeric_observations=item['observations'][:12],
            diagnosis_status='Evidence triage, not visually confirmed root cause',additional_training_authorized=False))
    assert sum(field_counts.values())==metrics['field_total']-metrics['field_correct']
    analysis=dict(round=number,categories=dict(categories),wrong_fields_by_category=dict(field_counts),cases=cases,
        baseline=dict(path=str(baseline),sha256=digest(baseline),field_correct=previous['field_correct'],
            scope='Prior adopted-model output, rescored with identical current labels; historical report unchanged'),
        field_gains=sum(len(c['gained']) for c in changes),field_losses=sum(len(c['lost']) for c in changes),changes=changes,
        source_report_sha256=digest(folder/'report.json'),trace_sha256=digest(trace) if trace.exists() else None,
        original_images_rerun=False,independent_final_score=False)
    write(target,analysis)
    lines=['## 기존 채택 모델 대비 및 오답 검토',
        f"같은 최신 정답으로 기존 출력만 다시 계산한 기준 {previous['field_correct']}/{metrics['field_total']} → 이번 {metrics['field_correct']}/{metrics['field_total']}. 획득 {analysis['field_gains']}필드, 손실 {analysis['field_losses']}필드. 과거 성적·시간 판정은 덮어쓰지 않았습니다.",
        '| 관측 유형 | 원본 수 | 오답 필드 | 코드·파이프라인 해결 방향 | 추가 학습 판단 |','|---|---:|---:|---|---|']
    for key,count in categories.items():
        title,code,training=ROUTES[key];lines.append(f'| {title} | {count} | {field_counts[key]} | {code} | {training} |')
    lines+=['','이 유형은 저장 trace의 조사 경로이며 전 건의 구조적 원인을 확정한 시각 검증이 아닙니다. 정답 후보 존재만으로 코드 결함을 단정하지 않으며, 후보 미관측을 모두 학습 부족으로 분류하지 않습니다.',
        '후속 원본 학습안: 오답 원본과 승인 crop 전사를 먼저 대조하고, 기존 optimizer/검증 상품 그룹 역할을 유지합니다. 검증 원본은 optimizer로 옮기지 않습니다. 저장 증강본은 제외하며, 누적 재학습은 새 사용자 피드백·승인과 별도 설정 검토 후에만 진행합니다. 이번 실행은 추가 학습을 수행하지 않았습니다.',
        '이번 비교는 코드 개선과 1 epoch 학습이 함께 바뀐 누적 개발 평가이므로 각각의 효과를 분리한 실험은 아닙니다.',f'원본별 득실·후보 trace 위치·출력 근거: `{target}`.']
    path=REPORTS/f'round_{number:02d}.md'
    with path.open('a',encoding='utf-8') as stream:stream.write('\n'+'\n\n'.join(lines)+'\n')
    print(json.dumps(dict(round=number,field_correct=metrics['field_correct'],gains=analysis['field_gains'],losses=analysis['field_losses'],categories=dict(categories)),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--round',type=int,choices=COUNTS,required=True)
    analyze(parser.parse_args().round)
