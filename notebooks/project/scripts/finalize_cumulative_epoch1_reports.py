"""Verify and assemble saved evaluation reports. No inference or training."""
import json
import re
from collections import Counter

from scripts.evaluate_cumulative_epoch1 import RUN, REPORTS, COUNTS, verify_release
from scripts.prepare_sequential_rounds import read, write, digest, csv_read
from scripts.grouped_rounds import original_inputs


def main():
    verify_release()
    summary=read(RUN/'summary.json')
    assert summary['status']=='completed' and summary['field_total']==6330
    analyses=[];reports=[]
    for number,count in COUNTS.items():
        original_inputs(RUN/'control',csv_read(RUN/'control'/f'test_round_{number:02d}.csv'))
        folder=RUN/'evaluation'/f'round_{number:02d}'
        report=read(folder/'report.json');analysis=read(folder/'analysis.json')
        assert report['metrics']['field_total']==3*count
        assert analysis['source_report_sha256']==digest(folder/'report.json')
        assert report['metrics']['field_correct']-analysis['baseline']['field_correct']==analysis['field_gains']-analysis['field_losses']
        reports.append(report);analyses.append(analysis)
    assert sum(r['metrics']['field_correct'] for r in reports)==summary['field_correct']
    before=sum(a['baseline']['field_correct'] for a in analyses)
    gains=sum(a['field_gains'] for a in analyses);losses=sum(a['field_losses'] for a in analyses)
    categories=Counter();fields=Counter()
    for a in analyses:categories.update(a['categories']);fields.update(a['wrong_fields_by_category'])
    assert sum(fields.values())==6330-summary['field_correct']
    result=dict(baseline_fields=before,current_fields=summary['field_correct'],field_total=6330,gains=gains,losses=losses,
        categories=dict(categories),wrong_fields_by_category=dict(fields),model_adopted=False,additional_training=False,
        failed_images=sum(len(r['runtime']['failures']) for r in reports),missing_images=sum(len(r['metrics']['labels_without_predictions']) for r in reports),
        timed_out_rounds=[r['round'] for r in reports if r['runtime']['status']=='timeout'])
    target=RUN/'final-report-audit.json'
    if target.exists():raise FileExistsError(target)
    path=REPORTS/'summary.md'
    text=path.read_text(encoding='utf-8')
    text+='\n## 기존 채택 모델 대비\n\n'
    text+=f"같은 최신 정답 기준 {before}/6330({before/6330:.4%}) → {summary['field_correct']}/6330({summary['field_accuracy']:.4%}). 획득 {gains}필드, 손실 {losses}필드, 순변화 {gains-losses:+d}필드입니다. 과거 보고서 판정은 변경하지 않았습니다.\n\n"
    text+='| 회차 | 기존 필드 | 이번 필드 | 획득 | 손실 | 상세 보고서 |\n|---|---:|---:|---:|---:|---|\n'
    for a,r in zip(analyses,reports):
        n=r['round'];text+=f"| {n} | {a['baseline']['field_correct']} | {r['metrics']['field_correct']} | {a['field_gains']} | {a['field_losses']} | [{n}회](round_{n:02d}.md) |\n"
    text+='\n## 오답 원인과 다음 검토\n\n'
    text+='각 회차 보고서의 유형별 표에서 후보 수용·선택·역할 처리 같은 코드 검토 대상과 검출·잘림·문자인식·파싱 분리 진단 대상을 구분했습니다. 후보가 없다는 이유만으로 전부 추가 학습 문제로 단정하지 않았습니다. 저장 trace 기반의 조사 분류이며 전체 원본에 대한 시각적 원인 확정은 아닙니다.\n\n'
    text+='코드와 학습 모델이 함께 바뀌었으므로 이번 비교만으로 두 효과를 분리할 수 없습니다. 과거와 CPU 병행 조건이 다른 시간 차이 역시 모델 효과로 단정할 수 없습니다. 검증 원본을 학습으로 옮기거나 정답을 다시 바꿔 성적을 올리지 않았습니다.\n\n'
    text+=f"실패 {result['failed_images']}건, 누락 {result['missing_images']}건, 강제 종료 회차 {result['timed_out_rounds']}. 실행 순서와 CPU·메모리·전체 시간은 회차 runtime에 있습니다. 추가 학습·모델 채택·공용 weights 변경·6회 실행·커밋·push는 하지 않았습니다.\n"
    # Formatting-only normalization: Markdown table rows must remain contiguous.
    text=re.sub(r'(?m)^(\|.*\|)\n\n(?=\|)',r'\1\n',text)
    path.write_text(text,encoding='utf-8')
    for number in COUNTS:
        p=REPORTS/f'round_{number:02d}.md'
        text=p.read_text(encoding='utf-8')
        p.write_text(re.sub(r'(?m)^(\|.*\|)\n\n(?=\|)',r'\1\n',text),encoding='utf-8')
    result['files']={str(p):digest(p) for p in sorted(REPORTS.glob('*.md'))}
    result['execution_release_sha256']=digest(RUN/'release.json')
    write(target,result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
