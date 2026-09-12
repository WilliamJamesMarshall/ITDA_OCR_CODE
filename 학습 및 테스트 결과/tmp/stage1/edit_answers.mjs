import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = 'C:/ITDA_OCR_CODE';
const tmp = path.join(root, '학습 및 테스트 결과/tmp/stage1');
const mode = process.argv[2] ?? 'preview';
const plan = JSON.parse(await fs.readFile(path.join(tmp, 'workbook_edits.json'), 'utf8'));
const report = [];
for (const entry of plan) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root, entry.path)));
  const sheet = workbook.worksheets.getItem('검수 정답지');
  const sample = entry.correctedRow ? `A${entry.correctedRow-1}:H${entry.correctedRow+1}` : 'A1:H4';
  if (mode === 'preview') {
    const preview = await workbook.render({sheetName: '검수 정답지', range: sample, scale: 1.5});
    await fs.writeFile(path.join(tmp, `${entry.key}_before.png`), new Uint8Array(await preview.arrayBuffer()));
    console.log(JSON.stringify({key: entry.key, check: (await workbook.inspect({kind: 'table', range: `검수 정답지!${sample}`, include: 'values,formulas', tableMaxRows: 4, tableMaxCols: 8})).ndjson}));
    continue;
  }
  if (mode !== 'edit') throw new Error(`Unknown mode: ${mode}`);
  for (const change of entry.dateChanges) sheet.getRange(change.cell).values = [[change.value]];
  sheet.getRange(`E2:H${entry.metadata.length+1}`).values = entry.metadata;
  // Metadata now contains text; preserve columns and fit only the affected rows.
  sheet.getRange(`E2:H${entry.metadata.length+1}`).format.wrapText = true;
  sheet.getRange(`E2:H${entry.metadata.length+1}`).format.autofitRows();
  workbook.recalculate();
  const checked = await workbook.inspect({kind: 'table', range: `검수 정답지!${sample}`, include: 'values,formulas', tableMaxRows: 4, tableMaxCols: 8});
  const errors = await workbook.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: {useRegex: true, maxResults: 20}});
  const preview = await workbook.render({sheetName: '검수 정답지', range: sample, scale: 1.5});
  await fs.writeFile(path.join(tmp, `${entry.key}_after.png`), new Uint8Array(await preview.arrayBuffer()));
  // Export to staging; the independent preservation check runs before installation.
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(tmp, `${entry.key}.xlsx`));
  report.push({key: entry.key, check: checked.ndjson, errors: errors.ndjson});
  console.log(JSON.stringify({key: entry.key, status: 'staged', errors: errors.ndjson}));
}
if (mode === 'edit') await fs.writeFile(path.join(tmp, 'workbook_tool_report.json'), JSON.stringify(report, null, 2));
// The bundled renderer leaves worker handles on Windows after all exports finish.
process.exit(0);
