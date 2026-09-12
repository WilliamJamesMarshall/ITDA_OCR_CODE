import unittest
from scripts.evaluate_pipeline import score_predictions, assess_targets
from src.date_extraction import submission_fields


def row(key, value):
    return {'image_id': key, **submission_fields(value)}


def label(value):
    return {'정답 날짜': value, '라벨 상태': 'manual'}


class EvaluationTest(unittest.TestCase):
    def test_user_approved_date_labels_are_evaluated(self):
        approved = {'정답 날짜': 'NONE', '라벨 상태': 'approved'}
        report = score_predictions({'000001': approved}, [row('1', None)], [])
        self.assertEqual(report['evaluated_labels'], 1)
        self.assertEqual(report['exact_matches'], 1)
        report = score_predictions({'000001': approved}, [], [])
        self.assertEqual(report['labels_without_predictions'], ['000001'])

    def test_legacy_and_canonical_missing_are_semantically_equal(self):
        for expected in ('NONE', 'NONE-NONE-NONE'):
            for actual in ('NONE', 'NONE-NONE-NONE'):
                prediction = row('1', None)
                prediction['final_date'] = actual
                report = score_predictions({'000001': label(expected)}, [prediction], [])
                self.assertEqual(report['exact_matches'], 1)
                self.assertEqual(report['categories']['none'], {'total': 1, 'correct': 1})
                self.assertEqual(report['submission_format']['all_rows_compliant'], actual == 'NONE')
                self.assertEqual(report['field_metrics']['year']['absent_match_rate'], 1)
                self.assertIsNone(report['field_metrics']['year']['known_match_rate'])

    def test_partial_credit_diagnostics_do_not_change_exact_target(self):
        report = score_predictions({'000001': label('2026-09-05')}, [row('1', '2026-09-06')], [])
        self.assertEqual(report['exact_matches'], 0)
        self.assertFalse(report['accuracy_target_met'])
        self.assertEqual(report['field_metrics']['year']['known_match_rate'], 1)
        self.assertEqual(report['field_metrics']['month']['known_matches'], 1)
        self.assertEqual(report['field_metrics']['day']['known_wrong'], 1)
        self.assertIsNone(report['official_partial_score'])

    def test_partial_missing_spurious_and_unavailable_fields_are_separate(self):
        report = score_predictions({
            '000001': label('2026-09-05'), '000002': label('NONE-02-14'),
            '000003': label('NONE-NONE-NONE'), '000004': label('2026-09-NONE'),
        }, [row('1', '2026-09-NONE'), row('2', '2026-02-14'), row('3', None)], [{'image_id': '3'}])
        day = report['field_metrics']['day']
        self.assertEqual(day['known_missing'], 1)
        self.assertEqual(day['known_matches'], 1)
        self.assertEqual(day['absent_unavailable'], 2)
        self.assertEqual(report['field_metrics']['year']['absent_spurious'], 1)
        self.assertEqual(report['field_metrics']['year']['known_unavailable'], 1)
        self.assertEqual(day['total'], 4)
        self.assertEqual(report['prediction_categories'], {'full': 1, 'partial': 1, 'none': 1, 'invalid': 0})

    def test_invalid_output_is_not_a_missing_date_or_partial_success(self):
        for value in (None, '', '2026-02-30', '20260905', 'NONE-2-14'):
            report = score_predictions({'000001': label('NONE')}, [{'image_id': '1', 'final_date': value}], [])
            self.assertEqual(report['exact_matches'], 0)
            self.assertEqual(report['prediction_categories']['invalid'], 1)
            self.assertEqual(report['field_metrics']['year']['absent_unavailable'], 1)
            self.assertFalse(report['submission_format']['all_rows_compliant'])

    def test_invalid_ground_truth_is_rejected_including_missing_predictions(self):
        for predictions in ([], [row('1', None)]):
            with self.assertRaises(ValueError):
                score_predictions({'000001': label('bad label')}, predictions, [])

    def test_field_denominator_uses_confirmed_scope_and_includes_missing_rows(self):
        report = score_predictions({
            '000001': label('2026-09-05'), '000002': label('2026-09-05'),
            '000003': {'정답 날짜': '2026-09-05', '라벨 상태': 'needs_review'},
            '000004': label('2026-09-05'),
        }, [row('1', '2026-09-05'), row('3', '2026-09-05')], [], expected_ids=['1', '2', '3'])
        self.assertEqual(report['field_metrics']['year']['total'], 2)
        self.assertEqual(report['field_metrics']['year']['known_match_rate'], .5)
        self.assertEqual(report['evaluated_labels'], 2)

    def test_inconsistent_columns_fail_format_gate_not_semantic_comparison(self):
        prediction = row('1', '2026-09-05')
        prediction['day'] = '06'
        report = score_predictions({'000001': label('2026-09-05')}, [prediction], [])
        self.assertEqual(report['exact_match_rate'], 1)
        self.assertEqual(report['submission_format']['final_date_compliant_rate'], 1)
        self.assertFalse(report['submission_format']['all_rows_compliant'])
        result = assess_targets({'images': 1, 'total_elapsed_seconds': 1, 'failures': []}, report)
        self.assertFalse(result['local_relative_joint_target_met'])
        self.assertFalse(result['submission_format_met'])

    def test_column_order_is_part_of_format_compliance(self):
        prediction = row('1', '2026-09-05')
        prediction = dict(reversed(list(prediction.items())))
        report = score_predictions({'000001': label('2026-09-05')}, [prediction], [])
        self.assertEqual(report['exact_matches'], 1)
        self.assertFalse(report['submission_format']['all_rows_compliant'])

    def test_unknown_format_cannot_claim_joint_acceptance(self):
        report = score_predictions({'000001': label('2026-09-05')}, [row('1', '2026-09-05')], [])
        del report['submission_format']
        result = assess_targets({'images': 1, 'total_elapsed_seconds': 1, 'failures': []}, report)
        self.assertIsNone(result['submission_format_met'])
        self.assertFalse(result['local_relative_joint_target_met'])

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
