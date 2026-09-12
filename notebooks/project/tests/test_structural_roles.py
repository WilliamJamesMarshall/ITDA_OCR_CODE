import unittest
from dataclasses import replace

from src.date_extraction import OCRLine, _link_roles, select_date


def line(text, y=0, **kwargs):
    return OCRLine(text, .98, (0, y, 220, y+20), **kwargs)


class StructuralRoleTests(unittest.TestCase):
    def test_explicit_pair_across_crops_uses_original_coordinates(self):
        rows = [line('MFG 25.09.04',original_box=(800,2000,1600,2200)),
                line('EXP 26.09.03',variant='label-roi',original_box=(800,2230,1600,2430))]
        result=select_date(rows)
        self.assertEqual(result.final_date,'2026-09-03')
        self.assertEqual(result.candidates[0].order_reason,'labelled_date_pair')

    def test_cross_crop_order_does_not_use_local_overlap_as_proof(self):
        for box in [None,(800,8000,1600,8200),(800,2000,1600,2200)]:
            rows=[line('MFG 25.09.04',original_box=(800,2000,1600,2200)),
                  line('EXP 26.09.03',variant='label-roi',original_box=box)]
            self.assertFalse(any(c.order_reason=='labelled_date_pair' for c in select_date(rows,final=True).candidates))

    def test_cross_crop_pair_needs_both_explicit_roles_and_valid_geometry(self):
        start=line('MFG 25.09.04',original_box=(800,2000,1600,2200))
        end=line('EXP 26.09.03',variant='label-roi',original_box=(800,2230,1600,2430))
        for rows in [[replace(start,text='25.09.04'),end],[start,replace(end,geometry_valid=False)],
                     [replace(start,text='MFG 2S.09.04'),end]]:
            self.assertFalse(any(c.order_reason=='labelled_date_pair' for c in select_date(rows,final=True).candidates))

    def test_manufacturing_facility_is_not_date_heading(self):
        result = select_date([line('제조시설에서 제조하였습니다'), line('2026.09.14', 200)], final=True)
        self.assertEqual(result.final_date, '2026-09-14')

    def test_cross_pass_role_requires_same_original_region(self):
        anchor = line('제조일자: 2025.09.26', original_box=(0,0,220,20))
        same = line('2025.09.26', variant='roi', original_box=(0,0,220,20))
        other = line('2026.03.25', 50, variant='roi', original_box=(0,50,220,70))
        roles = _link_roles([anchor,same,other])
        self.assertEqual(roles[1].role, 'start')
        self.assertIsNone(roles[2].role)

    def test_unknown_coordinates_do_not_transfer_role(self):
        self.assertIsNone(_link_roles([line('MFG 2025.09.26'),line('2025.09.26',variant='roi')])[1].role)

    def test_clipped_manufacturing_prefix_preserves_role(self):
        rows = [line('제조2020.04.03',original_box=(400,200,800,270)),
                line('20.04.03',variant='roi',original_box=(600,202,790,268))]
        self.assertEqual(_link_roles(rows)[1].role,'start')
        self.assertIsNone(select_date(rows,final=True).final_date)

    def test_larger_merged_row_does_not_inherit_small_label(self):
        rows = [line('MFG',original_box=(0,0,60,20)),
                line('2025.01.01 2026.01.01',variant='roi',original_box=(0,0,400,20))]
        self.assertIsNone(_link_roles(rows)[1].role)

    def test_conflicting_roles_are_not_silently_chosen(self):
        rows = [line('MFG 2025.09.26',original_box=(0,0,220,20)),
                line('EXP 2025.09.26',variant='roi',original_box=(0,0,220,20))]
        self.assertTrue(all(l.role=='conflict' for l in _link_roles(rows)))
        self.assertIsNone(select_date(rows,final=True).final_date)

    def test_local_unlabelled_three_year_pair(self):
        result = select_date([line('2023.01.01'),line('2026.01.01',30)],final=True)
        self.assertEqual(result.final_date,'2026-01-01')
        self.assertEqual(result.reason,'local-date-pair')

    def test_user_dmy_policy_is_resolved_before_pair_selection(self):
        result = select_date([line('01.07.2020'),line('01.07.2023',30)],final=True)
        self.assertEqual(result.final_date,'2023-07-01')
        self.assertEqual(result.reason,'local-date-pair')
        self.assertFalse(result.order_resolved)

    def test_global_latest_date_is_not_local_pair(self):
        result = select_date([line('2023.01.01'),line('2026.01.01',800)],final=True)
        self.assertNotEqual(result.reason,'local-date-pair')

    def test_three_date_block_has_no_pair_override(self):
        result = select_date([line('2023.01.01'),line('2024.01.01',30),line('2026.01.01',60)],final=True)
        self.assertNotEqual(result.reason,'local-date-pair')

    def test_explicit_expiry_beats_unlabelled_latest(self):
        result = select_date([line('EXP 2024.01.01'),line('2025.01.01',300),line('2026.01.01',330)],final=True)
        self.assertEqual(result.final_date,'2024-01-01')

    def test_role_does_not_choose_ambiguous_date_order(self):
        result = select_date([line('20-06-21'),line('22-06-23',30)],final=True)
        self.assertNotEqual(result.reason,'local-date-pair')

    def test_explicit_partial_beats_unlabelled_full_date(self):
        result = select_date([line('EXP 2026.09'),line('2025.01.01',300)],final=True)
        self.assertEqual(result.final_date,'2026-09-NONE')

    def test_license_number_not_expiry_partial(self):
        result = select_date([line('인증 제2013-06호 까지'),line('2027.03.02',300)],final=True)
        self.assertEqual(result.final_date,'2027-03-02')

    def test_damaged_expiry_keeps_recovery_open(self):
        result = select_date([line('제조일자: 2025.09.26'),line('소비기한: 2E.03.2E',30)])
        self.assertFalse(result.stop_ocr)
        self.assertIsNone(result.final_date)

    def test_bbd_calendar_unique(self):
        self.assertEqual(select_date([line('BBD:20/06/2026')]).final_date,'2026-06-20')

    def test_printed_legend_overrides_country_language(self):
        rows = [line('소비기한: 읽는 법 (일월년 순) BEST BEFORE (DDMMYY)'),line('050926',100)]
        self.assertEqual(select_date(rows,final=True).final_date,'2026-09-05')


if __name__ == '__main__':
    unittest.main()
