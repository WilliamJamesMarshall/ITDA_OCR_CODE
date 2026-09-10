import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const labelsDir = "C:/ITDA_OCR_CODE/labels";
const previewDir = "C:/ITDA_OCR_CODE/.codex-tmp/renumber_20260910/previews_final";

async function listBooks(directory) {
  const books = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "node_modules" && entry.name !== "validation_000001_003352") {
        books.push(...await listBooks(fullPath));
      }
    } else if (entry.name.startsWith("validation_003355_003718") && entry.name.endsWith(".xlsx")) {
      books.push(fullPath);
    }
  }
  return books;
}

await fs.mkdir(previewDir, { recursive: true });
const books = (await listBooks(labelsDir)).sort();
if (books.length !== 5) throw new Error(`Expected 5 workbooks, found ${books.length}`);

const verified = [];
for (const workbookPath of books) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange();
  const values = sheet.getRange("A1:H365").values;
  const ids = values.slice(1).map((row) => Number(row[0]));
  if (values.length !== 365 || values[0].length !== 8) throw new Error(`Range mismatch: ${workbookPath}`);
  if (ids.some((id, index) => id !== 3355 + index)) throw new Error(`ID mismatch: ${workbookPath}`);
  if (sheet.tables.items.length !== 1) {
    throw new Error(`Table mismatch: ${workbookPath}`);
  }
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: "final formula error scan",
  });
  if (!errors.ndjson.includes("matched 0 entries")) {
    throw new Error(`Formula errors: ${workbookPath}\n${errors.ndjson}`);
  }
  const safeName = path.relative(labelsDir, workbookPath).replaceAll("\\", "__").replaceAll("/", "__");
  for (const [label, range] of [["head", "A1:H15"], ["tail", "A352:H365"]]) {
    const preview = await workbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, `${safeName}.${label}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  verified.push({ workbook: workbookPath, usedRange: used.address, rows: values.length - 1, firstId: ids[0], lastId: ids.at(-1) });
}

console.log(JSON.stringify({ verified }, null, 2));
