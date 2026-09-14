"""Build the notebook artifact without executing any notebook cell or test."""
import importlib.util
import json
import os
from pathlib import Path

BASE = Path('C:/ITDA_OCR_WORKSPACE/grouped-6-originals-v1/paper-plan-implementation-20260914')
GENERATOR = Path('C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/structural-development-20260914-v15/build_embedded_notebook.py')


def main():
    spec = importlib.util.spec_from_file_location('paper_notebook_generator',GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    staging = BASE/'predict-implementation.generated.ipynb'
    module.build(BASE/'code', staging)
    notebook = json.loads(staging.read_text(encoding='utf-8'))
    # This guard is in the first non-CONFIG cell, before definitions/models.
    notebook['cells'][1]['source'][:0] = [
        'import os\n',
        'if os.environ.get("ITDA_EXPLICIT_TEST_INSTRUCTION") != "1":\n',
        '    raise RuntimeError("Testing is paused. Obtain a separate user instruction before execution.")\n']
    notebook['metadata']['paper_implementation'] = dict(tested=False, execution_instruction_required=True)
    destination = BASE/'code/predict.ipynb'
    temporary = BASE/'code/predict-implementation.tmp'
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(notebook,stream,ensure_ascii=False,indent=1)
    os.replace(temporary,destination)
    print('Generated only, not executed: '+str(destination))


if __name__ == '__main__':
    main()
