import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const labelsDir = "C:/ITDA_OCR_CODE/labels";
const outputDir = "C:/ITDA_OCR_CODE/outputs/01a08828-ff4d-7401-bdfe-75041206f3e4/renumbered_labels";
const previewDir = "C:/ITDA_OCR_CODE/.codex-tmp/renumber_20260910/previews_after";
const deleted = new Set([
  3360, 3376, 3395, 3430, 3441, 3491, 3516, 3535, 3609, 3675, 3677,
  3689, 3708, 3713, 3716, 3719, 3724, 3727, 3729, 3730, 3738, 3739,
]);
const survivors = [];
for (let imageId = 3355; imageId <= 3740; imageId += 1) {
  if (!deleted.has(imageId)) survivors.push(imageId);
}
const mapping = new Map(survivors.map((oldId, index) => [oldId, 3355 + index]));

async function listBooks(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "validation_000001_003352") continue;
      result.push(...await listBooks(fullPath));
    } else if (entry.name.startsWith("validation_003355_003718") && entry.name.endsWith(".xlsx")) {
      result.push(fullPath);
    }
  }
  return result;
}

function normalizeId(value) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 3355 && number <= 3740 ? number : null;
}

async function saveInspect(workbook, workbookPath) {
  const bytes = await fs.readFile(workbookPath);
  const sheet = workbook.worksheets.getItemAt(0);
  const dataRange = sheet.getRange("A1:H365");
  const values = dataRange.values;
  const formulas = dataRange.formulas;
  const lines = [JSON.stringify({
    kind: "workbook",
    source: workbookPath,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    sheets: workbook.worksheets.items.length,
    rows: values.length,
    dataRows: values.length - 1,
    columns: values[0].length,
  }), JSON.stringify({ kind: "sheet", name: sheet.name, range: `A1:H${values.length}` })];
  for (let index = 0; index < values.length; index += 1) {
    lines.push(JSON.stringify({
      kind: "row",
      sheet: sheet.name,
      row: index + 1,
      values: values[index].map((value) => value ?? ""),
      formulas: formulas[index].map((value) => value ?? ""),
    }));
  }
  await fs.writeFile(`${workbookPath}.inspect.ndjson`, `${lines.join("\n")}\n`, "utf8");
}

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
const books = (await listBooks(labelsDir)).sort();
if (books.length !== 5) throw new Error(`Expected 5 workbooks, found ${books.length}`);

for (const workbookPath of books) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange();
  const sourceValues = used.values;
  if (sourceValues.length < 365 || sourceValues[0].length !== 8) {
    throw new Error(`Unexpected source range in ${workbookPath}: ${sourceValues.length}x${sourceValues[0]?.length}`);
  }
  const keptRows = [];
  const existingIds = sourceValues.slice(1, 365).map((row) => normalizeId(row[0]));
  const alreadyRenumbered = existingIds.every((id, index) => id === 3355 + index);
  if (alreadyRenumbered) {
    keptRows.push(...sourceValues.slice(1, 365));
  } else {
    for (const row of sourceValues.slice(1)) {
      const oldId = normalizeId(row[0]);
      if (oldId === null) throw new Error(`Invalid image_id in ${workbookPath}: ${row[0]}`);
      if (deleted.has(oldId)) continue;
      const updated = [...row];
      updated[0] = mapping.get(oldId);
      keptRows.push(updated);
    }
  }
  if (keptRows.length !== 364) throw new Error(`Expected 364 rows in ${workbookPath}`);

  const tables = sheet.tables.items;
  if (tables.length !== 1) throw new Error(`Expected one table in ${workbookPath}`);
  const oldTable = tables[0];
  const tableSettings = {
    name: oldTable.name,
    style: oldTable.style,
    showHeaders: oldTable.showHeaders,
    showTotals: oldTable.showTotals,
    showBandedColumns: oldTable.showBandedColumns,
    showFilterButton: oldTable.showFilterButton,
  };
  oldTable.delete();
  sheet.getRange("A2:H365").values = keptRows;
  sheet.getRange("A366:H387").clear({ applyTo: "all" });
  const formulas = Array.from({ length: 364 }, (_, index) => {
    const row = index + 2;
    return [`=IF(OR(B${row}="",C${row}=""),"",IF(B${row}=C${row},"True","False"))`];
  });
  sheet.getRange("D2:D365").formulas = formulas;
  const table = sheet.tables.add("A1:H365", true, tableSettings.name);
  if (tableSettings.style) table.style = tableSettings.style;
  table.showHeaders = tableSettings.showHeaders;
  table.showTotals = tableSettings.showTotals;
  table.showBandedColumns = tableSettings.showBandedColumns;
  table.showFilterButton = tableSettings.showFilterButton;
  sheet.getRange("A366:H387").clear({ applyTo: "contents" });
  workbook.recalculate();

  const check = await workbook.inspect({
    kind: "region,formula",
    sheetId: sheet.name,
    range: "A1:H365",
    maxChars: 4000,
    tableMaxRows: 6,
    tableMaxCols: 8,
    options: { maxResults: 20 },
  });
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: "final formula error scan",
  });
  console.log(`EDITED ${workbookPath}`);
  console.log(check.ndjson);
  console.log(errors.ndjson);

  const relative = path.relative(labelsDir, workbookPath);
  const exportedPath = path.join(outputDir, relative);
  await fs.mkdir(path.dirname(exportedPath), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(exportedPath);

  const verified = await SpreadsheetFile.importXlsx(await FileBlob.load(exportedPath));
  const verifiedSheet = verified.worksheets.getItemAt(0);
  const verifiedValues = verifiedSheet.getRange("A1:H365").values;
  if (verifiedValues.length !== 365 || verifiedValues[0].length !== 8) {
    throw new Error(`Exported range mismatch in ${exportedPath}`);
  }
  const ids = verifiedValues.slice(1).map((row) => Number(row[0]));
  if (ids.some((id, index) => id !== 3355 + index)) {
    throw new Error(`Exported ID sequence mismatch in ${exportedPath}`);
  }
  const trailingValues = verifiedSheet.getRange("A366:H387").values;
  const trailingFormulas = verifiedSheet.getRange("A366:H387").formulas;
  if (trailingValues.some((row) => row.some((value) => value !== null && value !== "")) ||
      trailingFormulas.some((row) => row.some((value) => value !== null && value !== ""))) {
    throw new Error(`Trailing data remained in ${exportedPath}`);
  }
  const safeName = relative.replaceAll("\\", "__").replaceAll("/", "__");
  for (const [label, range] of [["head", "A1:H15"], ["tail", "A352:H365"]]) {
    const preview = await verified.render({ sheetName: verifiedSheet.name, range, scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, `${safeName}.${label}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  await fs.copyFile(exportedPath, workbookPath);
  await saveInspect(verified, workbookPath);
}

console.log(JSON.stringify({ editedWorkbooks: books.length, rowsPerWorkbook: 364, firstId: 3355, lastId: 3718 }));
