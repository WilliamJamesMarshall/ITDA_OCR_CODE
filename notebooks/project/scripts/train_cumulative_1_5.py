"""One-epoch cumulative 1..5 training. Full-image tests are deliberately absent.

Adapted from the preserved targeted-retrain-code-20260914-v1/train_joint_v2.py.
"""
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
import math
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict

BASE=Path(os.environ['ITDA_CUMULATIVE_RUN']).resolve()
ROOT=Path(os.environ.get('ITDA_ASSET_ROOT', Path(__file__).resolve().parents[3])).resolve()
CODE=BASE/'code'
RELEASE=BASE/'release/release.json'
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','FLAGS_num_threads','FLAGS_paddle_num_threads'):
    os.environ[name]='4'
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
sys.path.insert(0,str(CODE/'notebooks/project'))

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,path)

def validate_config(config):
    global_config=config['Global']
    if (global_config['epoch_num']!=1 or global_config['seed']!=20260911
            or global_config['use_gpu'] or global_config.get('checkpoints')
            or not global_config['freeze_bn_statistics']
            or config['Optimizer']['lr']['learning_rate']!=0.000005):
        raise ValueError('Unapproved diagnostic configuration')
    for section in ('Train','Eval'):
        if config[section]['loader']['num_workers']!=0 or config[section]['loader']['drop_last']:
            raise ValueError('All samples must remain in the fixed loaders')
    if any(any(key in op for key in ('RecAug','RecConAug','MildPrintAug'))
           for op in config['Train']['dataset']['transforms']):
        raise ValueError('This diagnostic has no live augmentation')

def validate_release():
    import yaml
    release=read(RELEASE)
    authorization=read(release['authorization']['path'])
    if (not authorization['online_local_training_allowed'] or authorization['whole_image_test_allowed'] or authorization['external_upload_allowed']
            or authorization['shared_weights_promotion_allowed']):
        raise ValueError('Execution authority mismatch')
    for path,expected in release['protected_files'].items():
        if sha(path)!=expected: raise ValueError('Frozen input changed: '+path)
    config=yaml.safe_load(Path(release['config']).read_text(encoding='utf-8'))
    validate_config(config)
    pool=read(release['pool'])
    if set(pool['admitted'])!=({f'AMLC{i:06d}' for i in range(1,1747)} | {f'BMLC{i:06d}' for i in range(2247,2611)}):
        raise ValueError('Original scope changed')
    for item in pool['admitted'].values():
        original=Path(item['original_path'])
        if original.parent.resolve()!=(ROOT/'학습대상데이터').resolve():
            raise ValueError('Non-original image source')
        if sha(original)!=item['original_sha256'] or sha(item['annotation_path'])!=item['annotation_sha256']:
            raise ValueError('Original or historical annotation changed')
    for sample in pool['samples']:
        item=pool['admitted'][sample['image_id']]
        if (sha(sample['crop_path'])!=sample['crop_sha256']
                or sample['record_sha256']!=item['annotation_sha256']
                or sample['group_id']!=item['group_id']
                or sample['role']!=pool['group_roles'][sample['group_id']]):
            raise ValueError('Crop lineage or permanent group role changed')
    return release,config,pool

def remove_sampler_padding(sampler, expected_count):
    """Remove only repeated padding indices; preserve the seeded sampler order."""
    seen=set();removed=0
    for batch in sampler.batchs_in_one_epoch:
        unique=[]
        for item in batch:
            index=int(item[2])
            if index in seen:
                removed+=1
            else:
                unique.append(item);seen.add(index)
        batch[:]=unique
    if seen!=set(range(expected_count)) or any(not batch for batch in sampler.batchs_in_one_epoch):
        raise RuntimeError('Sampler missing/invalid crop indices')
    return dict(unique_indices=len(seen),removed_padding_indices=removed,
        batch_count=len(sampler.batchs_in_one_epoch),batch_sizes=[len(b) for b in sampler.batchs_in_one_epoch],
        index_order_sha256=hashlib.sha256(json.dumps(sampler.batchs_in_one_epoch,default=str).encode()).hexdigest())

def fingerprint(model):
    digest=hashlib.sha256()
    for name,value in sorted(model.state_dict().items()):
        digest.update(name.encode());digest.update(value.numpy().tobytes())
    return digest.hexdigest()

