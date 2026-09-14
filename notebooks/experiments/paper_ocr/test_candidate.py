"""Run source tests with the existing legacy/budget test separation."""
import argparse
import contextlib
import json
import os
import sys
import unittest
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.code_root/'notebooks/project'))
    os.environ['ITDA_EXECUTION_POLICY'] = 'legacy'
    selected, excluded = unittest.TestSuite(), []
    def add(suite):
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                add(test)
            elif test.id().startswith('test_repository_layout.'):
                excluded.append(test.id())
            else:
                selected.addTest(test)
    add(unittest.TestLoader().discover(str(args.code_root/'notebooks/project/tests')))
    with args.log.open('x', encoding='utf-8') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(selected)
    record = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  excluded=excluded, passed=result.wasSuccessful(), log=str(args.log))
    args.log.with_suffix('.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
