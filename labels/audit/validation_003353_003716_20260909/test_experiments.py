import sys
import json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, 'C:/ITDA_OCR_WORKTREES/lee-hoyeon')
from src import date_extraction as d
from experiments import install

stage = sys.argv[1]
pipeline = SimpleNamespace()
install(stage, pipeline)
tests = []
def check(name, actual, expected):
    tests.append({'name':name,'actual':actual,'expected':expected,'passed':actual==expected})
def infer(text):
    return pipeline.select_date([d.OCRLine(text,.98,(0,0,350,20))], final=True).final_date or 'NONE'
check('historical-full-date',infer('EXP 2019.04.18'),'2019-04-18')
check('year-month-only',infer('EXP 2022.06'),'2022-06-NONE')
check('month-day-only',infer('소비기한 02월 14일'),'NONE-02-14')
check('no-date',infer('유통기한 제조일부터 90일'),'NONE')
check('invalid-calendar',infer('EXP 2021.02.30'),'NONE')
check('partial-output-contract',pipeline.submission_fields('NONE-02-14'),{'year':'NONE','month':'02','day':'14','final_date':'NONE-02-14'})
check('manufacturing-only',infer('제조일자 2021.05.08'),'NONE')
if stage in ('p2','p3'):
    check('two-digit-MDY-unambiguous',infer('EXP 08/18/21'),'2021-08-18')
    check('explicit-Korean-MDY',infer('07.12.2022 (월/일/년)'),'2022-07-12')
    check('explicit-English-MDY',infer('07.12.2022 (MM/DD/YYYY)'),'2022-07-12')
    check('year-month-name-day',infer('EXP 2022 JUN 12'),'2022-06-12')
if stage == 'p3':
    check('no-cross-frame-date',pipeline.select_date([d.OCRLine('2022.',.95,(0,0,90,40),'paddle-mobile','original'),d.OCRLine('05.29까지',.95,(100,0,250,40),'paddle-mobile','roi-1')],final=True).final_date,'NONE-05-29')
    check('distant-keyword-not-attached',d._nearby_context(d.OCRLine('2022.05.29',.98,(0,0,90,20),members=(0,)),[d.OCRLine('2022.05.29',.98,(0,0,90,20)),d.OCRLine('제조일자',.98,(2000,2000,2100,2020))]),([],[],0.))
Path(__file__).with_name(f'{stage}_tests.json').write_text(json.dumps(tests,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'stage':stage,'passed':sum(t['passed'] for t in tests),'total':len(tests),'failures':[t for t in tests if not t['passed']]},ensure_ascii=False))
assert all(t['passed'] for t in tests)
