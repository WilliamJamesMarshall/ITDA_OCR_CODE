import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";


const [inputPath, previewPath] = process.argv.slice(2);
if (!inputPath || !previewPath) {
  throw new Error("Usage: node verify_validation_csv.mjs <input.csv> <preview.png>");
}

const csvText = await fs.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "RapidOCR labels" });
workbook.recalculate();

const sheet = workbook.worksheets.getItem("RapidOCR labels");
const usedRange = sheet.getUsedRange(true);
const values = usedRange.values;
if (values.length !== 3353 || values[0].length !== 6) {
  throw new Error(`Unexpected CSV shape: ${values.length} rows x ${values[0]?.length ?? 0} columns`);
}

const first = await workbook.inspect({
  kind: "table",
  range: "'RapidOCR labels'!A1:F8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 6,
});
const last = await workbook.inspect({
  kind: "table",
  range: "'RapidOCR labels'!A3346:F3353",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 6,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 20 },
  summary: "final formula error scan",
});

const preview = await workbook.render({
  sheetName: "RapidOCR labels",
  range: "A1:F24",
  scale: 1,
  format: "png",
});
await fs.mkdir(path.dirname(previewPath), { recursive: true });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

console.log(JSON.stringify({
  shape: [values.length, values[0].length],
  first: first.ndjson,
  last: last.ndjson,
  errors: errors.ndjson,
}));
