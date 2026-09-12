import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.date_extraction import OCRLine, select_date
from src.line_recovery import _flat_label_rows, recover_missing_rows
from src.pipeline import PipelineConfig, predict_image


def reading(text,score=.96,digit=.98):
    return text,score,tuple(digit for _ in text)


class FlatRowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.image=np.full((160,500,3),220,dtype=np.uint8)
        self.labels=[OCRLine('부터',.99,(350,60,390,90)),OCRLine('까지',.99,(350,95,390,125))]
        self.boxes=[(60,70,300,85),(60,100,325,116)]

    def recover(self,results,labels=None):
        with patch('src.line_recovery._flat_label_rows',return_value=self.boxes):
            return recover_missing_rows(self.image,self.labels if labels is None else labels,lambda crops:results)

    def test_two_rows_resolve_order_from_roles_without_digit_substitution(self):
        new,obs,decisions,_=self.recover([reading('20.08.27')]*2+[reading('21.05.26P'),reading('21.05.26F')])
        self.assertEqual(len(new),2)
        self.assertEqual(len(obs),4)
        self.assertTrue(all(d['accepted_text'] for d in decisions))
        result=select_date([*self.labels,*new])
        self.assertEqual(result.final_date,'2021-05-26')
        self.assertTrue(result.order_resolved)
        self.assertEqual(result.candidates[0].order_reason,'labelled_date_pair')
        self.assertEqual(new[1].box,self.boxes[1])

    def test_one_unstable_row_rejects_whole_block(self):
        new,_,decisions,_=self.recover([reading('20.08.27')]*2+[reading('21.05.26'),reading('21.05.28')])
        self.assertEqual(new,[])
        self.assertTrue(all(d['accepted_text'] is None for d in decisions))

    def test_missing_or_weak_character_evidence_rejected(self):
        for result in [('20.08.27',.99),reading('20.08.27',digit=.6),reading('20.08.27',score=.7)]:
            new,_,_,_=self.recover([result]*4)
            self.assertEqual(new,[])

    def test_same_model_votes_never_inflate_confidence(self):
        new,_,_,_=self.recover([reading('20.08.27',.9),reading('20.08.27',.99)]+[reading('21.05.26',.94)]*2)
        self.assertEqual(new[0].score,.9)

    def test_multiple_labels_existing_dates_and_prose_do_not_trigger(self):
        for labels in [self.labels+[self.labels[1]],self.labels+[OCRLine('2026.09.20',.99,(0,0,200,30))],
                       [OCRLine('상단까지 확인',.99,(350,95,390,125))]]:
            self.assertEqual(self.recover([],labels)[0],[])

    def test_result_count_mismatch_is_error(self):
        with self.assertRaises(ValueError):self.recover([])

    def test_single_row_does_not_force_year_first(self):
        self.boxes=self.boxes[1:]
        new,_,_,_=self.recover([reading('21.05.26')]*2,[self.labels[1]])
        result=select_date([self.labels[1],*new])
        self.assertEqual(result.final_date,'2026-05-21')
        self.assertFalse(result.order_resolved)

    def test_digit_substitution_cannot_supply_missing_row_evidence(self):
        new,_,_,_=self.recover([reading('2O.08.27')]*2+[reading('21.05.26')]*2)
        self.assertEqual(new,[])

    def test_pixel_rows_are_bounded_and_three_rows_are_ambiguous(self):
        image=np.zeros((200,600,3),dtype=np.uint8)
        image[50:175,80:390]=240
        label=OCRLine('까지',.99,(420,120,460,150))
        for y in (90,120):
            for x in range(110,350,15):
                cv2.rectangle(image,(x,y),(x+5,y+9),(20,20,20),-1)
        boxes=_flat_label_rows(image,label)
        self.assertEqual(len(boxes),2)
        self.assertTrue(all(0<=b[0]<b[2]<=600 and 0<=b[1]<b[3]<=200 for b in boxes))
        for x in range(110,350,15):cv2.rectangle(image,(x,150),(x+5,159),(20,20,20),-1)
        self.assertEqual(_flat_label_rows(image,label),[])

    def test_masked_projection_keeps_two_dot_rows_across_input_scales(self):
        image=np.zeros((200,600,3),dtype=np.uint8)
        image[50:175,80:390]=240
        label=OCRLine('까지',.99,(420,120,460,150))
        for y in (90,120):
            for x in range(110,350,15):
                for dy in (0,3,6,9):
                    cv2.rectangle(image,(x,y+dy),(x+5,y+dy+1),(20,20,20),-1)
        for factor in (1,4):
            resized=cv2.resize(image,None,fx=factor,fy=factor,interpolation=cv2.INTER_NEAREST)
            scaled=OCRLine(label.text,label.score,tuple(v*factor for v in label.box))
            self.assertEqual(len(_flat_label_rows(resized,scaled,masked=True)),2)

    def test_pipeline_recovers_missing_block_and_stops_full_image_retries(self):
        labels=self.labels
        class Backend:
            def recognize(self,image,**kwargs):return labels if kwargs['variant']=='original' else []
            def recognize_crops(self,crops):return [reading('20.08.27')]*2+[reading('21.05.26F')]*2
        with patch('src.pipeline._load_bgr',return_value=self.image),patch('src.line_recovery._flat_label_rows',return_value=self.boxes):
            result=predict_image(Path('sample.jpg'),Backend(),PipelineConfig())
        self.assertEqual(result.final_date,'2021-05-26')
        self.assertEqual(result.passes,('mobile:original','mobile:label-roi','recognition-only:label-rows'))
        self.assertEqual(result.trace['summary']['line_recovery_changes'],2)
        self.assertTrue(result.trace['outcomes'][-1]['selection']['candidates'][0]['observation_ids'])

    def test_optional_failure_preserves_full_fallback(self):
        labels=self.labels
        class Backend:
            def recognize(self,image,**kwargs):
                return [OCRLine('EXP 2026.09.20',.99,(0,0,200,30))] if kwargs['variant']=='clahe' else labels
            def recognize_crops(self,crops):raise RuntimeError('injected')
        with patch('src.pipeline._load_bgr',return_value=self.image),patch('src.line_recovery._flat_label_rows',return_value=self.boxes):
            result=predict_image(Path('sample.jpg'),Backend(),PipelineConfig())
        self.assertEqual(result.final_date,'2026-09-20')
        self.assertEqual(result.trace['summary']['failed_passes'],1)


