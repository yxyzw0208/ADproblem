from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[2] / "knowledge_graph"
OLD_XLSX = ROOT / "Swiss_AD共同靶点分析_20260814" / "最终交付" / "01_Swiss预测靶点与AD交集.xlsx"
NEW_CSV = ROOT / "最终交付_SwissAD全分子_20260818" / "02_中药-分子-靶点-AD完整路径.csv"
OUT = ROOT / "Script for Drawing Targeted Network Diagrams and QA Records" / "remaining_targets_only_plot_input.csv"
AUDIT = ROOT / "Script for Drawing Targeted Network Diagrams and QA Records" / "new_old_targets_diff_audit.json"


def old_targets() -> set[str]:
    workbook = openpyxl.load_workbook(OLD_XLSX, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    headers = [str(value or "").strip() for value in next(rows)]
    index = headers.index("UniProt编号")
    values = {str(row[index] or "").strip().upper() for row in rows if row[index]}
    workbook.close()
    return values


def main() -> None:
    prior = old_targets()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    all_new: set[str] = set()
    remaining: set[str] = set()
    source_rows = kept_rows = 0
    with NEW_CSV.open("r", encoding="utf-8-sig", newline="") as source, OUT.open("w", encoding="utf-8-sig", newline="") as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            source_rows += 1
            accession = str(row["Swiss预测靶点UniProt编号"]).strip().upper()
            all_new.add(accession)
            if accession not in prior:
                writer.writerow(row)
                remaining.add(accession)
                kept_rows += 1
    payload = {
        "old_pdf_corresponding_target_set_source": str(OLD_XLSX),
        "old_target_count": len(prior),
        "new_target_count": len(all_new),
        "overlap_target_count": len(all_new & prior),
        "remaining_target_count": len(remaining),
        "remaining_target_accessions": sorted(remaining),
        "source_path_rows": source_rows,
        "remaining_path_rows": kept_rows,
        "filter_key": "Swiss预测靶点UniProt编号 exact set difference",
    }
    AUDIT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
