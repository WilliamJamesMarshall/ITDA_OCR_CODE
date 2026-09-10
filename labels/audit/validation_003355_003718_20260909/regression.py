"""Execute the unchanged production parser tests against an isolated variant."""
import sys
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, 'C:/ITDA_OCR_WORKTREES/lee-hoyeon')
stage = sys.argv[1]
if stage != 'baseline':
    from experiments import install
    install(stage, SimpleNamespace())
suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_date_extraction')
result = unittest.TextTestRunner(verbosity=1).run(suite)
record = {'stage':stage,'tests_run':result.testsRun,
          'failures':[{'test':str(t),'traceback':err} for t,err in result.failures],
          'errors':[{'test':str(t),'traceback':err} for t,err in result.errors]}
Path(__file__).with_name(f'{stage}_regression.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
