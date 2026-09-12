"""Verify current pixels and approved snapshot before further split work."""
from collections import Counter
from scripts import ocr_annotations as ann

def main():
    base=ann.ROOT/'학습 및 테스트 결과'
    inventory=ann.read(base/'00_protocol/dataset_inventory.json')
    errors=[];hashes=[];test_matches=0
    for i,path in enumerate(sorted((ann.OUT/'records').glob('*.json'))):
        r=ann.read(path);current=ann.sha(ann.source_path(r));hashes.append(current)
        if current!=r['image_sha256']:errors.append(r['image_id'])
        if i%500==0:print('pixel_hashes',i,flush=True)
    # The stage-1 inventory binds the test copy to the same asset. Retain explicit
    # provenance wording rather than claiming a new test-directory byte scan.
    for r in inventory['images']:
        if r['selected_for_training'] and r['test_image_id']:test_matches+=1
    report=dict(current_images_verified=len(hashes),changed_image_ids=errors,
        exact_duplicate_hashes=sum(n>1 for n in Counter(hashes).values()),
        stage1_inventory_training_test_overlap=test_matches,
        test_overlap_basis='stage1 verified inventory, not a new byte scan of the test directory',
        created_at=ann.now())
    ann.write(base/'04_group_review/input_verification.json',report)
    print(report)
    if errors or len(hashes)!=2610:raise SystemExit(1)

if __name__=='__main__':main()