class PairRetryTests(unittest.TestCase):
    def test_weak_surrounding_manufacturing_prose_does_not_block_pair(self):
        lines=[OCRLine('01.07.2020',.99,(0,100,200,130)),OCRLine('01.07.2023',.99,(0,140,200,170)),
               OCRLine('같은 시설에서 제조하고 있습니다',.6,(0,0,300,40))]
        result=select_date(lines)
        self.assertEqual(result.final_date,'2023-07-01')
        self.assertTrue(result.stop_ocr)

    def test_merged_weak_nondigit_text_not_independent_date_uncertainty(self):
        lines=[OCRLine('01.07.2020',.99,(0,0,200,30)),OCRLine('01.07.2023',.99,(0,40,200,70)),
               OCRLine('email',.6,(220,0,300,30))]
        result=select_date(lines)
        self.assertTrue(result.stop_ocr)
        self.assertEqual(result.final_date,'2023-07-01')

    def test_merged_explicit_manufacturing_conflict_not_ignored(self):
        lines=[OCRLine('01.07.2020',.99,(0,0,200,30)),OCRLine('01.07.2023',.99,(0,40,200,70)),
               OCRLine('MFG',.6,(220,40,300,70))]
        self.assertFalse(select_date(lines).stop_ocr)

    def test_third_weak_date_prevents_fast_exit(self):
        lines=[OCRLine('01.07.2020',.99,(0,0,200,30)),OCRLine('01.07.2023',.99,(0,40,200,70)),
               OCRLine('01.07.2022',.6,(220,0,400,30))]
        self.assertFalse(select_date(lines).stop_ocr)


if __name__=='__main__':unittest.main()
