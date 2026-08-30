from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


API = "https://rest.uniprot.org/uniprotkb/search"
FIELDS = "accession,protein_name,gene_primary,reviewed,organism_id"


def read_accessions(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        values = {
            str(row.get("UniProt编号", "")).strip().upper()
            for row in csv.DictReader(handle)
            if str(row.get("UniProt编号", "")).strip()
        }
    return sorted(values)


def chunks(values: list[str], size: int):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_batch(accessions: list[str], attempts: int = 4) -> list[dict[str, str]]:
    query = " OR ".join(f"accession:{value}" for value in accessions)
    params = urllib.parse.urlencode({"query": f"({query})", "format": "tsv", "fields": FIELDS, "size": 500})
    url = f"{API}?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "Codex-AD-target-normalization/1.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
            return list(csv.DictReader(io.StringIO(text), delimiter="\t"))
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(attempt * 2)
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    requested = read_accessions(args.input_csv)
    rows: list[dict[str, str]] = []
    for index, batch in enumerate(chunks(requested, args.batch_size), start=1):
        rows.extend(fetch_batch(batch))
        print(f"batch {index}: requested={len(batch)} cumulative_returned={len(rows)}", flush=True)

    by_accession = {row.get("Entry", "").strip().upper(): row for row in rows if row.get("Entry")}
    output_fields = [
        "UniProt编号",
        "UniProt推荐蛋白名称",
        "UniProt主Gene Symbol",
        "UniProt审核状态",
        "Organism ID",
        "UniProt查询链接",
        "查询状态",
    ]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        for accession in requested:
            row = by_accession.get(accession, {})
            writer.writerow(
                {
                    "UniProt编号": accession,
                    "UniProt推荐蛋白名称": row.get("Protein names", ""),
                    "UniProt主Gene Symbol": row.get("Gene Names (primary)", ""),
                    "UniProt审核状态": row.get("Reviewed", ""),
                    "Organism ID": row.get("Organism (ID)", ""),
                    "UniProt查询链接": f"https://www.uniprot.org/uniprotkb/{accession}",
                    "查询状态": "returned" if row else "not_returned",
                }
            )
    summary = {
        "requested": len(requested),
        "returned_exact_primary_accessions": len(by_accession),
        "not_returned": sorted(set(requested) - set(by_accession)),
        "endpoint": API,
        "fields": FIELDS,
    }
    args.output_csv.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
