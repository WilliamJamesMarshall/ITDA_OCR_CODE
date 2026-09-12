"""Epoch-end policy evaluation adapter for the pinned, unmodified PaddleOCR runtime."""
import inspect
import os
import sys
from dataclasses import asdict
from pathlib import Path
from scripts.recognition_metrics import compute_metrics, selection_key
from scripts.prepare_sequential_rounds import write

class PolicyMetric:
    main_indicator = 'acc'

    def __init__(self):
        self.pairs = []

    def __call__(self, pred_label, *args, **kwargs):
        predictions, labels = pred_label
        if len(predictions) != len(labels): raise ValueError('Validation predictions/labels differ')
        self.pairs.extend((truth[0], prediction[0]) for prediction, truth in zip(predictions, labels))

    def get_metric(self):
        result = asdict(compute_metrics(self.pairs))
        result['acc'] = result['string_exact_match_rate']
        return result

class StopTraining(Exception):
    pass

class WindowsEpochLoader:
    """Compensate for the pinned trainer's Windows len(loader)-1 cutoff."""
    def __init__(self, loader): self.loader = loader
    def __len__(self): return len(self.loader) + 1
    def __iter__(self): return iter(self.loader)
    def __getattr__(self, name): return getattr(self.loader, name)

def main():
    from scripts.train_recognition_cpu import RUNTIME, CHECKPOINT, SEED
    from scripts.sequential_rounds import require_training_release, round_dir
    base = Path(os.environ['ITDA_SEQUENTIAL_WORKSPACE'])
    number = int(os.environ['ITDA_SEQUENTIAL_ROUND'])
    dest = round_dir(base, number)
    require_training_release(base, number, dest / 'optimizer_train.txt', dest / 'inner_validation.txt')
    sys.path.insert(0, str(RUNTIME))
    import tools.program as program
    import tools.train as trainer
    original_train, original_save = program.train, program.save_model
    selected, context = {}, {}
    stale = 0

    def train(*args, **kwargs):
        bound = inspect.signature(original_train).bind(*args, **kwargs)
        context.update(bound.arguments)
        if os.name == 'nt':
            bound.arguments['train_dataloader'] = WindowsEpochLoader(bound.arguments['train_dataloader'])
        return original_train(*bound.args, **bound.kwargs)

    def save(*args, **kwargs):
        nonlocal stale, selected
        result = original_save(*args, **kwargs)
        if kwargs.get('prefix') != 'latest': return result
        epoch = kwargs['epoch']
        metric = PolicyMetric()
        model = args[0]
        import paddle
        model.eval()
        # The pinned generic Windows evaluator drops its final batch. Recognition
        # must score every validation crop, including a partial final batch.
        with paddle.no_grad():
            for batch in context['valid_dataloader']:
                predictions = model(batch[0])
                metric(context['post_process_class'](predictions, batch[1].numpy()))
        values = metric.get_metric()
        expected = sum(1 for path in context['config']['Eval']['dataset']['label_file_list']
                       for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip())
        if values['sample_count'] != expected: raise ValueError('Validation crops missing or duplicated')
        model.train()
        directory = Path(context['config']['Global']['save_model_dir'])
        candidate = {**values, 'epoch': epoch, 'checkpoint': str(directory / f'policy_epoch_{epoch}')}
        write(directory / f'validation_epoch_{epoch:03d}.json',
              {'metrics': candidate, 'pairs': metric.pairs, 'scope': 'inner_validation_only'})
        improved = not selected or selection_key(candidate) > selection_key(selected)
        if improved:
            selected, stale = candidate, 0
            saved = {**kwargs, 'prefix': f'policy_epoch_{epoch}'}
            original_save(*args, **saved)
        else:
            stale += 1
        write(directory / 'selected_checkpoint.json',
              {**selected, 'patience': 5, 'selection_horizon_epoch': epoch,
               'scope': 'inner_validation_only', 'early_stopped': stale >= 5})
        if stale >= 5: raise StopTraining()
        return result

    program.train, program.save_model = train, save
    config, device, logger, writer = program.preprocess(is_train=True)
    for section, role in [('Train', 'optimizer_train'), ('Eval', 'inner_validation')]:
        if [Path(p).resolve() for p in config[section]['dataset']['label_file_list']] != [(dest / (role + '.txt')).resolve()]:
            raise ValueError('Runtime training list override rejected')
    global_config = config['Global']
    if (global_config['use_gpu'] or global_config['seed'] != SEED or global_config.get('checkpoints')
            or Path(global_config['pretrained_model']).resolve() != CHECKPOINT.resolve()):
        raise ValueError('Runtime initial checkpoint/CPU/seed override rejected')
    # Evaluate exactly once at epoch end through the save hook, using policy metrics.
    config['Global']['eval_batch_step'] = [10**12, 10**12]
    config['Global'].pop('eval_batch_epoch', None)
    trainer.set_seed(config['Global']['seed'])
    try:
        trainer.main(config, device, logger, writer)
    except StopTraining:
        logger.info('Policy patience=5 reached; selected checkpoint preserved')
    if not selected: raise RuntimeError('No internal validation checkpoint selected')

if __name__ == '__main__': main()
