import unittest
import numpy as np

from src.date_extraction import OCRLine, DateContext, select_date, _link_roles
from src.line_recovery import recover_lines


class EvidenceBoundaryTests(unittest.TestCase):
    def line(self, text, box=(10,20,310,60), score=.98):
        return OCRLine(text,score,box,original_box=box)

    def test_same_date_can_recover_until_without_score_bonus(self):
        original=self.line('25-10-24파지14')
        text='25-10-24까지14'
        active,_,decisions,_=recover_lines(np.zeros((100,400,3),dtype=np.uint8),[original],
                                          lambda crops:[(text,.91,(.99,)*len(text))]*len(crops))
        self.assertEqual(select_date(active,context=DateContext()).final_date,'2025-10-24')
        self.assertLessEqual(active[0].score,original.score)
        self.assertEqual(decisions[0]['change_kind'],'context-only')

    def test_weak_or_conflicting_role_does_not_override_original(self):
        for original,text,scores in [
            ('25-10-24파지14','25-10-24까지14',(.99,)*8+(.2,)*4),
            ('MFG 2026.01.02','EXP 2026.01.02',(.99,)*14),
        ]:
            base=self.line(original)
            active,_,_,_=recover_lines(np.zeros((100,400,3),dtype=np.uint8),[base],
                                       lambda crops:[(text,.98,scores)]*len(crops))
            self.assertEqual(active[0].text,base.text)

    def test_rejected_views_have_auditable_reasons(self):
        text='2026.03.23'
        active,_,decisions,_=recover_lines(np.zeros((100,400,3),dtype=np.uint8),[self.line('2026.0.23m')],
                                          lambda crops:[(text,.9,(.99,)*9+(.3,))]*len(crops))
        self.assertEqual(active[0].text,'2026.0.23m')
        self.assertIn('weak-digit',decisions[0]['evidence'][0]['rejections'])
        self.assertEqual(decisions[0]['decision_basis'],'no-eligible-date')

    def test_bare_six_digit_number_needs_role_or_format(self):
        result=select_date([self.line('801005')],final=True,context=DateContext())
        self.assertIsNone(result.final_date)
        self.assertEqual(result.reason,'review_unanchored_compact')
        self.assertEqual(select_date([self.line('EXP 801005')],final=True,context=DateContext()).final_date,'2080-10-05')

    def test_partial_parse_of_corrupt_date_is_not_a_complete_date(self):
        for text in ['202 6.06.29까지','2027.0B.1ㅂ까지']:
            result=select_date([self.line(text)],final=True,context=DateContext())
            self.assertIsNone(result.final_date,text)

    def test_standalone_ed_pd_are_local_roles_not_digit_repairs(self):
        rows=[self.line('ED',(0,0,50,40)),self.line('27.94.2026',(60,0,350,40)),
              self.line('PD',(0,80,50,120)),self.line('28.04.2025',(60,80,350,120))]
        linked=_link_roles(rows)
        self.assertEqual(linked[1].role,'end')
        self.assertEqual(linked[3].role,'start')
        self.assertNotEqual(select_date(rows,final=True,context=DateContext()).final_date,'2025-04-28')

    def test_explicit_top_reference_links_one_remote_date(self):
        rows=[self.line('28.08.17',(10,10,310,50)),
              self.line('소비기한 상단표기일까지',(10,1000,400,1040))]
        self.assertEqual(select_date(rows,context=DateContext()).final_date,'2028-08-17')
        for extra in [self.line('27.08.17',(10,80,310,120))]:
            self.assertIsNone(select_date([*rows,extra],context=DateContext()).final_date)

    def test_reference_does_not_guess_from_generic_prose_or_wrong_direction(self):
        for label in ['소비기한 별도표기일까지','소비기한 하단표기일까지','제조일 상단표기일까지']:
            self.assertIsNone(select_date([self.line('28.08.17',(10,10,310,50)),
                                          self.line(label,(10,1000,400,1040))],context=DateContext()).final_date)


if __name__=='__main__':unittest.main()
