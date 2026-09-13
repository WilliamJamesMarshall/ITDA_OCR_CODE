import copy
import unittest
from scripts.frozen_batch_norm import FrozenBatchNormStatistics, validation_gate


class FrozenBatchNormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import paddle
        cls.paddle = paddle

    def test_statistics_fixed_across_train_eval_and_optimizer(self):
        p = self.paddle
        p.seed(7)
        model = p.nn.Sequential(p.nn.Conv2D(1, 2, 1), p.nn.BatchNorm2D(2))
        guard = FrozenBatchNormStatistics(model)
        before = model[1].weight.numpy().copy()
        optimizer = p.optimizer.Adam(learning_rate=1e-3, parameters=model.parameters())
        for _ in range(3):
            model.eval()
            with p.no_grad():
                model(p.ones([2, 1, 4, 4]))
            model.train()
            loss = model(p.ones([2, 1, 4, 4]) * 3).square().mean()
            self.assertTrue(model.training)
            self.assertTrue(model[0].training)
            self.assertFalse(model[1].training)
            loss.backward()
            self.assertIsNotNone(model[1].weight.grad)
            self.assertGreater(float(p.abs(model[1].weight.grad).sum()), 0)
            optimizer.step()
            optimizer.clear_grad()
            guard.assert_unchanged()
        self.assertTrue((before != model[1].weight.numpy()).any())
        self.assertEqual(guard.evidence()['running_tensor_count'], 2)

    def test_detects_changed_statistics(self):
        p = self.paddle
        layer = p.nn.BatchNorm1D(2)
        guard = FrozenBatchNormStatistics(layer)
        layer._mean.set_value(p.ones([2]))
        with self.assertRaises(RuntimeError):
            guard.assert_unchanged()

    def test_rejects_missing_or_explicit_batch_statistics(self):
        p = self.paddle
        with self.assertRaises(ValueError):
            FrozenBatchNormStatistics(p.nn.Linear(1, 1))
        with self.assertRaises(ValueError):
            FrozenBatchNormStatistics(p.nn.BatchNorm1D(2, use_global_stats=False))


class ValidationGateTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(sample_count=22, exact_match_count=14, edit_error_count=11,
                         ground_truth_character_count=231, micro_cer=11/231,
                         string_exact_match_rate=14/22, normalized_edit_similarity=.95, epoch=0,
                         digit_metrics=dict(sample_count=22, exact_match_count=19,
                                            edit_error_count=3, ground_truth_character_count=176))

    def test_equal_quality_later_epoch_can_be_evaluated(self):
        candidate = copy.deepcopy(self.base)
        candidate['epoch'] = 1
        self.assertTrue(validation_gate(candidate, self.base))

    def test_each_regression_and_missing_sample_is_rejected(self):
        for scope in (None, 'digit_metrics'):
            for field, change in [('sample_count', -1), ('exact_match_count', -1),
                                  ('edit_error_count', 1), ('ground_truth_character_count', -1)]:
                with self.subTest(scope=scope, field=field):
                    candidate = copy.deepcopy(self.base)
                    (candidate if scope is None else candidate[scope])[field] += change
                    self.assertFalse(validation_gate(candidate, self.base))

    def test_selection_quality_loss_is_rejected(self):
        candidate = copy.deepcopy(self.base)
        candidate['normalized_edit_similarity'] -= .01
        self.assertFalse(validation_gate(candidate, self.base))


if __name__ == '__main__':
    unittest.main()
