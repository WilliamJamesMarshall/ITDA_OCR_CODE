"""Publish documentation views; never edits the preserved annotation workspace."""
import hashlib
import json
import os
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'학습 및 테스트 결과'

def main():
    if (ROOT/'notebooks/reports/migration/document_mapping.json').exists():
        raise RuntimeError('Initial document relocation already published; do not rewrite migrated links twice.')
    mapping={}
    for p in (ROOT/'notebooks/docs/architecture').glob('*.md'):
        mapping[ROOT/'docs'/p.name]=p
    for p in BASE.rglob('*.md'):
        parts=p.relative_to(BASE).parts
        if len(parts)>1 and parts[0] not in ('00_protocol','02_annotations','03_existing_705_policy','04_group_review','05_holdout_lock'):
            continue
        section=('protocol' if len(parts)==1 or parts[0]=='00_protocol' else
                 'data' if parts[0]=='02_annotations' else 'evaluation')
        mapping[p]=ROOT/'notebooks/docs'/section/Path(*parts)
    mapping[ROOT/'Harness_README.md']=ROOT/'notebooks/docs/architecture/Harness_README.md'
    records=[]
    # Rewrite relative Markdown link destinations to retain their original targets.
    for old,new in mapping.items():
        source=old if old.exists() else new
        content=source.read_text(encoding='utf-8')
        def link(match):
            target=match.group(1)
            if target.startswith(('https:','http:','#','mailto:')):return match.group(0)
            clean=target.strip('<>');file,sep,anchor=clean.partition('#')
            resolved=Path(os.path.abspath(old.parent/file))
            destination=mapping.get(resolved,resolved)
            relative=os.path.relpath(destination,new.parent).replace('\\','/')
            return '](<'+relative+(sep+anchor if sep else '')+'>)'
        content=re.sub(r'\]\(([^)]+)\)',link,content)
        if old.is_relative_to(BASE):
            content='> 문서 열람용 사본. 계획 수정은 원본 `'+str(old)+'`에서 수행한 뒤 이 도구로 다시 게시합니다. 승인/정답 데이터는 포함하지 않습니다.\n\n'+content
        new.parent.mkdir(parents=True,exist_ok=True)
        new.write_text(content,encoding='utf-8')
        records.append(dict(source=str(old),published=str(new),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    readme=ROOT/'README.md'
    content=readme.read_text(encoding='utf-8')
    content=content.replace('C:/ITDA_OCR_CODE/docs/','notebooks/docs/architecture/')
    content=content.replace('](docs/','](notebooks/docs/architecture/')
    readme.write_text(content,encoding='utf-8')
    for name in ['experiments','reports/baselines','reports/summary','reports/migration',
                 'reports/round_01','reports/round_02','reports/round_03','reports/round_04','reports/round_05_final','docs/training']:
        p=ROOT/'notebooks'/name;p.mkdir(parents=True,exist_ok=True)
        if not (p/'README.md').exists():
            (p/'README.md').write_text('# '+name+'\n\n공개 가능한 문서·집계만 보관합니다. 원본 정답, 이미지, 샘플별 trace, 가중치를 추가하지 않습니다. 최종 fold 결과는 해제 후 게시합니다.\n',encoding='utf-8')
    (ROOT/'notebooks/reports/migration/document_mapping.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Published documents:',len(records))

if __name__=='__main__':main()
