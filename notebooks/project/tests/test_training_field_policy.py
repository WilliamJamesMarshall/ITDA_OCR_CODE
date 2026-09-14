import unittest
from scripts.train_sequential_cpu import PolicyMetric
from scripts.recognition_metrics import selection_key


class TrainingFieldPolicyTest(unittest.TestCase):
    def test_epoch_metric_uses_three_fields(self):
        metric=PolicyMetric({'2026.05.29':dict(year='2026',month='05',day='29')})
        metric(([('2026.05.28',.9)],[('2026.05.29',1.)]))
        result=metric.get_metric()
        self.assertEqual((result['field_correct'],result['field_total']),(2,3))
        self.assertEqual(result['acc'],2/3)
        self.assertEqual(result['string_exact_match_rate'],0)

    def test_field_accuracy_precedes_string_exact(self):
        a=dict(accuracy_policy='date-fields-v1',field_accuracy=.95,string_exact_match_rate=.8,micro_cer=.1,normalized_edit_similarity=.9,epoch=1)
        b=dict(a,field_accuracy=.94,string_exact_match_rate=.9)
        self.assertGreater(selection_key(a),selection_key(b))
        del a['field_accuracy']
        with self.assertRaises(ValueError):selection_key(a)

    def test_unapproved_truth_is_not_invented(self):
        metric=PolicyMetric({})
        metric(([('2026.05.28',.9)],[('2026.05.29',1.)]))
        with self.assertRaises(KeyError):metric.get_metric()
