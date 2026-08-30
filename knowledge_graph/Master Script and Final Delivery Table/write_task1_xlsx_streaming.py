from __future__ import annotations

import csv
from pathlib import Path

import xlsxwriter


ROOT = Path(r"D:\codex\大创")
SOURCE = ROOT / "本轮任务_20260818" / "主控" / "01_swiss_predicted_targets_ad_intersection_final.csv"
OUTPUT = ROOT / "最终交付_SwissAD全分子_20260818" / "01_Swiss预测靶点与AD交集.xlsx"
EXPECTED_HEADERS = ["中药小分子", "UniProt编号", "靶点名称", "Gene Symbol", "预测概率", "查询网站"]


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(
        OUTPUT,
        {
            "constant_memory": True,
            "strings_to_urls": False,
            "strings_to_formulas": False,
        },
    )
    worksheet = workbook.add_worksheet("Swiss∩AD共同靶点")
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(1, 0)
    worksheet.set_column("A:A", 30)
    worksheet.set_column("B:B", 15)
    worksheet.set_column("C:C", 58)
    worksheet.set_column("D:D", 18)
    worksheet.set_column("E:E", 16)
    worksheet.set_column("F:F", 72)
    worksheet.set_row(0, 34)

    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#25577F",
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "bottom": 2,
            "bottom_color": "#173A5E",
        }
    )
    probability_format = workbook.add_format({"num_format": "0.000000000"})

    with SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader)
        if headers != EXPECTED_HEADERS:
            raise RuntimeError(f"Unexpected headers: {headers!r}")
        worksheet.write_row(0, 0, headers, header_format)
        row_index = 1
        for row in reader:
            if len(row) != len(EXPECTED_HEADERS):
                raise RuntimeError(f"Unexpected column count at source row {row_index + 1}")
            worksheet.write_row(row_index, 0, row[:4])
            worksheet.write_number(row_index, 4, float(row[4]), probability_format)
            worksheet.write_string(row_index, 5, row[5])
            row_index += 1

    worksheet.autofilter(0, 0, row_index - 1, len(EXPECTED_HEADERS) - 1)
    workbook.close()
    print(f"rows={row_index - 1}")
    print(f"output={OUTPUT}")


if __name__ == "__main__":
    main()
