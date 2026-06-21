import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve("outputs", "prompt_validation");
const csvPath = path.join(outputDir, "prompt_validation_results.csv");
const outputPath = path.join(outputDir, "prompt_validation_results.xlsx");

const csvText = await fs.readFile(csvPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "Prompt Validation" });
const sheet = workbook.worksheets.getItem("Prompt Validation");
sheet.showGridLines = false;
const used = sheet.getUsedRange();
used.format.wrapText = true;
used.format.autofitRows();
sheet.freezePanes.freezeRows(1);
sheet.getRange("A1:J1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
};
sheet.getRange("A:A").format.columnWidth = 7;
sheet.getRange("B:B").format.columnWidth = 52;
sheet.getRange("C:E").format.columnWidth = 18;
sheet.getRange("F:H").format.columnWidth = 24;
sheet.getRange("I:J").format.columnWidth = 70;
const table = sheet.tables.add(`A1:J${used.rowCount}`, true, "PromptValidationTable");
table.style = "TableStyleMedium2";
table.showFilterButton = true;

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;
summary.getRange("A1:D1").merge();
summary.getRange("A1").values = [["Prompt Validation Summary"]];
summary.getRange("A1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF", size: 15 },
};
summary.getRange("A3:B7").values = [
  ["Total prompts tested", used.rowCount - 1],
  ["Output file", outputPath],
  ["Source prompt file", "C:\\Users\\giris\\Downloads\\AIPrompts.txt"],
  ["Data mode", "Realtime default where market connector is implemented"],
  ["Generated at", new Date()],
];
summary.getRange("A3:A7").format = { fill: "#E0F2F1", font: { bold: true } };
summary.getRange("B7").setNumberFormat("yyyy-mm-dd hh:mm");
summary.getRange("A:B").format.autofitColumns();
summary.getRange("B:B").format.columnWidth = 82;

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const preview = await workbook.render({
  sheetName: "Summary",
  autoCrop: "all",
  scale: 1,
  format: "png",
});
await fs.writeFile(path.join(outputDir, "prompt_validation_summary.png"), new Uint8Array(await preview.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(JSON.stringify({ outputPath, rows: used.rowCount - 1 }));
