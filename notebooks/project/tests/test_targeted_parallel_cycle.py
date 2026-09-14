import unittest
from dataclasses import replace
from src.date_extraction import OCRLine,DateContext,select_date,DateSelection,_separate_printed_lot_reference
from src.budget_pipeline import output_selection

def line(text,box,**kwargs):return OCRLine(text,.99,box,original_box=box,**kwargs)

class TargetedCycleTests(unittest.TestCase):
    def test_printed_lot_date_header_separates_prefix_without_id_rule(self):
        rows=[line('제조번호 / 사용기한(연.월.일)',(0,0,300,30)),line('87654/28.11.19',(0,60,300,90))]
        selected=select_date(rows,context=DateContext())
        self.assertEqual(output_selection(selected).final_date,'2028-11-19')
        self.assertEqual(rows[1].text,'87654/28.11.19')

    def test_no_lot_splitting_without_local_explicit_legend(self):
        row=line('87654/28.11.19',(0,60,300,90))
        self.assertEqual(_separate_printed_lot_reference([row])[0].text,row.text)
        far=line('제조번호 / 사용기한(연.월.일)',(0,2000,300,2030))
        self.assertEqual(_separate_printed_lot_reference([row,far])[0].text,row.text)

    def test_split_manufacture_date_heading(self):
        rows=[line('제조',(0,0,40,20)),line('일자',(0,22,40,42)),line('2023.06.18',(50,10,220,35))]
        self.assertIsNone(output_selection(select_date(rows,context=DateContext())).final_date)

    def test_sale_date_header_survives_cross_pass_recovery(self):
        rows=[line('할인판매 시작일',(0,0,180,20)),line('2023.06.18',(0,25,180,45),source='paddle-geometric',variant='geometric-rows')]
        self.assertIsNone(output_selection(select_date(rows,context=DateContext())).final_date)

    def test_far_sale_label_does_not_cancel_expiry(self):
        rows=[line('할인판매 시작일',(0,2000,180,2020)),line('소비기한 2023.06.18',(0,25,240,45),source='paddle-geometric',variant='geometric-rows')]
        self.assertEqual(output_selection(select_date(rows,context=DateContext())).final_date,'2023-06-18')

    def test_partial_fields_preserved_without_inventing_year(self):
        partial=DateSelection('NONE-11-19',2.,1.,False,'partial-date',())
        previous=output_selection(partial)
        missing=DateSelection(None,0.,0.,False,'no-valid-date',())
        self.assertEqual(output_selection(missing,previous=previous).final_date,'NONE-11-19')

    def test_explicit_manufacturing_retracts_old_wrong_output(self):
        old=output_selection(select_date([line('2023.06.18',(0,0,180,20))],context=DateContext()))
        new=select_date([line('제조일 2023.06.18',(0,0,240,20))],context=DateContext())
        self.assertIsNone(output_selection(new,previous=old).final_date)

if __name__=='__main__':unittest.main()
