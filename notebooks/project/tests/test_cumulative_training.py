import importlib
import os
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {'ITDA_CUMULATIVE_RUN': 'C:/unused-cumulative-test'}):
    training = importlib.import_module('scripts.train_cumulative_1_5')


class CumulativeTrainingGuardTest(unittest.TestCase):
    def config(self):
        return {'Global': dict(epoch_num=1, seed=20260911, use_gpu=False,
                               checkpoints=None, freeze_bn_statistics=True),
                'Optimizer': {'lr': {'learning_rate': 5e-6}},
                'Train': {'loader': dict(num_workers=0, drop_last=False), 'dataset': {'transforms': []}},
                'Eval': {'loader': dict(num_workers=0, drop_last=False)}}

    def test_only_approved_single_epoch_configuration(self):
        training.validate_config(self.config())
        for field, value in [('epoch_num', 2), ('seed', 1), ('use_gpu', True),
                             ('checkpoints', 'resume'), ('freeze_bn_statistics', False)]:
            config = self.config()
            config['Global'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                training.validate_config(config)

    def test_stored_crop_policy_does_not_enable_live_augmentation(self):
        config = self.config()
        config['Train']['dataset']['transforms'] = [{'RecAug': None}]
        with self.assertRaises(ValueError):
            training.validate_config(config)

    def test_sampler_preserves_remainder_once(self):
        class Sampler:
            batchs_in_one_epoch = [[(320, 48, i, None) for i in range(8)],
                                  [(320, 48, i, None) for i in [8, 0, 1, 2, 3, 4, 5, 6]]]
        evidence = training.remove_sampler_padding(Sampler(), 9)
        self.assertEqual(evidence['batch_sizes'], [8, 1])
        self.assertEqual(evidence['removed_padding_indices'], 7)

    def test_release_rejects_whole_image_authority_before_any_training(self):
        release = {'authorization': {'path': 'authorization.json'}}
        authority = dict(online_local_training_allowed=True, whole_image_test_allowed=True,
                         external_upload_allowed=False, shared_weights_promotion_allowed=False)
        with patch.object(training, 'read', side_effect=[release, authority]), self.assertRaises(ValueError):
            training.validate_release()


if __name__ == '__main__':
    unittest.main()
