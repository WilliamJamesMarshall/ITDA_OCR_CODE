import unittest
from dataclasses import replace

from src.date_extraction import OCRLine, DateContext, select_date, _link_roles
from src.budget_pipeline import output_selection
from src.selective_recovery import actions_for


def selected(*lines):
    return select_date(list(lines), context=DateContext(), final=False)


class SubmissionDecisionTests(unittest.TestCase):
    def test_missing_regions_route_to_detector_but_role_labels_keep_context_route(self):
        self.assertEqual(actions_for(selected(), [])[0], 'secondary')
        lines = [OCRLine('소비기한 별도표기', .99, (0,0,200,30))]
        self.assertEqual(actions_for(selected(*lines), lines)[0], 'context-roi')

    def test_additional_ocr_flag_does_not_delete_supported_date(self):
        decision = selected(OCRLine('2026.07.15', .98, (10, 10, 180, 30)))
        decision = replace(decision, confident=False, reason='ambiguous')
        self.assertEqual(output_selection(decision).final_date, '2026-07-15')

    def test_two_unlabelled_dates_remain_unresolved(self):
        decision = selected(OCRLine('2025.07.15', .98, (10, 10, 180, 30)),
                            OCRLine('2026.07.15', .98, (10, 110, 180, 130)))
        self.assertIsNone(output_selection(decision).final_date)

    def test_role_below_two_separate_columns(self):
        decision = selected(OCRLine('2025.10.03', .98, (10, 10, 160, 30)),
                            OCRLine('2025.12.01', .98, (230, 10, 380, 30)),
                            OCRLine('포장 년,월,일', .98, (10, 36, 160, 56)),
                            OCRLine('소비기한', .98, (240, 36, 370, 56)))
        self.assertEqual(output_selection(decision).final_date, '2025-12-01')

    def test_shared_heading_must_not_choose_one_of_two_columns(self):
        decision = selected(OCRLine('2025.10.03', .98, (10, 10, 160, 30)),
                            OCRLine('2025.12.01', .98, (230, 10, 380, 30)),
                            OCRLine('소비기한', .98, (10, 36, 380, 56)))
        self.assertIsNone(output_selection(decision).final_date)

    def test_manufacturing_only_is_not_expiry(self):
        decision = selected(OCRLine('제조일자: 2025.10.03', .98, (10, 10, 280, 30)))
        self.assertIsNone(output_selection(decision).final_date)

    def test_inline_label_precedes_overlapping_date_above(self):
        decision = selected(OCRLine('등급판정일:2021.03.12', .97, (755,636,1088,685)),
                            OCRLine('유통기한:', .92, (757,672,899,718)),
                            OCRLine('2021.03.18', .99, (928,672,1084,708)))
        self.assertEqual(output_selection(decision).final_date, '2021-03-18')

    def test_clear_digits_with_role_conflict_routes_to_context(self):
        lines = [OCRLine('2025.07.15', .98, (10,10,180,30)),
                 OCRLine('2026.07.15', .98, (10,110,180,130))]
        self.assertEqual(actions_for(selected(*lines), lines)[0], 'context-roi')

    def test_report_and_csv_use_same_decision(self):
        decision = selected(OCRLine('2025.07.15', .98, (10,10,180,30)),
                            OCRLine('2026.07.15', .98, (10,110,180,130)))
        output = output_selection(decision)
        self.assertEqual(output.policy_details['expiration_date'], output.final_date)
        self.assertEqual(output.policy_details['status'], 'REVIEW_REQUIRED')
        self.assertIsNotNone(output.policy_details['candidate_date'])

    def test_vertical_serial_fragment_does_not_inherit_expiry(self):
        lines = [OCRLine('At-Nr: 10679 125 ge', .95, (100,100,440,179)),
                 OCRLine('소비기한', .95, (110,185,320,210))]
        self.assertIsNone(_link_roles(lines)[0].role)

    def test_serial_fragment_does_not_hide_printed_month_year(self):
        decision = selected(OCRLine('10/2022 L0900337 2C41', .97, (467,842,768,879)),
                            OCRLine('At-Nr: 10679 125 ge', .89, (464,998,808,1077)),
                            OCRLine('제품뒷면표시된해당월의1일까지(읽는법:월년순)', .81, (6,1057,242,1085)))
        self.assertEqual(output_selection(decision, base_partial=True).final_date, '2022-10-NONE')


if __name__ == '__main__':
    unittest.main()
