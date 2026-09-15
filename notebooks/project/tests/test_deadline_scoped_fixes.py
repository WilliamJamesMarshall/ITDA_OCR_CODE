"""Regression boundaries for candidate output, role linkage and retry routing."""
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from src.date_extraction import OCRLine, DateContext, select_date, _link_roles, field_evidence
from src.budget_pipeline import output_selection, run_budget_pipeline
from src.pipeline import PipelineConfig
from src.selective_recovery import remaining_actions


def row(text, box, score=.99, variant='original'):
    return OCRLine(text, score, box, variant=variant, original_box=box)


class DeadlineScopedFixTests(unittest.TestCase):
    def test_left_aligned_short_expiry_heading_binds_its_date(self):
        lines = [row('EXP', (549,389,623,431)),
                 row('22/09/2021', (550,442,742,483)),
                 row('L-2209 13:22', (548,491,776,532))]
        self.assertEqual(_link_roles(lines)[1].role, 'end')
        self.assertIsNone(_link_roles(lines)[2].role)
        self.assertEqual(output_selection(select_date(lines, context=DateContext())).final_date, '2021-09-22')

    def test_shared_or_weak_heading_does_not_gain_exclusive_role(self):
        for heading in [row('EXP',(0,0,390,25)), row('EXP',(0,0,70,25),score=.6)]:
            lines=[heading,row('2026.03.04',(0,35,170,60)),row('2026.04.05',(220,35,390,60))]
            self.assertIsNone(output_selection(select_date(lines,context=DateContext())).final_date)

    def test_explicit_lot_clock_is_not_expiry_even_under_heading(self):
        lines=[row('EXP',(0,0,70,25)),row('L-2209 13:22',(0,35,230,65))]
        self.assertIsNone(output_selection(select_date(lines,context=DateContext())).final_date)

    def test_expiry_with_trailing_lot_and_time_is_preserved(self):
        lines=[row('EXP 22/09/2021 L-2209 13:22',(0,0,400,35))]
        self.assertEqual(output_selection(select_date(lines,context=DateContext())).final_date,'2021-09-22')

    def test_lot_without_clock_does_not_expose_month_legend_as_new_date(self):
        lines=[row('0CT-10,NOV-11월,.DEC-12월',(113,170,249,200),score=.9076),
               row('LOT ACAEU051120',(140,319,265,348),score=.9644),
               row('EXP NOU 05 2022',(137,349,270,376),score=.8931)]
        self.assertIsNone(output_selection(select_date(lines,context=DateContext())).final_date)

    def test_same_token_in_two_passes_keeps_only_order_consensus(self):
        lines=[row('10/02/2022',(0,0,190,40)),row('10/02/2022',(1,1,191,41),variant='recovery')]
        selection=select_date(lines,context=DateContext())
        self.assertEqual(field_evidence(selection)['final_date'],'2022-NONE-NONE')

    def test_new_expiry_token_does_not_borrow_month_day_from_other_region(self):
        old=output_selection(select_date([row('2026.04.20',(0,0,190,40))],context=DateContext()))
        new=select_date([row('EXP 02/10/2026',(0,200,260,240))],context=DateContext())
        self.assertEqual(output_selection(new,previous=old).final_date,'2026-NONE-NONE')

    def test_supported_recovery_replaces_old_wrong_date(self):
        old=output_selection(select_date([row('22/09/2013',(0,0,190,40))],context=DateContext()))
        new=select_date([row('EXP 22/09/2021',(0,0,260,40))],context=DateContext())
        output=output_selection(new,previous=old)
        self.assertEqual(output.final_date,'2021-09-22')
        self.assertEqual(output.policy_details['expiration_date'],output.final_date)

    def test_clear_order_uncertainty_replaces_numeric_retry_chain(self):
        lines=[row('10/02/2022',(0,0,190,40))]
        selection=select_date(lines,context=DateContext())
        self.assertEqual(remaining_actions(selection,lines,['geometric','stroke','secondary'],{'date-lines'}),
                         ['context-roi','secondary'])
        self.assertEqual(remaining_actions(selection,lines,['geometric'],{'context-roi','secondary'}),[])

    def test_weak_digits_preserve_unattempted_numeric_retries(self):
        lines=[row('10/02/2022',(0,0,190,40))]
        selection=replace(select_date(lines,context=DateContext()),digits_confident=False)
        self.assertEqual(remaining_actions(selection,lines,['date-lines','geometric'],{'date-lines'}),['geometric'])

    def test_budget_loop_does_not_restart_digits_after_context_detection(self):
        class Backend:
            def recognize(self,image,**kwargs): return [row('2026.03.04',(0,0,190,40),score=.8)]
        actions=[]
        clear=[row('10/02/2022',(0,0,190,40))]
        def recover(action,image,lines,backend,guard,config,trace,commit):
            actions.append(action)
            return clear,[],[],0.
        with TemporaryDirectory() as folder:
            root=Path(folder)
            Image.new('RGB',(250,100)).save(root/'sample.png')
            with patch('src.budget_pipeline.run_stage',side_effect=recover):
                result=run_budget_pipeline(root,root/'out.csv',backend=Backend(),
                    config=PipelineConfig(collect_trace=False,progress_every=0,date_context=DateContext()))
            self.assertEqual(actions,['date-lines','context-roi','secondary'])
            self.assertEqual(result['budget_seconds'],1470.)
            self.assertTrue(result['output_complete'])


if __name__=='__main__': unittest.main()
