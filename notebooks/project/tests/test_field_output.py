import unittest
from dataclasses import replace
from src.date_extraction import OCRLine, DateContext, select_date, submission_fields, selection_fields
from src.budget_pipeline import output_selection


class FieldOutputTest(unittest.TestCase):
    def test_known_year_survives_ambiguous_month_day_order(self):
        s=select_date([OCRLine('01.07.2023',.99,(0,0,300,40))],context=DateContext())
        self.assertEqual(output_selection(s).final_date,'2023-NONE-NONE')

    def test_partial_is_not_deleted_because_it_was_recovered(self):
        s=select_date([OCRLine('소비기한 2026.05',.99,(0,0,300,40))],context=DateContext())
        result=output_selection(s)
        self.assertEqual(selection_fields(result)['year'],'2026')
        self.assertEqual(selection_fields(result)['month'],'05')

    def test_all_partial_masks_are_representable(self):
        for value in ('2026-NONE-NONE','NONE-05-NONE','NONE-NONE-29','2026-NONE-29'):
            self.assertEqual(submission_fields(value)['final_date'],value)

    def test_full_observation_is_not_erased_by_matching_fragment(self):
        s=select_date([OCRLine('소비기한 2026.05.29',.99,(0,0,300,40))],context=DateContext())
        old=output_selection(s)
        fragment=replace(s,final_date='2026-05-NONE',reason='printed-month-year')
        self.assertEqual(output_selection(fragment,previous=old).final_date,'2026-05-29')

    def test_unrelated_partial_cannot_steal_fields_from_previous_date(self):
        s=select_date([OCRLine('소비기한 2026.05.29',.99,(0,0,300,40))],context=DateContext())
        fragment=replace(s,final_date='2027-06-NONE',reason='printed-month-year')
        self.assertEqual(output_selection(fragment,previous=output_selection(s)).final_date,'2027-06-NONE')

    def test_partial_field_survives_disappearance_from_candidate_list(self):
        old=output_selection(select_date([OCRLine('소비기한 2026.05',.99,(0,0,300,40))],context=DateContext()))
        missing=replace(old,final_date=None,output_fields=None,candidates=(),reason='no-valid-date')
        self.assertEqual(output_selection(missing,previous=old).final_date,old.final_date)

    def test_full_date_survives_unresolved_recovery(self):
        old=output_selection(select_date([OCRLine('소비기한 2026.05.29',.99,(0,0,300,40))],context=DateContext()))
        missing=replace(old,final_date=None,output_fields=None,candidates=(),reason='ambiguous',confident=False)
        self.assertEqual(output_selection(missing,previous=old).final_date,old.final_date)

    def test_explicit_negative_role_retracts_old_date(self):
        old=output_selection(select_date([OCRLine('소비기한 2026.05.29',.99,(0,0,300,40))],context=DateContext()))
        rejected=replace(old,final_date=None,output_fields=None,candidates=(),reason='negative-context',confident=False)
        self.assertIsNone(output_selection(rejected,previous=old).final_date)

    def test_new_matching_fields_can_complete_partial_without_synthetic_date(self):
        old=output_selection(select_date([OCRLine('소비기한 2026.05',.99,(0,0,300,40))],context=DateContext()))
        full=select_date([OCRLine('소비기한 2026.05.29',.99,(0,0,300,40))],context=DateContext())
        self.assertEqual(output_selection(full,previous=old).final_date,'2026-05-29')

    def test_disjoint_partial_observations_are_not_joined_without_anchor(self):
        s=select_date([OCRLine('소비기한 2026.05.29',.99,(0,0,300,40))],context=DateContext())
        old=output_selection(replace(s,final_date='2026-NONE-NONE',reason='printed-month-year'))
        new=replace(s,final_date='NONE-06-NONE',reason='printed-month-year')
        self.assertEqual(output_selection(new,previous=old).final_date,'NONE-06-NONE')

    def test_retention_cannot_create_an_invalid_calendar_date(self):
        s=select_date([OCRLine('소비기한 2024.02.29',.99,(0,0,300,40))],context=DateContext())
        old=output_selection(replace(s,final_date='NONE-02-29',reason='printed-month-year'))
        new=replace(s,final_date='2025-02-NONE',reason='printed-month-year')
        self.assertEqual(output_selection(new,previous=old).final_date,'2025-02-NONE')
