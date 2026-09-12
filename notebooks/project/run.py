"""Run development modules with the same project import root as predict.ipynb."""
import os
import runpy
import sys
from pathlib import Path

if __name__=='__main__':
    if len(sys.argv)<2:
        raise SystemExit('Usage: python notebooks/project/run.py <module> [arguments]')
    os.chdir(Path(__file__).resolve().parents[2])
    module=sys.argv.pop(1)
    runpy.run_module(module,run_name='__main__')
