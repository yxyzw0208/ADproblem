from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "01_swiss_predicted_targets_ad_intersection_final.csv"
TARGET = ROOT / "artifact_final" / "task1_rows.ndjson"


def main() -> None:
    count = 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as source, TARGET.open("w", encoding="utf-8", newline="\n") as target:
        reader = csv.reader(source)
        header = next(reader)
        probability_index = header.index("预测概率")
        target.write(json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n")
        for row in reader:
            row[probability_index] = float(row[probability_index])
            target.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    print(json.dumps({"rows": count, "columns": len(header)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
