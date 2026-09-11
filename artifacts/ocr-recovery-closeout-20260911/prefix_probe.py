"""Probe label-relative search geometry; selected existing development cases."""
import sys,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src import pipeline
original=pipeline._label_crop_bounds


def bounds(image,lines):
    old=original(image,lines)
    if old is None:return None
    labels=[l for l in lines if l.geometry_valid and l.score>=.9 and l.width>=l.height
            and re.fullmatch(r'까지|소비\s*기한|유통\s*기한|EXP|BBD',l.text,re.I)]
    label=labels[0];h=label.height;height,width=image.shape[:2]
    if label.text=='까지':return old
    result=(max(0,int(label.box[0]-h)),max(0,int(label.box[1]-4*h)),min(width,int(label.box[2]+12*h)),min(height,int(label.box[3]+3*h)))
    reference=[l for l in lines if l.score>=.9 and re.fullmatch(r'상단\s*표시일?까지',l.text)
               and (l.source,l.variant)==(label.source,label.variant)
               and abs(l.center[1]-label.center[1])<h and -h<=l.box[0]-label.box[2]<2*h]
    if reference:return (0,0,width,max(1,int(label.box[1])))
    return result


def main():
    pipeline._label_crop_bounds=bounds
    config=pipeline.PipelineConfig(progress_every=0);backend=pipeline.PaddleOCRBackend(config)
    records=json.loads((OUT/'stopping_only_live.json').read_text(encoding='utf8'))['rows']
    output=[]
    for row in records:
        if row['current_id'] not in {'000210'}:continue
        result=pipeline.predict_image(Path(row['path']),backend,config)
        item=dict(id=row['current_id'],expected=row['expected'],value=result.final_date,seconds=result.elapsed_seconds,passes=result.passes,trace=result.trace)
        output.append(item)
        print(json.dumps({k:v for k,v in item.items() if k!='trace'},ensure_ascii=False),flush=True)
    (OUT/'prefix_probe.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
