"""Produce human-readable audit outputs and verify source integrity."""
import json,re,hashlib
from pathlib import Path
from collections import Counter
B=Path(__file__).parent;R=B.parent.parent;S=R/'상품사진입니다'
rows=json.loads((B/'inspection_ledger.json').read_text(encoding='utf-8'))
checks=json.loads((B/'assembly_checks.json').read_text(encoding='utf-8'))
assert not checks['unknown'] and not checks['explicit_conflicts']
assert len(rows)==3352 and {r['image_id'] for r in rows}=={f'{i:06d}' for i in range(1,3353)}
assert not any(r['status']=='pending' for r in rows)
amb=[r for r in rows if r['status']=='ambiguous']
assert all(len(set(r['interpretations'].values()))>=2 for r in amb)
assert all(r['recommendation']=='hold' or r['recommendation'] in r['interpretations'] for r in amb)
assert all((B/'sheets'/f"{r['page']:03d}.jpg").is_file() for r in rows)
for r in rows:
 assert hashlib.sha256((S/r['filename']).read_bytes()).hexdigest()==r['sha256'],r['filename']
def link(p,label):return f'[{label}](<{p.as_posix()}>)'
def write(name,text):(B/name).write_text(text,encoding='utf-8')
names={'ymd':'년월일','mdy':'월일년','dmy':'일월년','hold':'판정보류'}
counts=Counter(r['recommendation'] for r in amb)
def table(rs):
 lines=['| 일련번호 / 원본 | 판독 숫자 | YMD 후보 | MDY 후보 | DMY 후보 | 추천 | 추천 날짜 | 근거 / 제한 |','|---|---|---|---|---|---|---|---|']
 for r in rs:
  d=r['interpretations'];note=r['note'].replace('|','/').replace('\n',' ')
  if r['recommendation']!='hold':note='[문맥 추정·정답 미확정] '+note
  else:note='[보류] '+note
  lines.append('| '+' | '.join([link(S/r['filename'],r['image_id']),r['raw'],d.get('ymd','—'),d.get('mdy','—'),d.get('dmy','—'),names[r['recommendation']],r['recommended_date'] or '자동 결정 금지',note])+' |')
 return '\n'.join(lines)
index=['# 애매한 사진 전체 일련번호','',f'최종 {len(amb)}장 / 원본 3,352장. 날짜 순서 직접 명시·대응 날짜로 확정되는 사진 제외. 동일 상품의 변형 사진도 각각의 파일 번호로 집계.','', '추천은 확정 정답이 아닙니다. 숫자에서 두 개 이상의 서로 다른 날짜가 가능하며, 생산국만으로 자동 확정하지 않았습니다. 컵/캔 바닥처럼 날짜 종류가 불명확한 후보도 누락 방지를 위해 보류 목록에 포함합니다.','',link(B/'판단기준_전수검사보고서.md','판단 기준 및 한계'),'']
for key,name in names.items():
 rs=[r for r in amb if r['recommendation']==key]
 write(f'{name}_일련번호.txt','\n'.join(r['image_id'] for r in rs)+'\n')
 write(f'{name}_사진별_판독표.md',f'# {name}: {len(rs)}장\n\n두 자리 연도는 후보 비교를 위해 2000+YY로 계산했습니다. 추천은 형식 확정이나 식품 섭취 가능성 판정이 아닙니다. —는 해당 형식으로 유효한 달력 날짜가 되지 않음을 뜻합니다.\n\n'+table(rs)+'\n')
 index += [f'## {name}: {len(rs)}장','',link(B/f'{name}_사진별_판독표.md','인쇄 날짜·모든 후보 날짜·근거·원본 링크'),'']
 for start in range(0,len(rs),20):index+= [', '.join(r['image_id'] for r in rs[start:start+20]),'']
write('애매한사진_전체일련번호.md','\n'.join(index))
write('애매한사진_전체일련번호.txt','\n'.join(r['image_id'] for r in amb)+'\n')
write('애매한사진_전체판독표.md','# 모호 날짜 전체 판독표\n\n숫자 순서의 모호성과 문맥상 추천을 분리했습니다. 기한 종류가 보이지 않는 바닥/뚜껑 사진은 기한 자체도 추가 확인해야 합니다.\n\n'+table(amb)+'\n')
excluded=['# 명시적 표기 및 별도 분류 기록','','이 파일은 제외 사유 추적용이며 원본 삭제 목록이 아닙니다. 명시적 형식 126장은 숫자 모양만으로 오인하기 쉬워 따로 기록한 사례입니다. 다른 네 자리 연도·문자 월 등 명확한 사진까지 합한 전체 명시적 날짜 수가 아닙니다.','']
for st,title in [('explicit','형식 안내 또는 대응 날짜 확인'),('partial','부분 일자·연월만 표시 등'),('nonexpiry','제조일·코드·SELL BY 등 별도 대상'),('nonfood','비식품')]:
 rs=[r for r in rows if r['status']==st]
 write(f'{st}_일련번호.txt','\n'.join(r['image_id'] for r in rs)+'\n')
 excluded += [f'## {title}: {len(rs)}장','','| 일련번호 / 원본 | 기록 |','|---|---|']
 for r in rs:excluded.append('| '+link(S/r['filename'],r['image_id'])+' | '+(r['note'] or title).replace('|','/').replace('\n',' ')+' |')
 excluded.append('')
write('명시표기_별도분류_기록.md','\n'.join(excluded))
summary={'source':str(S),'source_count':len(rows),'full_visual_sheet_count':419,'visually_screened_images':len(rows),'zoom_followup_records':sum(r['zoom_review'] for r in rows),'ambiguous_count':len(amb),'ambiguous_percent_of_all':round(len(amb)*100/len(rows),2),'recommended_counts':dict(counts),'status_counts':dict(Counter(r['status'] for r in rows)),'unreviewed_ids':[],'unresolved_processing_queue':[],'recommendations_are_ground_truth':False,'source_sha256_unchanged':True,'century_assumption':'2000 + YY for candidate comparison only'}
write('summary.json',json.dumps(summary,ensure_ascii=False,indent=2))
assert len((B/'애매한사진_전체일련번호.txt').read_text(encoding='utf-8').splitlines())==len(amb)
print(json.dumps(summary,ensure_ascii=False))
