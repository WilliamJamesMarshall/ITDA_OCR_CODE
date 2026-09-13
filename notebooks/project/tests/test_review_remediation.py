import unittest
from src.date_extraction import OCRLine, DateContext, select_date
from src.line_recovery import _apply_views


class ReviewRemediationTests(unittest.TestCase):
    def test_remote_format_across_mapped_passes(self):
        from dataclasses import replace
        digit=OCRLine('22.11.26',.99,(0,0,300,30),original_box=(100,100,400,130))
        hint=OCRLine('소비기한 뚜껑 옆면 표시일까지(일/월/년)',.99,(0,0,600,40),variant='roi',original_box=(100,1500,700,1540))
        self.assertEqual(select_date([digit,hint],final=True,context=DateContext()).final_date,'2026-11-22')
        self.assertIsNone(select_date([digit,replace(hint,original_box=None)],final=True,context=DateContext()).final_date)

    def test_printed_ed_pd_roles_choose_expiry(self):
        result=select_date([OCRLine('PD 28.04.2025',.99,(0,45,500,80)),
                            OCRLine('ED 27.04.2026',.99,(0,0,500,35))],final=True,context=DateContext())
        self.assertEqual(result.final_date,'2026-04-27')

    def test_unresolved_order_keeps_seeking_evidence(self):
        result = select_date([OCRLine('22.11.26', .99, (0, 0, 300, 30))], context=DateContext())
        self.assertIsNone(result.final_date)
        self.assertFalse(result.stop_ocr)

    def test_lid_reference_links_distant_format(self):
        result = select_date([
            OCRLine('22.11.26', .99, (100, 100, 400, 130)),
            OCRLine('소비기한 뚜껑 옆면 표시일까지(일/월/년)', .99, (100, 1500, 700, 1540)),
        ], final=True, context=DateContext())
        self.assertEqual(result.final_date, '2026-11-22')

    def test_complementary_digit_evidence_recovers_exact_repeat(self):
        old = OCRLine('126.14.2', .7, (0, 0, 300, 40))
        scores = [(.99, .67, .88, .99, .9, .81, .69, .5, .95, .97),
                  (.99, .90, .53, .98, .79, .84, .92, .97, .99, .79)]
        from src.line_recovery import _digit_evidence
        observations = []
        for i, chars in enumerate(scores):
            mean, minimum = _digit_evidence('2026.04.23', chars)
            observations.append(OCRLine('2026.04.23', [.839, .874][i], old.box,
                character_scores=chars, date_digit_score=mean, date_digit_min_score=minimum))
        active = [old]
        result = _apply_views(active, [old], [old], [(0, 'a', old.box), (0, 'b', old.box)], observations, strict=True)
        self.assertEqual(result[0]['accepted_text'], '2026.04.23')
        self.assertLess(active[0].score, .85)  # no agreement confidence bonus
        # A digit weak in BOTH views must still be rejected.
        from dataclasses import replace
        weak = [replace(o, character_scores=(.1,) + o.character_scores[1:]) for o in observations]
        active = [old]
        self.assertIsNone(_apply_views(active, [old], [old], [(0,'a',old.box),(0,'b',old.box)], weak, strict=True)[0]['accepted_text'])
