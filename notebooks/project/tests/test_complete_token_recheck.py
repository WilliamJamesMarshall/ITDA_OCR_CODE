import unittest
import numpy as np
from src.date_extraction import OCRLine
from src.line_recovery import recover_lines


class CompleteTokenRecheckTests(unittest.TestCase):
    def run_case(self, secondary):
        image = np.full((100,400,3),180,dtype=np.uint8)
        line = OCRLine('2026.07.03',.96,(10,20,310,60),
                       polygon=((10,20),(310,20),(310,60),(10,60)))
        calls = []
        def fallback(crops):
            calls.append(len(crops))
            if isinstance(secondary, Exception):
                raise secondary
            return secondary
        result = recover_lines(image,[line],lambda crops:[('2026.01.03',.99)]*len(crops),
                               fallback if secondary is not None else None)
        return line, result, calls

    def test_primary_agreement_does_not_skip_cross_recognizer(self):
        text='2026.01.03'
        _,(active,_,decisions,_),calls=self.run_case([(text,.99,(.99,)*len(text))]*2)
        self.assertEqual(calls,[2])
        self.assertEqual(active[0].text,text)
        self.assertIsNone(decisions[0]['accepted_text'])
        self.assertEqual(decisions[0]['decision_basis'],'complete-token-conflict-needs-cross-recognizer')
        self.assertEqual(decisions[-1]['stage'],'rectified-conflict-recheck')

    def test_disagreeing_cross_recognizer_preserves_original(self):
        results=[(text,.99,(.99,)*len(text)) for text in ('2026.01.03','2026.07.03')]
        line,(active,_,_,_),calls=self.run_case(results)
        self.assertEqual(calls,[2])
        self.assertEqual(active[0].text,line.text)

    def test_weak_cross_recognizer_preserves_original(self):
        line,(active,_,_,_),_=self.run_case([('2026.01.03',.6)]*2)
        self.assertEqual(active[0].text,line.text)

    def test_missing_cross_recognizer_preserves_original(self):
        line,(active,_,_,_),_=self.run_case(None)
        self.assertEqual(active[0].text,line.text)

    def test_failed_cross_recognizer_preserves_original(self):
        line,(active,_,decisions,_),_=self.run_case(RuntimeError('injected recognition failure'))
        self.assertEqual(active[0].text,line.text)
        self.assertEqual(decisions[-1]['reason'],'rectified-recognition-error')

    def test_incremental_output_never_emits_unconfirmed_primary_change(self):
        image=np.full((100,400,3),180,dtype=np.uint8)
        line=OCRLine('2026.07.03',.96,(10,20,310,60),polygon=((10,20),(310,20),(310,60),(10,60)))
        commits=[]
        recover_lines(image,[line],lambda crops:[('2026.01.03',.99)]*len(crops),
                      lambda crops:[('2026.07.03',.99,(.99,)*10)]*len(crops),
                      on_progress=lambda active,*args:commits.append(active[0].text))
        self.assertTrue(commits)
        self.assertTrue(all(text==line.text for text in commits))


if __name__=='__main__': unittest.main()
