import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,'C:/ITDA_OCR_WORKTREES/lee-hoyeon')
from src import date_extraction as d
d.MIN_YEAR=1
checks={
    'historical_date_accepted':d._valid_date(2021,5,26).isoformat()=='2021-05-26',
    'future_limit_unchanged':d.MAX_YEAR==2035 and d._valid_date(2036,1,1) is None,
    'invalid_calendar_rejected':d._valid_date(2021,2,30) is None,
    'yearless_parser_unchanged':d.parse_dates('02.14')==[],
    'year_month_parser_unchanged':d.parse_dates('2022.05')==[],
}
assert all(checks.values())
suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_date_extraction')
result=unittest.TextTestRunner(verbosity=1).run(suite)
failures=[{'test':str(t),'traceback':e} for t,e in result.failures]
assert len(failures)==1 and '2020.09.20' in failures[0]['traceback'] and not result.errors
output={'variant':{'MIN_YEAR':d.MIN_YEAR,'MAX_YEAR':d.MAX_YEAR},'targeted_checks':checks,
        'tests_run':result.testsRun,'failures':failures,'errors':[],
        'interpretation':'Only the old expectation that 2020 dates are rejected fails. No other production test regresses.'}
Path(__file__).with_name('baseline_tests.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'targeted_checks':checks,'tests_run':result.testsRun,'expected_policy_failures':len(failures)}))
