"""Exercise the real epoch adapter on generated text images only, never original data."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from scripts.prepare_sequential_rounds import BASE, digest, write, read

def main():
    import yaml
    from scripts.train_recognition_cpu import CONFIG, CHECKPOINT, DICTIONARY
    from scripts.train_sequential_cpu import main as train
    out = BASE / 'synthetic-runtime-smoke-full-batches'
    if out.exists(): raise ValueError('Synthetic smoke already exists; preserve evidence')
    dest = out / 'rounds/round_01'
    dest.mkdir(parents=True)
    generated = {}
    lists = {}
    for role in ('optimizer_train', 'inner_validation'):
        lines = []
        for i in range(8):
            text = f'2027.07.{i+1:02d}'
            image = Image.new('RGB', (320,48), 'white')
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 30)
            draw.text((8,5), text, font=font, fill='black')
            path = dest / f'{role}_{i}.png'
            image.save(path)
            generated[str(path)] = digest(path)
            lines.append(str(path) + '\t' + text)
        path = dest / (role + '.txt')
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        lists[role] = path
        generated[str(path)] = digest(path)
    config = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    model_dir = out / 'model'
    config['Global'].update(epoch_num=7, pretrained_model=str(CHECKPOINT), character_dict_path=str(DICTIONARY),
                            save_model_dir=str(model_dir), save_res_path=str(out / 'predictions.txt'),
                            print_batch_step=1, save_epoch_step=100, cal_metric_during_train=False)
    config['Train']['dataset']['label_file_list'] = [str(lists['optimizer_train'])]
    config['Eval']['dataset']['label_file_list'] = [str(lists['inner_validation'])]
    config['Train']['sampler'].update(first_bs=2, scales=[[320,48]], fix_bs=True)
    config['Train']['dataset']['transforms'] = [t for t in config['Train']['dataset']['transforms'] if not any(k in t for k in ('RecConAug','RecAug'))]
    config['Eval']['loader']['batch_size_per_card'] = 3
    config_path = out / 'synthetic_config.yml'
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    def require_synthetic(base, number, train_list, validation_list):
        if Path(base) != out or number != 1 or Path(train_list) != lists['optimizer_train'] or Path(validation_list) != lists['inner_validation']:
            raise ValueError('Smoke adapter accepts only its generated lists')
        for path, expected in generated.items():
            if digest(path) != expected or not Path(path).resolve().is_relative_to(out.resolve()):
                raise ValueError('Synthetic fixture changed')
        return {'scope': 'synthetic_test_fixture_not_user_approval'}
    env = {'ITDA_SEQUENTIAL_WORKSPACE': str(out), 'ITDA_SEQUENTIAL_ROUND': '1',
           'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '4'}
    with patch.dict(os.environ, env), patch.object(sys, 'argv', ['synthetic-smoke', '-c', str(config_path)]), \
         patch('scripts.sequential_rounds.require_training_release', require_synthetic):
        train()
    selected = read(model_dir / 'selected_checkpoint.json')
    epochs = sorted(model_dir.glob('validation_epoch_*.json'))
    if len(epochs) < 2 or any(read(p)['metrics']['sample_count'] != 8 for p in epochs):
        raise ValueError('Expected multiple epochs and all eight validation samples, including partial final batch')
    checkpoint = Path(selected['checkpoint'] + '.pdparams')
    if digest(checkpoint) == digest(CHECKPOINT): raise ValueError('Checkpoint did not change')
    write(out / 'result.json', {'status':'passed', 'epochs':len(epochs), 'selected_epoch':selected['epoch'],
          'early_stopped':selected['early_stopped'], 'validation_samples_per_epoch':8,
          'generated_images':16, 'original_images_used':0, 'production_model_changed':False,
          'checkpoint_sha256':digest(checkpoint), 'scope':'Synthetic adapter integration smoke, not round training'})
    print(json.dumps(read(out / 'result.json')))

if __name__ == '__main__': main()
