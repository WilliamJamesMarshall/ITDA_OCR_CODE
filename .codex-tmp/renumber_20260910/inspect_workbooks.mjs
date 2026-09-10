import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const labelsDir = "C:/ITDA_OCR_CODE/labels";
const previewDir = "C:/ITDA_OCR_CODE/.codex-tmp/renumber_20260910/previews_before";
await fs.mkdir(previewDir, { recursive: true });

const entries = await fs.readdir(labelsDir, { withFileTypes: true });
const books = entries.filter((entry) => entry.isFile() && entry.name.endsWith(".xlsx"));
for (const entry of books) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(labelsDir, entry.name)));
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table,formula",
    maxChars: 3500,
    tableMaxRows: 5,
    tableMaxCols: 10,
    options: { maxResults: 30 },
  });
  console.log(`BOOK ${entry.name}`);
  console.log(summary.ndjson);
  const sheet = workbook.worksheets.getItemAt(0);
  for (const [label, range] of [["head", "A1:H15"], ["tail", "A374:H387"]]) {
    const preview = await workbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, `${entry.name}.${label}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}
