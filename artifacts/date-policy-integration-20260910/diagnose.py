"""Inspect the lost development cases; IDs are never used in production rules."""
from dataclasses import asdict
import compare_existing as comparison
import json

lost = set(comparison.summary['lost'])
output = []
for raw in comparison.cache.read_text(encoding='utf-8').splitlines():
    record = json.loads(raw)
    if record['image_id'] not in lost:
        continue
    item = {'image_id':record['image_id'],'truth':comparison.truth[record['image_id']]['truth']}
    for name,module in (('baseline',comparison.reference),('integrated',comparison.current)):
        lines = [module.OCRLine(**line) for line in record['lines']]
        selection = module.select_date(lines,final=True)
        item[name] = {'prediction':selection.final_date,'reason':selection.reason,
                      'candidates':[asdict(c) for c in selection.candidates[:5]]}
    item['lines'] = [line for line in record['lines'] if comparison.current.parse_dates(line['text']) or comparison.current.POSITIVE_CONTEXT.search(line['text']) or comparison.current.NEGATIVE_CONTEXT.search(line['text'])]
    output.append(item)
(comparison.OUT/'regression_diagnostics.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
for item in output:
    print(json.dumps(item,ensure_ascii=False,default=str))
