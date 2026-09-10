import unittest
from scripts.evaluate_pipeline import score_predictions


class EvaluationTest(unittest.TestCase):
    def test_failure_ids_use_the_same_normalization_as_predictions(self):
        report = score_predictions({'000001': {'정답 날짜':'NONE','라벨 상태':'manual'}},
                                   [{'image_id':'000001','final_date':'NONE'}], [{'image_id':'1'}])
        self.assertEqual(report['exact_matches'],0)
        self.assertEqual(report['error_type_counts'],{'실행 오류':1})

    def test_none_runtime_failure_is_not_correct(self):
        report = score_predictions({'000001': {'정답 날짜':'NONE','라벨 상태':'manual'}},
                                   [{'image_id':'000001','final_date':'NONE'}], [{'image_id':'000001'}])
        self.assertEqual(report['exact_matches'],0)
        self.assertEqual(report['error_type_counts'],{'실행 오류':1})

    def test_partial_and_missing_prediction_counts(self):
        report = score_predictions({key:{'정답 날짜':'NONE-02-14','라벨 상태':'manual'} for key in ('000001','000002')},
                                   [{'image_id':'1','final_date':'NONE-02-14'}], [])
        self.assertEqual(report['categories']['partial'],{'total':2,'correct':1})
        self.assertEqual(report['exact_match_rate'], .5)
        self.assertFalse(report['accuracy_target_met'])
        self.assertEqual(report['labels_without_predictions'],['000002'])

    def test_input_scope_is_independent_of_returned_predictions(self):
        labels = {key:{'정답 날짜':'NONE','라벨 상태':'manual'} for key in ('000001','000002','000003')}
        report = score_predictions(labels, [{'image_id':'1','final_date':'NONE'}], [], expected_ids=['1','2'])
        self.assertEqual(report['evaluated_labels'], 2)
        self.assertEqual(report['labels_without_predictions'], ['000002'])

    def test_no_labels_and_duplicates_fail_loudly(self):
        with self.assertRaises(ValueError):
            score_predictions({}, [{'image_id':'1','final_date':'NONE'}], [])
        with self.assertRaises(ValueError):
            score_predictions({}, [{'image_id':'1','final_date':'NONE'}, {'image_id':'000001','final_date':'NONE'}], [])
