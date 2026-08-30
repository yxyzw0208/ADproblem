from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path


API = "https://rest.uniprot.org/uniprotkb/search"
FIELDS = "accession,protein_name,gene_primary,reviewed,organism_id"


def fetch_gene(gene: str) -> list[dict[str, str]]:
    params = urllib.parse.urlencode(
        {
            "query": f"(gene_exact:{gene}) AND (organism_id:9606) AND (reviewed:true)",
            "format": "tsv",
            "fields": FIELDS,
            "size": 100,
        }
    )
    request = urllib.request.Request(
        f"{API}?{params}", headers={"User-Agent": "Codex-TCMSP-UniProt-normalization/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return list(csv.DictReader(io.StringIO(response.read().decode("utf-8")), delimiter="\t"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    with args.input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        genes = sorted({row["TCMSP靶点Gene Symbol"].strip().upper() for row in csv.DictReader(handle)})
    output: list[dict[str, str]] = []
    for gene in genes:
        rows = fetch_gene(gene)
        exact = [row for row in rows if row.get("Gene Names (primary)", "").strip().upper() == gene]
        status = "unique_exact" if len(exact) == 1 else f"ambiguous_or_missing:{len(exact)}"
        row = exact[0] if len(exact) == 1 else {}
        output.append(
            {
                "TCMSP靶点Gene Symbol": gene,
                "UniProt编号": row.get("Entry", ""),
                "UniProt推荐蛋白名称": row.get("Protein names", ""),
                "UniProt主Gene Symbol": row.get("Gene Names (primary)", ""),
                "UniProt审核状态": row.get("Reviewed", ""),
                "Organism ID": row.get("Organism (ID)", ""),
                "UniProt查询链接": f"https://www.uniprot.org/uniprotkb/{row.get('Entry', '')}" if row else "",
                "查询状态": status,
            }
        )
        print(gene, status, row.get("Entry", ""), flush=True)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    summary = {"genes": len(genes), "unique_exact": sum(x["查询状态"] == "unique_exact" for x in output)}
    args.output_csv.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
