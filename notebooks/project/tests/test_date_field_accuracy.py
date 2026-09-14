import unittest
from scripts.evaluate_pipeline import score_predictions
from src.date_fields import fields_from_date, serialize_fields, compliant_row
from scripts.grouped_review import evaluation_gate


class FieldAccuracyTests(unittest.TestCase):
    def test_500_images_1425_fields_is_95_percent(self):
        labels={f'x{i}':{'정답 날짜':'2026-05-29','라벨 상태':'approved'} for i in range(500)}
        rows=[dict(image_id=f'x{i}',**fields_from_date('2026-05-28' if i<75 else '2026-05-29')) for i in range(500)]
        report=score_predictions(labels,rows,[],expected_ids=list(labels))
        self.assertEqual((report['field_correct'],report['field_total']), (1425,1500))
        self.assertEqual(report['field_accuracy'],.95)
        self.assertTrue(report['accuracy_target_met'])
        self.assertEqual(report['exact_match_rate'],.85)

    def test_fields_are_not_reconstructed_from_final_date(self):
        report=score_predictions({'x':{'정답 날짜':'2026-05-29','라벨 상태':'approved'}},
            [dict(image_id='x',year='2026',month='05',day='NONE',final_date='NONE')],[])
        self.assertEqual(report['field_correct'],2)
        self.assertTrue(report['submission_format']['all_rows_compliant'])

    def test_one_malformed_field_does_not_erase_other_two(self):
        report=score_predictions({'x':{'정답 날짜':'2026-05-29','라벨 상태':'approved'}},
            [dict(image_id='x',year='2026',month='05',day='bad',final_date='NONE')],[])
        self.assertEqual(report['field_correct'],2)
        self.assertFalse(report['submission_format']['all_rows_compliant'])

    def test_missing_failed_and_unlabelled_stay_in_denominator(self):
        labels={'x':{'정답 날짜':'NONE','라벨 상태':'approved'}}
        report=score_predictions(labels,[dict(image_id='x',**fields_from_date(None))],[dict(image_id='x')],expected_ids=['x','y'])
        self.assertEqual((report['field_correct'],report['field_total']),(0,6))

    def test_all_eight_field_masks_roundtrip(self):
        for mask in range(8):
            fields={k:v if mask & (1<<i) else 'NONE' for i,(k,v) in enumerate(zip(('year','month','day'),('2026','05','29')))}
            row=serialize_fields(fields)
            self.assertEqual(fields_from_date(row['final_date']),row)
            self.assertTrue(compliant_row(dict(image_id='x',**row)))

    def test_field_regression_blocks_candidate(self):
        r=dict(ids=['x'],metrics=dict(errors=[],field_results={'x':{'year':True,'month':False,'day':True}},submission_format=dict(all_rows_compliant=True)),runtime=dict(status='completed',failures=[]))
        gate=evaluation_gate([r],[],['x:month'])
        self.assertEqual(gate['field_regressions'],['x:month'])
        self.assertFalse(gate['eligible'])
