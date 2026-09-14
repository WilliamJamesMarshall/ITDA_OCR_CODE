"""Generate readable, isolated code cells from one source tree; no runtime py files."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


class EmbeddedImports(ast.NodeTransformer):
    def __init__(self, names):
        self.names = names

    def visit_ImportFrom(self, node):
        if node.module == '__future__':
            return None
        if not node.level:
            return node
        if node.level != 1 or node.module not in self.names or any(a.name=='*' for a in node.names):
            raise ValueError('Unsupported local import: '+ast.unparse(node))
        return [ast.Assign(targets=[ast.Name(id=a.asname or a.name,ctx=ast.Store())],
                           value=ast.Attribute(value=ast.Subscript(value=ast.Name(id='_ITDA_NS',ctx=ast.Load()),
                                                slice=ast.Constant(node.module),ctx=ast.Load()),
                                               attr=a.name,ctx=ast.Load())) for a in node.names]

    def visit_Subscript(self, node):
        expected = ast.parse('Path(__file__).resolve().parents[3]',mode='eval').body
        if ast.dump(node) == ast.dump(expected):
            return ast.Name(id='_ITDA_BUNDLE_ROOT',ctx=ast.Load())
        return self.generic_visit(node)


def cell(source):
    return dict(cell_type='code',execution_count=None,metadata={},outputs=[],source=source.splitlines(True))


def build(code_root, destination):
    code_root = Path(code_root)
    template=json.loads((code_root/'predict.ipynb').read_text(encoding='utf-8'))
    sources={p.stem:p for p in sorted((code_root/'notebooks/project/src').glob('*.py')) if p.stem!='__init__'}
    trees={name:ast.parse(path.read_text(encoding='utf-8-sig')) for name,path in sources.items()}
    dependencies={name:{node.module for node in tree.body if isinstance(node,ast.ImportFrom) and node.level}
                  for name,tree in trees.items()}
    order=[]
    while len(order)<len(sources):
        ready=sorted(name for name,deps in dependencies.items() if name not in order and deps<=set(order))
        if not ready: raise ValueError('Top-level import cycle; fix source dependency direction first')
        order.extend(ready)
    cells=[template['cells'][0],cell('import time\nNOTEBOOK_STARTED = time.perf_counter()\n'
           'from pathlib import Path\nfrom types import SimpleNamespace as _ITDA_Namespace\n'
           '_ITDA_BUNDLE_ROOT = Path.cwd().resolve()\n_ITDA_NS = {}\n')]
    for name in order:
        tree=EmbeddedImports(sources).visit(trees[name])
        ast.fix_missing_locations(tree)
        if any(isinstance(node,(ast.Global,ast.Nonlocal)) or isinstance(node,ast.Name) and node.id=='__file__'
               for node in ast.walk(tree)):
            raise ValueError('Unsupported module state: '+name)
        body=ast.unparse(tree)
        text=(f'from __future__ import annotations\n# Embedded from src/{name}.py; generated, do not edit separately.\n'
              f'def _itda_define_{name}():\n'+''.join('    '+line+'\n' for line in body.splitlines())+
              '    return _ITDA_Namespace(**locals())\n'
              f'_ITDA_NS[{name!r}] = _itda_define_{name}()\ndel _itda_define_{name}\n')
        compile(text,f'<embedded:{name}>','exec')
        cells.append(cell(text))
    cells.append(cell('summary = _ITDA_NS["pipeline"].run_pipeline(\n'
                      '    INPUT_DIR, OUTPUT_PATH, notebook_started=NOTEBOOK_STARTED,\n'
                      '    config=_ITDA_NS["pipeline"].PipelineConfig(weights_dir=_ITDA_BUNDLE_ROOT / "weights" / "paddle"))\n'))
    notebook=dict(template,cells=cells)
    notebook['metadata']=dict(template.get('metadata',{}),itda_embedded=dict(
        schema=1,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sources={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()},
        order=order,packaging_only=True,external_project_source_required=False))
    with Path(destination).open('x',encoding='utf-8') as stream:
        json.dump(notebook,stream,ensure_ascii=False,indent=1)
    print(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--code-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    build(args.code_root,args.output)
