import unittest
from unittest.mock import patch
import numpy as np
from src.date_extraction import OCRLine
from src.printed_context_recovery import stroke_views, recover_printed_context


class PrintedContextRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.image=np.full((120,700,3),220,dtype=np.uint8)
        self.quad=((0.,0.),(699.,0.),(699.,119.),(0.,119.))

    def recover(self, readings):
        with patch('src.printed_context_recovery.numeric_region_proposals',return_value=[self.quad]):
            return recover_printed_context(self.image,[],lambda crops:readings)

    def reading(self,text,weak_role=False):
        chars=[.99]*len(text)
        if weak_role:chars[text.index('까')]=.4
        return text,.99,tuple(chars)

    def test_two_supported_views_recover_role_and_date(self):
        added,_,decisions,_=self.recover([self.reading('28.04.24까지'),self.reading('28.04.24까지')])
        self.assertEqual(added[0].text,'28.04.24까지')
        self.assertEqual(decisions[0]['stage'],'printed-stroke-context')

    def test_single_view_role_or_weak_role_is_rejected(self):
        for readings in ([self.reading('28.04.24까지'),self.reading('28.04.24')],
                         [self.reading('28.04.24까지',True),self.reading('28.04.24까지')]):
            self.assertFalse(self.recover(readings)[0])

    def test_conflicting_dates_remain_rejected(self):
        self.assertFalse(self.recover([self.reading('2028.04.24'),self.reading('2029.04.24')])[0])

    def test_only_original_space_polygons_are_proposed(self):
        lines=[OCRLine('28.04.24',.9,(0,0,699,119),variant=name,polygon=self.quad)
               for name in ('original','clahe','geometric-rows','roi-1','rot90')]
        with patch('src.printed_context_recovery.numeric_region_proposals',return_value=[]) as p:
            recover_printed_context(self.image,lines,lambda crops:[])
        self.assertEqual([l.variant for l in p.call_args.args[1]],['original','clahe','geometric-rows'])

    def test_views_have_distinct_sampling_and_invalid_geometry_is_rejected(self):
        views=stroke_views(self.image,self.quad)
        self.assertEqual(len(views),2)
        self.assertNotEqual(views[0][1].shape,views[1][1].shape)
        self.assertEqual(stroke_views(self.image,()),[])

    def test_partial_date_cannot_be_promoted_to_a_full_year(self):
        added,observations,_,_=self.recover([self.reading('10.20까지')]*2)
        self.assertTrue(all('202' not in o.text for o in observations))
        self.assertTrue(all(not o.text.startswith('202') for o in added))


if __name__=='__main__':unittest.main()
