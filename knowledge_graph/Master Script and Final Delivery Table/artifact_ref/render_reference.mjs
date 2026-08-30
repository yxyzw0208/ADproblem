import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = "D:/codex/大创/Swiss_AD共同靶点分析_20260814/最终交付/01_Swiss预测靶点与AD交集.xlsx";
const outDir = "D:/codex/大创/本轮任务_20260818/主控/artifact_ref";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const inspect = await workbook.inspect({
  kind: "workbook,sheet,table,computedStyle",
  range: "A1:F12",
  maxChars: 8000,
  tableMaxRows: 12,
  tableMaxCols: 6,
});
await fs.writeFile(`${outDir}/reference_inspect.ndjson`, inspect.ndjson, "utf8");
const preview = await workbook.render({
  sheetName: workbook.worksheets.getItemAt(0).name,
  range: "A1:F25",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(`${outDir}/reference_preview.png`, new Uint8Array(await preview.arrayBuffer()));
console.log(inspect.ndjson.slice(0, 8000));
