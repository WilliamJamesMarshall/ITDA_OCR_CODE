import { Workbook } from "@oai/artifact-tool";
const wb = Workbook.create();
console.log(wb.help("table.rows.delete", { include: "index,examples,notes", maxChars: 5000 }).ndjson);
console.log(wb.help("table.resize", { include: "index,examples,notes", maxChars: 5000 }).ndjson);
