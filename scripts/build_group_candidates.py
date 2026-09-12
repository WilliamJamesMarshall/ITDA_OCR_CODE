"""Visual-neighbour shortlist only, not product identities or fold assignments."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ocr_annotations as ann


def main():
    rows=[]
    cache=ann.OUT/'visual_signatures.json'
    signatures=ann.read(cache) if cache.exists() else {}
    for path in sorted((ann.OUT/'records').glob('*.json')):
        record=ann.read(path)
        key=record['image_sha256']
        if key not in signatures:
            with ann.Image.open(ann.source_path(record)) as image:
                pixels=list(image.convert('L').resize((9,8)).getdata())
            bits=[pixels[y*9+x]>pixels[y*9+x+1] for y in range(8) for x in range(8)]
            signatures[key]=sum(int(bit)<<i for i,bit in enumerate(bits))
        rows.append((record,signatures[key]))
    ann.write(cache,signatures)
    result={}
    for record,signature in rows:
        matches=sorted([(int(signature ^ other_signature).bit_count(),other['image_id'])
            for other,other_signature in rows if other['image_id']!=record['image_id']])[:4]
        result[record['image_id']]=dict(
            candidates=[dict(image_id=image_id,dhash_distance=distance) for distance,image_id in matches if distance<=8],
            method='stored_raster_64bit_dhash_distance_le_8',
            warning='시각적으로 비슷한 사진 후보일 뿐 같은 상품으로 확정하지 않음. 후보 없음도 단독 상품 증명이 아님.',
            human_verified=False)
    ann.write(ann.OUT/'group_candidates.json',result)
    print(dict(images=len(result),images_with_neighbours=sum(bool(v['candidates']) for v in result.values()),
               automatic_group_merges=0),flush=True)


if __name__=='__main__':
    main()
