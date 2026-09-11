"""Classify policy transitions without relabelling frozen development truth."""
import json
from pathlib import Path
from collections import Counter

OUT=Path(__file__).resolve().parent


def main():
    summaries={}
    for mode in ('cache','live'):
        data=json.loads((OUT/f'{mode}.json').read_text(encoding='utf8'))
        changed=[]
        for row in data['rows']:
            iid=row.get('image_id',row.get('current_id'))
            before=row['before'] if mode=='cache' else row['before']['value']
            after=row['after'] if mode=='cache' else row['after']['value']
            details=row.get('policy_details') if mode=='cache' else row['after'].get('policy_details')
            if before==after:continue
            changed.append(dict(id=iid,before=before,after=after,expected=row['expected'],
                                gained=before!=row['expected']==after,lost=before==row['expected']!=after,
                                policy_details=details))
        statuses=Counter((r.get('policy_details') if mode=='cache' else r['after'].get('policy_details') or {}).get('status','legacy')
                         for r in data['rows'])
        summaries[mode]=dict(count=data['count'],status_counts=dict(statuses),
                             gained=data['gained'],lost=data['lost'],changes=changed)
    result=dict(note='REVIEW is abstention, not a correct date. Cache and actual OCR have separate denominators.',scopes=summaries)
    (OUT/'policy_transitions.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:{f:v for f,v in value.items() if f!='changes'} for k,value in summaries.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