def main():
    started=time.perf_counter()
    release,config,pool=validate_release()
    output=Path(config['Global']['save_model_dir'])
    output.mkdir(parents=True,exist_ok=False)
    from scripts.operating_environment import limit_cpu,network_probe,executable_paths
    cpu=limit_cpu([0,1,2,3])
    write(output/'environment.json',dict(cpu_affinity=cpu,threads=4,network_mode='online-user-authorized',
        network_probe=network_probe(False),external_upload=False,python=sys.executable,executable_paths=executable_paths()))
    runtime=Path(release['runtime'])
    sys.path.insert(0,str(runtime))
    import paddle
    import tools.program as program
    import tools.train as trainer
    from scripts.frozen_batch_norm import FrozenBatchNormStatistics,validation_gate
    from scripts.train_sequential_cpu import PolicyMetric,WindowsEpochLoader
    from scripts.recognition_metrics import compute_metrics,selection_key
    fields=read(release['fields'])['targets_by_transcription']
    expected=read(release['epoch_zero_reference'])
    previous_train,previous_save=program.train,program.save_model
    context={};metrics={};guard=None;weighted_loss=None
    status=dict(status='initializing',pid=os.getpid(),optimizer_steps=0,epochs_completed=0,
        selected_epoch=0,network_mode='online-user-authorized',cpu_affinity=cpu,threads=4,
        release_sha256=sha(RELEASE),shared_weights_changed=False)
    write(output/'runtime.json',status)
    def evaluate(epoch):
        model=context['model'];guard.assert_unchanged();before=fingerprint(model)
        model.eval();metric=PolicyMetric(fields)
        with paddle.no_grad():
            for batch in context['valid_dataloader']:
                metric(context['post_process_class'](model(batch[0]),batch[1].numpy()))
        values=metric.get_metric()
        if values['sample_count']!=release['scope']['validation_crops'] or fingerprint(model)!=before:
            raise RuntimeError('Missing validation samples or evaluation mutated parameters')
        guard.assert_unchanged()
        digits=asdict(compute_metrics([(''.join(c for c in a if c.isdigit()),''.join(c for c in b if c.isdigit())) for a,b in metric.pairs]))
        candidate=dict(values,epoch=epoch,digit_metrics=digits,checkpoint=str(output/f'epoch_{epoch:03d}'))
        if epoch==0:
            if metric.pairs[:release['round1_validation_count']]!=[tuple(pair) for pair in expected['pairs']]:
                raise RuntimeError('Starting model validation predictions differ from frozen reference')
            reference_metric=PolicyMetric(fields)
            reference_metric.pairs=metric.pairs[:release['round1_validation_count']]
            reference_values=reference_metric.get_metric()
            if reference_values['field_correct']!=expected['metrics']['field_correct'] or reference_values['field_total']!=expected['metrics']['field_total']:
                raise RuntimeError('Epoch-zero round1 subset field metric mismatch')
            status['epoch_zero_reproduced']=True
        metrics[epoch]=candidate
        paddle.save(model.state_dict(),candidate['checkpoint']+'.pdparams')
        write(output/f'validation_{epoch:03d}.json',dict(metrics=candidate,pairs=metric.pairs,
            frozen_bn=guard.evidence(),scope='Joint fixed inner-validation crops, not full-image accuracy'))
        status.update(epochs_completed=epoch,selected_epoch=max(metrics.values(),key=selection_key)['epoch'])
        write(output/'runtime.json',status)
        print(json.dumps(dict(epoch=epoch,field_correct=values['field_correct'],field_total=values['field_total'],
            exact=values['exact_match_count'],micro_cer=values['micro_cer'])),flush=True)
        model.train()
    def train(*args,**kwargs):
        nonlocal guard,weighted_loss
        bound=inspect.signature(previous_train).bind(*args,**kwargs);context.update(bound.arguments)
        model=context['model'];guard=FrozenBatchNormStatistics(model)
        if guard.evidence()['running_tensor_count']!=302: raise RuntimeError('BN tensor count mismatch')
        loader=bound.arguments['train_dataloader']
        sampler_evidence=remove_sampler_padding(loader.batch_sampler, release['scope']['optimizer_crops'])
        write(output/'sampler-evidence.json',sampler_evidence)
        if release.get('weight_manifest'):
            from scripts.weighted_cumulative_loss import weight_manifest,attach_weights,build_weighted_loss
            manifest=read(release['weight_manifest'])
            if json.dumps(manifest,sort_keys=True)!=json.dumps(weight_manifest(pool),sort_keys=True):
                raise RuntimeError('Weighted manifest differs from admitted originals')
            attach_weights(loader.dataset,manifest)
            weighted_loss=build_weighted_loss(manifest,output/'weighted-loss-batches.jsonl')
            bound.arguments['loss_class']=weighted_loss
        if os.name=='nt': bound.arguments['train_dataloader']=WindowsEpochLoader(loader)
        evaluate(0)
        validate_release()
        optimizer=context['optimizer'];old_step=optimizer.step
        def step(*a,**k):
            if not status.get('optimizer_started_at'):
                status['optimizer_started_at']=datetime.now(timezone.utc).isoformat()
                status['status']='optimizer_step_entered'
                write(output/'runtime.json',status)
                print('OPTIMIZER_STARTED '+json.dumps(dict(pid=os.getpid(),time=status['optimizer_started_at'])),flush=True)
            result=old_step(*a,**k)
            guard.assert_unchanged()
            status.update(status='training',optimizer_steps=status['optimizer_steps']+1)
            write(output/'runtime.json',status)
            return result
        optimizer.step=step
        return previous_train(*bound.args,**bound.kwargs)
    def save(*args,**kwargs):
        guard.assert_unchanged();result=previous_save(*args,**kwargs)
        if kwargs.get('prefix')=='latest': evaluate(kwargs['epoch'])
        return result
    program.train,program.save_model=train,save
    sys.argv=[str(Path(__file__)),'-c',release['config']]
    try:
        effective,device,logger,writer=program.preprocess(is_train=True)
        for section in ('Global','Architecture','Optimizer','Train','Eval','Loss','PostProcess'):
            for key,value in config[section].items():
                if effective[section].get(key)!=value: raise ValueError('Runtime config drift: '+section+'.'+key)
        trainer.set_seed(20260911)
        train_started=time.perf_counter();trainer.main(effective,device,logger,writer)
        status['training_and_validation_seconds']=time.perf_counter()-train_started
        if status['epochs_completed']!=1 or status['optimizer_steps']!=math.ceil(release['scope']['optimizer_crops']/8):
            raise RuntimeError('Incomplete joint epoch: actual optimizer steps differ from ceil(N/8)')
        if weighted_loss is not None:
            write(output/'weighted-epoch-audit.json',weighted_loss.finish())
        passed=validation_gate(metrics[1],metrics[0])
        selected=metrics[1] if passed else metrics[0]
        write(output/'selected_checkpoint.json',dict(selected,max_epochs=1,validation_gate_passed=passed,
            scope='internal selection only; whole-image tests held; user adoption required'))
        status.update(validation_gate_passed=passed,selected_epoch=selected['epoch'])
        if passed:
            selected=metrics[1]
            status['selected_epoch']=1
            export=output/'candidate_export'
            with (output/'export.log').open('x',encoding='utf-8') as log:
                subprocess.run([sys.executable,str(runtime/'tools/export_model.py'),'-c',release['config'],'-o',
                    'Global.pretrained_model='+selected['checkpoint'],'Global.checkpoints=null',
                    'Global.save_inference_dir='+str(export),'Global.use_gpu=False'],cwd=ROOT,
                    stdout=log,stderr=subprocess.STDOUT,check=True)
            bundle=output/'candidate_bundle';bundle.mkdir()
            for item in Path(release['bundle']).iterdir():
                if item.name=='korean_PP-OCRv5_mobile_rec': continue
                if item.is_dir(): shutil.copytree(item,bundle/item.name)
                else: shutil.copy2(item,bundle/item.name)
            shutil.copytree(export,bundle/'korean_PP-OCRv5_mobile_rec')
            status['candidate_bundle']=str(bundle)
        validate_release()
        status.update(status='completed',whole_image_evaluation='held_until_separate_user_instruction',frozen_bn=guard.evidence())
    except BaseException as error:
        status.update(status='failed',error=repr(error));raise
    finally:
        status['total_process_seconds']=time.perf_counter()-started
        write(output/'runtime.json',status)
        print(json.dumps(status,ensure_ascii=False),flush=True)

if __name__=='__main__': main()



