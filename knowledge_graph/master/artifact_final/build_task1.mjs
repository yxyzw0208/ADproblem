import fs from "node:fs";
import fsp from "node:fs/promises";
import readline from "node:readline";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputNdjson = "D:/codex/大创/本轮任务_20260818/主控/artifact_final/task1_rows.ndjson";
const outputXlsx = "D:/codex/大创/最终交付_SwissAD全分子_20260818/01_Swiss预测靶点与AD交集.xlsx";
const qaDir = "D:/codex/大创/本轮任务_20260818/主控/artifact_final";
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Swiss∩AD共同靶点");
sheet.showGridLines = false;
sheet.freezePanes.freezeRows(1);

const reader = readline.createInterface({
  input: fs.createReadStream(inputNdjson, { encoding: "utf8" }),
  crlfDelay: Infinity,
});
let headerValues = null;
let chunk = [];
let rowCursor = 1;
const CHUNK_ROWS = 5000;
function flushChunk() {
  if (!chunk.length) return;
  sheet.getRangeByIndexes(rowCursor, 0, chunk.length, headerValues.length).values = chunk;
  rowCursor += chunk.length;
  chunk = [];
}
for await (const line of reader) {
  if (!line) continue;
  const row = JSON.parse(line);
  if (headerValues === null) {
    headerValues = row;
    sheet.getRangeByIndexes(0, 0, 1, headerValues.length).values = [headerValues];
  } else {
    chunk.push(row);
    if (chunk.length >= CHUNK_ROWS) flushChunk();
  }
}
flushChunk();
if (headerValues === null) throw new Error("NDJSON input is empty");
const lastRow = rowCursor;

const header = sheet.getRange("A1:F1");
header.format = {
  fill: "#25577F",
  font: { bold: true, color: "#FFFFFF", size: 11 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { bottom: { style: "medium", color: "#173A5E" } },
};
header.format.rowHeight = 34;

sheet.getRange(`E2:E${lastRow}`).format.numberFormat = "0.000000000";

const widths = [30, 15, 58, 18, 16, 72];
for (let index = 0; index < widths.length; index += 1) {
  sheet.getCell(0, index).format.columnWidth = widths[index];
}

const inspect = await workbook.inspect({
  kind: "table",
  range: "Swiss∩AD共同靶点!A1:F12",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 6,
  maxChars: 8000,
});
await fsp.writeFile(`${qaDir}/task1_inspect.ndjson`, inspect.ndjson, "utf8");
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fsp.writeFile(`${qaDir}/task1_errors.ndjson`, errors.ndjson, "utf8");
const preview = await workbook.render({
  sheetName: "Swiss∩AD共同靶点",
  range: "A1:F25",
  scale: 1.5,
  format: "png",
});
await fsp.writeFile(`${qaDir}/task1_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputXlsx);
console.log(JSON.stringify({ outputXlsx, rows: lastRow - 1, inspect: inspect.ndjson.slice(0, 2000), errors: errors.ndjson.slice(0, 2000) }));
