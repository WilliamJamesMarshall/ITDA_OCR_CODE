import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const labelsDir = String.raw`C:\ITDA_OCR_WORKTREES\lee-hoyeon\labels`;
const imageDir = String.raw`C:\ITDA_OCR_CODE\추가수집데이터`;
const tempDir = String.raw`C:\ITDA_OCR_CODE\.codex-tmp\validation-003355-003740`;
const baseName = "validation_003355_003740_manual";
const csvPath = path.join(labelsDir, baseName + ".csv");
const xlsxPath = path.join(labelsDir, baseName + ".xlsx");
const inspectPath = path.join(labelsDir, baseName + ".xlsx.inspect.ndjson");
const previewPath = path.join(tempDir, "output-preview.png");

const sourcePaths = [
  path.join(labelsDir, "validation_000001_003352_manual.csv"),
  path.join(labelsDir, "validation_000001_003352_manual.xlsx"),
  path.join(labelsDir, "validation_000001_003352_manual.xlsx.inspect.ndjson"),
];

async function sha256(filePath) {
  const bytes = await fs.readFile(filePath);
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

const sourceHashesBefore = Object.fromEntries(
  await Promise.all(sourcePaths.map(async (p) => [p, await sha256(p)])),
);

const imageNames = (await fs.readdir(imageDir))
  .filter((name) => /^\d{6}\.jpg$/i.test(name))
  .sort();
if (imageNames.length !== 386 || imageNames[0] !== "003355.jpg" || imageNames.at(-1) !== "003740.jpg") {
  throw new Error(
    `Unexpected image set: count=${imageNames.length}, first=${imageNames[0]}, last=${imageNames.at(-1)}`,
  );
}
for (let i = 0; i < imageNames.length; i += 1) {
  const expected = String(3355 + i).padStart(6, "0") + ".jpg";
  if (imageNames[i] !== expected) throw new Error(`Non-contiguous image id: ${imageNames[i]} != ${expected}`);
}

const headers = ["image_id", "추출한 날짜", "정답 날짜", "True/False", "라벨 상태", "난이도", "오류 유형", "비고"];
const ids = imageNames.map((name) => Number(name.slice(0, 6)));
const rows = ids.map((id) => [id, "", "", "", "", "", "", ""]);

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("검수 정답지");
sheet.showGridLines = false;
sheet.getRange("A1:H387").values = [headers, ...rows];

sheet.getRange("D2").formulas = [[`=IF(OR(B2="",C2=""),"",IF(B2=C2,"True","False"))`]];
sheet.getRange("D2:D387").fillDown();

const table = sheet.tables.add("A1:H387", true, "ValidationTable");
table.style = "TableStyleLight1";
table.showFilterButton = true;
table.showBandedColumns = false;

const whole = sheet.getRange("A1:H387");
whole.format.font = { name: "Malgun Gothic", size: 10 };
whole.format.verticalAlignment = "center";
whole.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
whole.format.rowHeight = 22;
sheet.getRange("A2:H387").format.fill = "#FFFFFF";

const header = sheet.getRange("A1:H1");
header.format = {
  fill: "#1F4E78",
  font: { name: "Malgun Gothic", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#A6B9CF" },
};
header.format.rowHeight = 28;

sheet.getRange("A2:G387").format.horizontalAlignment = "center";
sheet.getRange("H2:H387").format.horizontalAlignment = "left";
sheet.getRange("H2:H387").format.wrapText = true;
sheet.getRange("A2:A387").format.numberFormat = "0";
sheet.getRange("B2:C387").format.numberFormat = "@";

sheet.getRange("A1:A387").format.columnWidth = 12;
sheet.getRange("B1:B387").format.columnWidth = 18;
sheet.getRange("C1:C387").format.columnWidth = 18;
sheet.getRange("D1:D387").format.columnWidth = 12;
sheet.getRange("E1:E387").format.columnWidth = 14;
sheet.getRange("F1:F387").format.columnWidth = 10;
sheet.getRange("G1:G387").format.columnWidth = 26;
sheet.getRange("H1:H387").format.columnWidth = 50;

sheet.freezePanes.freezeRows(1);
const truthRange = sheet.getRange("D2:D387");
truthRange.conditionalFormats.addCustom('=D2="True"', {
  fill: "#E2F0D9",
  font: { color: "#375623" },
});
truthRange.conditionalFormats.addCustom('=D2="False"', {
  fill: "#F4CCCC",
  font: { color: "#C00000" },
});

workbook.recalculate();
const tableCheck = await workbook.inspect({
  kind: "table",
  range: "검수 정답지!A1:H10",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 8,
  maxChars: 12000,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
const preview = await workbook.render({
  sheetName: "검수 정답지",
  range: "A1:H25",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(xlsxPath);

const csvLines = [
  headers.join(","),
  ...ids.map((id) => `${id},,,,,,,`),
];
await fs.writeFile(csvPath, csvLines.join("\n") + "\n", "utf8");

const xlsxDigest = await sha256(xlsxPath);
const ndjson = [];
ndjson.push(JSON.stringify({
  kind: "workbook",
  source: xlsxPath,
  sha256: xlsxDigest,
  sheets: 1,
  rows: 387,
  dataRows: 386,
  columns: 8,
}));
ndjson.push(JSON.stringify({ kind: "sheet", name: "검수 정답지", range: "A1:H387" }));
ndjson.push(JSON.stringify({
  kind: "row",
  sheet: "검수 정답지",
  row: 1,
  values: headers,
  formulas: ["", "", "", "", "", "", "", ""],
}));
for (let i = 0; i < ids.length; i += 1) {
  const excelRow = i + 2;
  ndjson.push(JSON.stringify({
    kind: "row",
    sheet: "검수 정답지",
    row: excelRow,
    values: [String(ids[i]), "", "", "", "", "", "", ""],
    formulas: ["", "", "", `=IF(OR(B${excelRow}="",C${excelRow}=""),"",IF(B${excelRow}=C${excelRow},"True","False"))`, "", "", "", ""],
  }));
}
ndjson.push(JSON.stringify({ kind: "summary", trueCount: 0, falseCount: 0, changedExtractedDates: 0 }));
await fs.writeFile(inspectPath, ndjson.join("\n") + "\n", "utf8");

const savedWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
const savedHead = await savedWorkbook.inspect({
  kind: "table",
  range: "검수 정답지!A1:H10",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 8,
  maxChars: 12000,
});
const savedTail = await savedWorkbook.inspect({
  kind: "table",
  range: "검수 정답지!A379:H387",
  include: "values,formulas",
  tableMaxRows: 9,
  tableMaxCols: 8,
  maxChars: 12000,
});
const savedErrors = await savedWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "saved workbook formula error scan",
});

const sourceHashesAfter = Object.fromEntries(
  await Promise.all(sourcePaths.map(async (p) => [p, await sha256(p)])),
);
if (JSON.stringify(sourceHashesBefore) !== JSON.stringify(sourceHashesAfter)) {
  throw new Error("One or more reference files changed");
}

console.log("=== PRE-EXPORT CHECK ===");
console.log(tableCheck.ndjson);
console.log(formulaErrors.ndjson);
console.log("=== SAVED HEAD ===");
console.log(savedHead.ndjson);
console.log("=== SAVED TAIL ===");
console.log(savedTail.ndjson);
console.log(savedErrors.ndjson);
console.log(JSON.stringify({
  csvPath,
  xlsxPath,
  inspectPath,
  previewPath,
  rowCount: ids.length,
  firstId: ids[0],
  lastId: ids.at(-1),
  sourceFilesUnchanged: true,
  outputHashes: {
    csv: await sha256(csvPath),
    xlsx: xlsxDigest,
    inspect: await sha256(inspectPath),
  },
}, null, 2));
