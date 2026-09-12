import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np

from src.date_extraction import OCRLine,select_date
from src.line_recovery import recover_lines,recover_missing_rows
from src.pipeline import PaddleOCRBackend,PipelineConfig


def reading(text,score=.98,digit=.99):
    return text,score,(digit,)*len(text)


class SecondaryRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.image=np.zeros((100,500,3),dtype=np.uint8)
        self.lines=[OCRLine('EXP 2E.09.20',.95,(10,10,300,40),original_box=(10,10,300,40))]

    def test_secondary_recovers_only_failed_primary_with_raw_scores_preserved(self):
        primary=lambda crops:[reading('2E.09.20')]*len(crops)
        secondary=Mock(side_effect=lambda crops:[reading('26.09.20')]*len(crops))
        active,obs,decisions,_=recover_lines(self.image,self.lines,primary,secondary)
        self.assertEqual(len(secondary.call_args.args[0]),3)
        self.assertEqual(active[0].text,'26.09.20')
        self.assertEqual(active[0].role,'end')
        self.assertEqual(len(obs),6)
        self.assertEqual(obs[-1].score,.98)
        self.assertTrue(obs[-1].variant.endswith('-english'))
        self.assertEqual(select_date(active).final_date,'2020-09-26')  # No YMD override.

    def test_successful_primary_or_clear_original_does_not_load_secondary(self):
        for original in ['EXP 2E.09.20','EXP 26.09.20']:
            secondary=Mock(side_effect=AssertionError('must stay unloaded'))
            recover_lines(self.image,[OCRLine(original,.99,(10,10,300,40))],
                          lambda crops:[reading('26.09.20')]*len(crops),secondary)
            secondary.assert_not_called()

    def test_secondary_needs_strong_aligned_character_evidence(self):
        for result in [reading('26.09.20',digit=.7),('26.09.20',.99,()),reading('26.09.20',score=.6)]:
            active,obs,_,_=recover_lines(self.image,self.lines,
                                        lambda crops:[reading('2E.09.20')]*len(crops),lambda crops:[result]*len(crops))
            self.assertEqual(active[0].text,self.lines[0].text)
            self.assertEqual(obs[-1].score,result[1])  # Rejection never zeroes measured score.

    def test_disagreeing_strong_views_not_adopted(self):
        active,_,_,_=recover_lines(self.image,self.lines,lambda crops:[reading('2E.09.20')]*len(crops),
                                  lambda crops:[reading('26.09.20'),reading('26.09.20'),reading('26.09.28')])
        self.assertEqual(active[0].text,self.lines[0].text)

    def test_failure_keeps_primary_recovery_of_other_row(self):
        rows=self.lines+[OCRLine('EXP 2E.10.20',.9,(10,60,300,90))]
        primary=lambda crops:[reading('26.09.20')]*3+[reading('2E.10.20')]*3
        for secondary in [Mock(side_effect=RuntimeError('offline')),lambda crops:[]]:
            active,obs,decisions,_=recover_lines(self.image,rows,primary,secondary)
            self.assertEqual(active[0].text,'26.09.20')
            self.assertEqual(active[1].text,rows[1].text)
            self.assertEqual(decisions[-1]['reason'],'secondary-recognition-error')
            self.assertIn('error',decisions[-1])

    def test_masked_rows_use_secondary_only_when_primary_geometry_missing(self):
        labels=[OCRLine('부터',.99,(350,10,390,40)),OCRLine('까지',.99,(350,50,390,80))]
        boxes=[(40,15,300,35),(40,55,300,75)]
        secondary=Mock(side_effect=lambda crops:[reading('2020.11.07')]*2+[reading('2021.11.06')]*2)
        with patch('src.line_recovery._flat_label_rows',side_effect=[[],boxes]):
            added,obs,_,_=recover_missing_rows(self.image,labels,Mock(side_effect=AssertionError('no primary crops')),secondary)
        self.assertEqual(len(secondary.call_args.args[0]),4)
        self.assertEqual(select_date([*labels,*added]).final_date,'2021-11-06')
        self.assertTrue(all(o.variant.endswith('-english') for o in obs))

    def test_missing_offline_secondary_weights_cannot_trigger_download(self):
        backend=PaddleOCRBackend.__new__(PaddleOCRBackend)
        backend._date_recognizer=None
        backend.config=PipelineConfig(weights_dir=Path('definitely-absent-model-root'))
        with patch('paddlex.create_model') as factory:
            with self.assertRaises(FileNotFoundError):backend.recognize_date_crops([self.image])
            factory.assert_not_called()

    def test_incomplete_primary_box_does_not_block_full_masked_block(self):
        labels=[OCRLine('부터',.99,(350,10,390,40)),OCRLine('까지',.99,(350,50,390,80))]
        boxes=[(40,15,300,35),(40,55,300,75)]
        with patch('src.line_recovery._flat_label_rows',side_effect=[[boxes[0]],boxes]):
            added,obs,decisions,_=recover_missing_rows(self.image,labels,lambda crops:[reading('garbled')]*len(crops),
                                              lambda crops:[reading('2020.11.07')]*2+[reading('2021.11.06')]*2)
        self.assertEqual(len(obs),6)
        self.assertEqual(len({d['line_index'] for d in decisions}),len(decisions))
        self.assertEqual(select_date([*labels,*added]).final_date,'2021-11-06')


if __name__=='__main__':unittest.main()
