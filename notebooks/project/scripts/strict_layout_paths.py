"""One-time mechanical path migration, preserving OCR algorithms and annotation records."""
import json
from pathlib import Path
ROOT=Path('C:/ITDA_OCR_CODE')
PROJECT=ROOT/'notebooks/project'
for folder in ('scripts','tests'):
    for path in (PROJECT/folder).glob('*.py'):
        if path.name.startswith('strict_layout_'):continue
        text=path.read_text(encoding='utf-8')
        # Root variables address data/weights; direct sys.path parents[1] remains code root.
        for prefix in ('ROOT = ','ROOT=','root = '):
            text=text.replace(prefix+'Path(__file__).resolve().parents[1]',prefix+'Path(__file__).resolve().parents[3]')
        text=text.replace('ROOT = Path(__file__).parents[1]','ROOT = Path(__file__).parents[3]')
        text=text.replace('Path(__file__).parents[1] / "predict.ipynb"','Path(__file__).parents[3] / "predict.ipynb"')
        text=text.replace('sys.path.insert(0,str(ROOT))','sys.path.insert(0,str(Path(__file__).resolve().parents[1]))')
        text=text.replace('sys.path.insert(0, str(ROOT))','sys.path.insert(0, str(Path(__file__).resolve().parents[1]))')
        text=text.replace("ROOT/'scripts/","ROOT/'notebooks/project/scripts/")
        text=text.replace('ROOT / "configs"','ROOT / "notebooks" / "project" / "configs"')
        path.write_text(text,encoding='utf-8')
p=PROJECT/'src/pipeline.py'
text=p.read_text(encoding='utf-8').replace('Path(__file__).resolve().parents[1] / "weights"','Path(__file__).resolve().parents[3] / "weights"')
p.write_text(text,encoding='utf-8')
p=PROJECT/'scripts/prepare_training_runtime.ps1'
text=p.read_text(encoding='utf-8').replace("Join-Path $PSScriptRoot '..'","Join-Path $PSScriptRoot '../../..'").replace("'scripts\\train_recognition_cpu.py'","'notebooks\\project\\scripts\\train_recognition_cpu.py'")
p.write_text(text,encoding='utf-8')
p=ROOT/'predict.ipynb';nb=json.loads(p.read_text(encoding='utf-8'))
nb['cells'][1]['source']=['from pathlib import Path\n','import sys\n','CODE_ROOT = Path.cwd() / "notebooks" / "project"\n','if not (CODE_ROOT / "src" / "pipeline.py").is_file():\n','    raise RuntimeError("Run predict.ipynb from the repository root")\n','sys.path.insert(0, str(CODE_ROOT))\n','from src.pipeline import run_pipeline']
p.write_text(json.dumps(nb,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Paths updated; notebook CONFIG and OCR logic retained')
