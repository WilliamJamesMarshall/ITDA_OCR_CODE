import unittest
from dataclasses import replace
from unittest.mock import patch
import cv2
import numpy as np
from src.date_extraction import OCRLine, DateContext, select_date
from src.date_region_recovery import _slanted_row_split, recover_geometric_rows
from src.line_recovery import recovery_targets, recover_lines


def reading(text, score=.99):
    return text, score, (score,)*len(text)


class SeamRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((160,600,3),255,dtype=np.uint8)
        self.quad = ((0.,0.),(599.,0.),(599.,159.),(0.,159.))
        self.line = OCRLine('2028.04.24',.99,(0,0,599,159),polygon=self.quad)

    def test_strong_four_digit_year_skips_but_order_or_damaged_token_does_not(self):
        self.assertEqual(recovery_targets([self.line]),[])
        for text in ('28.04.24','2028.0R.24'):
            self.assertEqual(recovery_targets([replace(self.line,text=text)]),[0])
        self.assertEqual(recovery_targets([replace(self.line,score=.95)]),[0])

    def test_phone_and_customer_service_are_not_date_retries(self):
        for text in ('070-1234-5678',')80-024-2311(수신자요금부담)'):
            self.assertEqual(recovery_targets([replace(self.line,text=text,score=.7)]),[])

    def test_slanted_gap_requires_two_substantial_rows(self):
        ink = np.zeros((160,600),dtype=np.uint8)
        for x in range(20,580,24):
            shift=round(x*.04)
            cv2.rectangle(ink,(x,20+shift),(x+13,62+shift),255,-1)
            cv2.rectangle(ink,(x,77+shift),(x+13,126+shift),255,-1)
        self.assertEqual(len(_slanted_row_split(ink,self.quad)),2)
        self.assertEqual(_slanted_row_split(np.zeros_like(ink),self.quad),[self.quad])
        ink[77:]=0
        self.assertEqual(_slanted_row_split(ink,self.quad),[self.quad])

    def test_successful_parent_is_never_split(self):
        with patch('src.date_region_recovery.numeric_region_proposals',return_value=[self.quad]), \
                patch('src.date_region_recovery.dot_row_proposals',return_value=[]), \
                patch('src.date_region_recovery._slanted_row_split') as split:
            added,_,_,_=recover_geometric_rows(self.image,[],lambda crops:[reading('2028.04.24')]*len(crops))
        self.assertEqual(len(added),1)
        split.assert_not_called()

    def test_primary_rectification_requires_stable_character_supported_date(self):
        line=replace(self.line,text='2028.0R.24',score=.7)
        calls=[]
        def recognizer(crops):
            calls.append(len(crops))
            return [reading('noise')]*len(crops) if len(calls)==1 else [reading('2028.04.24')]*len(crops)
        active,_,decisions,_=recover_lines(self.image,[line],recognizer)
        self.assertEqual(active[0].text,'2028.04.24')
        self.assertEqual(calls,[3,2])
        self.assertEqual(decisions[-1]['stage'],'primary-rectified-unparsed')

    def test_partial_date_never_receives_a_year(self):
        result=select_date([OCRLine('10.20까지',.99,(0,0,300,60))],final=True,context=DateContext())
        self.assertEqual(result.final_date,'NONE-10-20')

    def test_same_physical_token_retries_do_not_receive_agreement_bonus(self):
        first=OCRLine('EXP 2028.04.24',.97,(0,0,300,40),original_box=(0,0,300,40))
        copies=[replace(first,variant=name) for name in ('original','clahe','roi')]
        single=select_date([first],final=True,context=DateContext())
        repeated=select_date(copies,final=True,context=DateContext())
        self.assertEqual(single.score,repeated.score)
        self.assertEqual(single.final_date,repeated.final_date)

    def test_distinct_printed_copies_keep_separate_support(self):
        first=OCRLine('EXP 2028.04.24',.97,(0,0,300,40),original_box=(0,0,300,40))
        other=replace(first,box=(0,200,300,240),original_box=(0,200,300,240),variant='other')
        self.assertGreater(select_date([first,other],final=True,context=DateContext()).score,
                           select_date([first],final=True,context=DateContext()).score)


if __name__=='__main__': unittest.main()
