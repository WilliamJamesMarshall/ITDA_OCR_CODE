import unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path
import numpy as np

from src.date_extraction import OCRLine,select_date,_printed_month_day_token
from src.line_recovery import recover_lines
from src.pipeline import PipelineConfig,predict_image


def row(text,box=(0,0,200,30),score=.99,**kwargs):
    return OCRLine(text,score,box,**kwargs)


class ExplicitOmissionTests(unittest.TestCase):
    def lines(self):
        return [row('제조 2020.04.03',(0,0,250,30)),row('유통기한',(0,80,100,110)),
                row('장기보관이 가능하므로 표기하지 않습니다',(120,80,600,110))]

    def test_explicit_table_omission_stops_not_guessed_from_absence(self):
        result=select_date(self.lines())
        self.assertIsNone(result.final_date)
        self.assertTrue(result.stop_ocr)
        self.assertEqual(result.reason,'expiry-not-printed')

    def test_vertical_table_has_same_contract(self):
        lines=[row('제조 2020.04.03',(0,0,250,30)),row('유통기한',(300,80,330,170)),
               row('표기하지 않습니다',(300,185,330,400))]
        self.assertEqual(select_date(lines).reason,'expiry-not-printed')

    def test_distant_different_frame_weak_or_hypothetical_note_not_used(self):
        for note in [row('표기하지 않습니다',(800,900,1200,930)),row('표기하지 않습니다',(120,80,500,110),variant='other'),
                     row('표기하지 않습니다',(120,80,500,110),score=.6),row('표기하지 않으면 문의하세요',(120,80,500,110))]:
            self.assertNotEqual(select_date(self.lines()[:2]+[note]).reason,'expiry-not-printed')

    def test_printed_full_partial_and_damaged_expiry_prevent_omission_exit(self):
        for extra in [row('EXP 2026.09.20',(0,200,300,230)),row('03.21까지',(0,200,300,230)),
                      row('EXP 20??.09.20',(0,200,300,230))]:
            self.assertNotEqual(select_date(self.lines()+[extra]).reason,'expiry-not-printed')

    def test_manufacturing_heading_not_expiry_omission(self):
        lines=self.lines(); lines[1]=row('제조일자',(0,80,100,110))
        self.assertNotEqual(select_date(lines).reason,'expiry-not-printed')

    def test_unknown_role_date_prevents_omission_exit(self):
        lines=self.lines(); lines[0]=row('2020.04.03')
        self.assertNotEqual(select_date(lines).reason,'expiry-not-printed')


class PartialRecoveryTests(unittest.TestCase):
    def recover(self,text='03.21까지13:51',scores=None):
        original=row('03.2127 13:51',(10,10,300,50),score=.85)
        image=np.zeros((100,400,3),dtype=np.uint8)
        scores=tuple(.97 for _ in text) if scores is None else scores
        return recover_lines(image,[original],lambda crops:[(text,.96,scores)]*len(crops))

    def test_explicit_partial_is_adopted_without_year_from_clock(self):
        active,obs,decisions,_=self.recover()
        self.assertEqual(active[0].text,'03.21까지13:51')
        self.assertTrue(decisions[0]['accepted_text'])
        selection=select_date(active)
        self.assertEqual(selection.final_date,'NONE-03-21')
        self.assertTrue(selection.stop_ocr)

    def test_time_digits_not_date_character_evidence(self):
        text='03.21까지13:51'
        active,_,_,_=self.recover(text,tuple(.97 if i<5 else .2 for i in range(len(text))))
        self.assertAlmostEqual(active[0].date_digit_score,.97)

    def test_no_until_unknown_extra_year_or_invalid_time_not_supported(self):
        for text in ['03.21 13:51','2026.03.21까지','20??.03.21까지','13.21까지','03.21까지29:51','LOT 03.21까지']:
            self.assertIsNone(_printed_month_day_token(text))

    def test_raw_partial_without_recognition_evidence_still_recovers(self):
        result=select_date([row('03.21까지13:51')])
        self.assertEqual(result.final_date,'NONE-03-21')
        self.assertFalse(result.stop_ocr)

    def test_pipeline_partial_recovery_avoids_global_and_tiles(self):
        class Backend:
            def recognize(self,image,**kwargs):return [row('03.2127 13:51',(10,10,300,50),score=.85)]
            def recognize_crops(self,crops):return [('03.21까지13:51',.96,(.97,)*12)]*len(crops)
        with patch('src.pipeline._load_bgr',return_value=np.zeros((100,400,3),dtype=np.uint8)):
            result=predict_image(Path('partial.jpg'),Backend(),PipelineConfig())
        self.assertEqual(result.final_date,'NONE-03-21')
        self.assertEqual(result.passes,('mobile:original','recognition-only:date-lines'))


if __name__=='__main__':unittest.main()
