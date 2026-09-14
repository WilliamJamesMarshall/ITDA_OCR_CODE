"""Materialize one reviewable config, without loading a model or starting training."""
import argparse
import copy
import json
from pathlib import Path


def materialize(config, recipe):
    result = copy.deepcopy(config)
    result['Global']['paper_review_status'] = 'pending'
    for key in ('epoch_num','freeze_bn_statistics','paper_train_scope'):
        result['Global'][key] = recipe[key]
    result['Optimizer']['lr'].update(learning_rate=recipe['learning_rate'], warmup_epoch=recipe['warmup_epoch'])
    transforms = result['Train']['dataset']['transforms']
    for op in transforms:
        if 'RecConAug' in op:
            op['RecConAug']['prob'] = recipe['recconaug_prob']
    if recipe['packaging']:
        position = next(i for i,op in enumerate(transforms) if 'RecAug' in op) + 1
        transforms.insert(position, {'PaperPackagingAug': recipe['packaging']})
    # All other architecture, resize, dictionary and eval settings remain intact.
    return result


def main():
    import yaml
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True, type=Path)
    p.add_argument('--recipe', required=True)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    recipes = json.loads(Path(__file__).with_name('training_recipes.json').read_text(encoding='utf-8'))
    result = materialize(yaml.safe_load(a.base.read_text(encoding='utf-8')), recipes['candidates'][a.recipe])
    with a.output.open('x', encoding='utf-8') as stream:
        stream.write('# DRAFT: requires review and execution instruction; not a training approval.\n')
        yaml.safe_dump(result, stream, allow_unicode=True, sort_keys=False)


if __name__ == '__main__':
    main()
