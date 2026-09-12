import copy
import unittest
from scripts.approve_annotation_drafts import approved_candidate
from tests.test_ocr_annotations import AnnotationTests


class BulkApprovalTests(unittest.TestCase):
    def test_approval_does_not_invent_missing_polygon_or_claim_inspection(self):
        fixture=AnnotationTests()
        fixture.setUp()
        try:
            original=copy.deepcopy(fixture.record)
            candidate,eligible=approved_candidate(original,'snapshot')
            self.assertFalse(eligible)
            self.assertEqual(candidate['user_draft_approval']['status'],'approved')
            self.assertFalse(candidate['user_draft_approval']['individual_visual_inspection_claimed'])
            self.assertEqual(candidate['regions'],original['regions'])
            self.assertEqual(candidate['final_date'],original['final_date'])
        finally:
            fixture.doCleanups()

    def test_complete_draft_can_be_promoted_with_bulk_provenance(self):
        fixture=AnnotationTests()
        fixture.setUp()
        try:
            candidate,eligible=approved_candidate(fixture.checked(),'snapshot')
            self.assertTrue(eligible)
            self.assertEqual(candidate['review']['method'],'explicit_user_bulk_approval')
        finally:
            fixture.doCleanups()
