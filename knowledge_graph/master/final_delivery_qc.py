from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import openpyxl
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "最终交付_SwissAD全分子_20260818"
XLSX = DELIVERY / "01_Swiss预测靶点与AD交集.xlsx"
CSV = DELIVERY / "02_中药-分子-靶点-AD完整路径.csv"
PDF = DELIVERY / "03_剩余161个共同靶点网络可视化.pdf"
OUT = ROOT / "knowledge_graph" / "master" / "final_delivery_qc.json"

XLSX_HEADERS = ["中药小分子", "UniProt编号", "靶点名称", "Gene Symbol", "预测概率", "查询网站"]
CSV_HEADERS = [
    "中药名称", "中药分子", "TCMSP MOL_ID", "molecule_ID",
    "TCMSP分子对应靶点名称", "TCMSP分子对应靶点Gene Symbol", "TCMSP分子对应靶点UniProt编号",
    "Swiss预测靶点名称", "Swiss预测靶点Gene Symbol", "Swiss预测靶点UniProt编号",
    "Swiss预测概率", "Swiss查询网站", "AD相关证明句（英文原文）", "PMID", "PubMed链接",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_xlsx() -> dict[str, object]:
    workbook = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    headers = list(next(rows))
    count = 0
    missing = [0] * len(headers)
    targets: set[str] = set()
    duplicate_keys = 0
    seen: set[tuple[str, str]] = set()
    for row in rows:
        count += 1
        for index, value in enumerate(row):
            if value is None or str(value).strip() == "":
                missing[index] += 1
        key = (str(row[0]).casefold(), str(row[1]))
        duplicate_keys += key in seen
        seen.add(key)
        targets.add(str(row[1]))
    workbook.close()
    return {
        "headers": headers,
        "header_match": headers == XLSX_HEADERS,
        "rows": count,
        "missing_by_column": dict(zip(headers, missing)),
        "duplicate_name_target_keys": duplicate_keys,
        "unique_targets": len(targets),
    }


def check_csv() -> dict[str, object]:
    with CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        count = 0
        missing = {header: 0 for header in headers}
        targets: set[str] = set()
        herbs: set[str] = set()
        molecules: set[str] = set()
        duplicate_paths = 0
        seen_paths: set[tuple[str, str, str]] = set()
        for row in reader:
            count += 1
            for header in headers:
                if not str(row.get(header, "")).strip():
                    missing[header] += 1
            key = (row["中药名称"], row["molecule_ID"], row["Swiss预测靶点UniProt编号"])
            duplicate_paths += key in seen_paths
            seen_paths.add(key)
            targets.add(row["Swiss预测靶点UniProt编号"])
            herbs.add(row["中药名称"])
            molecules.add(row["molecule_ID"])
    return {
        "headers": headers,
        "header_match": headers == CSV_HEADERS,
        "rows": count,
        "missing_by_column": missing,
        "duplicate_path_keys": duplicate_paths,
        "unique_targets": len(targets),
        "unique_herbs": len(herbs),
        "unique_molecules": len(molecules),
    }


def main() -> None:
    files = [XLSX, CSV, PDF]
    if not all(path.exists() and path.stat().st_size for path in files):
        raise RuntimeError("One or more final delivery files are missing or empty")
    payload = {
        "final_files": [path.name for path in files],
        "final_file_count": len(files),
        "xlsx": check_xlsx(),
        "csv": check_csv(),
        "pdf": {"pages": len(PdfReader(PDF).pages)},
        "sha256": {path.name: sha256(path) for path in files},
    }
    payload["pass"] = (
        payload["xlsx"]["header_match"]
        and payload["xlsx"]["duplicate_name_target_keys"] == 0
        and not any(payload["xlsx"]["missing_by_column"].values())
        and payload["csv"]["header_match"]
        and payload["csv"]["duplicate_path_keys"] == 0
        and not any(payload["csv"]["missing_by_column"].values())
        and payload["pdf"]["pages"] == 161
        and payload["final_file_count"] == 3
    )
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
