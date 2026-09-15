"""Prepare the explicitly approved original-count weighted repeat, without training."""
import copy
import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone
import yaml

from scripts.grouped_rounds import source_lock, model_lock
from scripts.weighted_cumulative_loss import weight_manifest


def main():
    root=Path(__file__).resolve().parents[3]
    old=Path(os.environ['ITDA_CUMULATIVE_PREVIOUS']).resolve()
    run=Path(os.environ['ITDA_CUMULATIVE_RUN']).resolve()
    if run.exists():
        raise FileExistsError('Preserve previous weighted preparation')
    os.environ['ITDA_CUMULATIVE_RUN']=str(old)
    from scripts.train_cumulative_1_5 import validate_release,sha,read
    prior,config,pool=validate_release()
    os.environ['ITDA_CUMULATIVE_RUN']=str(run)
    if prior['scope']['optimizer_crops']!=3316 or prior['scope']['validation_crops']!=25:
        raise ValueError('Approved pool counts changed')
    checkpoint=Path(config['Global']['pretrained_model']+'.pdparams')
    if sha(checkpoint)!='07f23a2059d05d9977969e1f4a8742974376a5e1e47e28f23af7f23f13c611d9':
        raise ValueError('Not the approved adopted starting checkpoint')
    manifest=weight_manifest(pool)
    run.mkdir()
    dest=run/'release';dest.mkdir()
    def write(path,value):
        with path.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
    plan=root/'notebooks/docs/training/cumulative_weighted_originals_20260915/approved_plan.md'
    authorization=dict(actor='user',instruction='시작해.',
        preceding_user_request='각 회차가 학습오차에 기여하는 총 비중을 각 회차의 이미지 데이터 개수 가중평균으로 조정하여 누적학습을 다시 수행하려고 한다. 1회차부터 5회차까지의 누적학습을 다시 수행하는 계획을 정리해서 가져와.',
        source_reference='Current conversation: approval immediately following the original-count weighted training plan',
        recorded_at=datetime.now(timezone.utc).isoformat(),plan_path=str(plan),plan_sha256=sha(plan),
        prior_crop_authorization=prior['authorization'],
        online_local_training_allowed=True,whole_image_test_allowed=False,external_upload_allowed=False,
        shared_weights_promotion_allowed=False,commit_push_allowed=False,
        policy='Previously authorized local online workflow; new run scope is one weighted epoch and inner validation only')
    write(run/'instruction.json',authorization)
    write(dest/'authorization.json',authorization)
    for name in ('pool.json','excluded.json','group_roles.json','optimizer_train.txt','inner_validation.txt'):
        shutil.copy2(old/'release'/name,dest/name)
    write(dest/'weight_manifest.json',manifest)
    output=run/'training-run'
    config=copy.deepcopy(config)
    config['Global'].update(save_model_dir=str(output),save_res_path=str(output/'predicts.txt'))
    for section,name in [('Train','optimizer_train'),('Eval','inner_validation')]:
        config[section]['dataset']['label_file_list']=[str(dest/(name+'.txt'))]
    with (dest/'config.yml').open('x',encoding='utf-8') as stream:
        yaml.safe_dump(config,stream,allow_unicode=True,sort_keys=False)
    snapshot=run/'code'
    code=source_lock(root)
    for rel,digest in code.items():
        target=snapshot/rel;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/rel,target)
        assert sha(target)==digest
    bundle=run/'starting_bundle'
    shutil.copytree(Path(prior['bundle']),bundle)
    assert model_lock(bundle)==model_lock(root/'weights/paddle')
    protected=dict(prior['protected_files'])
    protected[str(old/'release/release.json')]=sha(old/'release/release.json')
    protected.update({str(snapshot/rel):digest for rel,digest in code.items()})
    protected.update({str(p):sha(p) for p in bundle.rglob('*') if p.is_file()})
    runtime=Path(prior['runtime'])
    protected.update({str(p):sha(p) for p in runtime.rglob('*.py') if '.git' not in p.parts})
    for p in [plan,plan.parent/'loader_findings.md',run/'instruction.json',*dest.iterdir()]:
        protected[str(p)]=sha(p)
    release=dict(prior,kind='cumulative-1-5-original-count-weighted-v1',
        authorization=dict(path=str(dest/'authorization.json'),sha256=sha(dest/'authorization.json')),
        pool=str(dest/'pool.json'),config=str(dest/'config.yml'),bundle=str(bundle),
        weight_manifest=str(dest/'weight_manifest.json'),protected_files=protected)
    write(dest/'release.json',release)
    write(dest/'preflight.json',dict(status='prepared_not_training',prior_release_sha256=sha(old/'release/release.json'),
        release_sha256=sha(dest/'release.json'),scope=release['scope'],
        original_sha_and_annotation_sha_verified=2110,crop_sha_and_role_verified=len(pool['samples']),
        excluded_and_group_roles_unchanged=True,shared_model_unchanged=True,
        coefficient_sums=manifest['round_coefficient_sums'],eligible_originals=manifest['eligible_originals']))
    print(json.dumps(dict(run=str(run),release_sha256=sha(dest/'release.json'),
        coefficients=manifest['round_coefficient_sums'],crops=manifest['crop_count']),ensure_ascii=True))


if __name__=='__main__':
    main()
