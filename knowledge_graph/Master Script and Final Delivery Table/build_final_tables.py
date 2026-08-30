from __future__ import annotations

import csv
import html
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "knowledge_graph"
WORK = ROOT
TASK1 = WORK / "Intersection of Swiss predicted targets and AD targets" / "swiss_ad_common_targets_normalized_dedup.csv"
TASK1_AUDIT = WORK / "Intersection of Swiss predicted targets and AD targets" / "swiss_ad_intersection_edge_audit.csv"
HERB_MOL = WORK / "Traditional Chinese Medicine—Molecule—TCMSP Target Index Table" / "01_tcm_molecule_dedup_long_table.csv"
TCMSP = WORK / "Traditional Chinese Medicine—Molecule—TCMSP Target Index Table" / "02_tcm_molecule_tcmsp_targets_uniprot_dedup_long_table.csv"
EVIDENCE = WORK / "Traditional Chinese Medicine—Molecule—TCMSP Target Index Table" / "03_ad_evidence_uniprot_index.csv"
UNIPROT = WORK / "Master Script and Final Delivery Table" / "uniprot_official_names_1035_targets.csv"
TCMSP_SUPPLEMENT = WORK / "Master Script and Final Delivery Table" / "uniprot_completion_tcmsp_missing_targets.csv"
OUT1 = WORK / "Master Script and Final Delivery Table" / "01_swiss_predicted_targets_ad_intersection_final.csv"
OUT2 = WORK / "Master Script and Final Delivery Table" / "02_tcm_molecule_target_ad_full_paths_final.csv"
DB = WORK / "Master Script and Final Delivery Table" / "final_join.sqlite"
QC = WORK / "Master Script and Final Delivery Table" / "final_data_qc.json"


def clean(value: object) -> str:
    return " ".join(html.unescape(str(value or "")).replace("\xa0", " ").split())


def mol_key(value: object) -> str:
    text = clean(value)
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def read_dict(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {clean(row[key]).upper(): {k: clean(v) for k, v in row.items()} for row in csv.DictReader(handle)}


def ordered_join(values: list[str]) -> str:
    return "; ".join(dict.fromkeys(value for value in values if value))


def prepare_tcmsp() -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, int]]:
    supplements = read_dict(TCMSP_SUPPLEMENT, "TCMSP靶点Gene Symbol")
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    missing_before = missing_after = 0
    with TCMSP.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = {key: clean(value) for key, value in raw.items()}
            key = (row["中药中文名"], row["TCMSP MOL_ID"].upper())
            accession = row.get("TCMSP靶点UniProt编号", "").upper()
            if not accession:
                missing_before += 1
                supplement = supplements.get(row["TCMSP靶点Gene Symbol"].upper(), {})
                accession = supplement.get("UniProt编号", "").upper()
                if accession:
                    row["TCMSP靶点UniProt标准Gene Symbol"] = supplement.get("UniProt主Gene Symbol", row["TCMSP靶点Gene Symbol"])
                row["TCMSP靶点UniProt编号"] = accession
            if not accession:
                missing_after += 1
            grouped[key].append(row)

    aggregate: dict[tuple[str, str], dict[str, str]] = {}
    for key, rows in grouped.items():
        rows.sort(key=lambda row: (row["TCMSP靶点Gene Symbol"], row.get("TCMSP靶点UniProt编号", "")))
        aggregate[key] = {
            "TCMSP分子对应靶点名称": ordered_join([row["TCMSP靶点名称"] for row in rows]),
            "TCMSP分子对应靶点Gene Symbol": ordered_join([row["TCMSP靶点Gene Symbol"] for row in rows]),
            "TCMSP分子对应靶点UniProt编号": ordered_join([row.get("TCMSP靶点UniProt编号", "") for row in rows]),
        }
    return aggregate, {"rows_missing_uniprot_before_supplement": missing_before, "rows_missing_uniprot_after_supplement": missing_after}


def build_task1(uniprot: dict[str, dict[str, str]]) -> dict[str, int]:
    headers = ["中药小分子", "UniProt编号", "靶点名称", "Gene Symbol", "预测概率", "查询网站"]
    dedup: dict[tuple[str, str], dict[str, object]] = {}
    source_rows = 0
    with TASK1.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        for raw in reader:
            source_rows += 1
            accession = clean(raw["UniProt编号"]).upper()
            official = uniprot.get(accession, {})
            name = official.get("UniProt推荐蛋白名称", "") or clean(raw["靶点名称"])
            gene = official.get("UniProt主Gene Symbol", "") or clean(raw["Gene Symbol"])
            molecule = clean(raw["中药小分子"])
            record = {
                "中药小分子": molecule,
                "UniProt编号": accession,
                "靶点名称": name,
                "Gene Symbol": gene,
                "预测概率": float(raw["预测概率"]),
                "查询网站": clean(raw["查询网站"]),
            }
            key = (molecule.casefold(), accession)
            if key not in dedup or record["预测概率"] > dedup[key]["预测概率"]:
                dedup[key] = record
    records = sorted(
        dedup.values(),
        key=lambda row: (str(row["Gene Symbol"]), -float(row["预测概率"]), str(row["中药小分子"]).casefold()),
    )
    with OUT1.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)
    return {
        "source_rows_before_display_dedup": source_rows,
        "rows": len(records),
        "duplicate_name_target_rows_removed": source_rows - len(records),
        "unique_targets": len({str(row["UniProt编号"]) for row in records}),
        "unique_molecules_by_name": len({str(row["中药小分子"]).casefold() for row in records}),
    }


def create_join_db(uniprot: dict[str, dict[str, str]], evidence: dict[str, dict[str, str]], tcmsp: dict[tuple[str, str], dict[str, str]]) -> tuple[sqlite3.Connection, dict[str, int]]:
    if DB.exists():
        DB.unlink()
    connection = sqlite3.connect(DB)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute(
        "CREATE TABLE herb_mol (herb TEXT, molecule TEXT, mol_id TEXT, molecule_id TEXT, t_names TEXT, t_genes TEXT, t_accessions TEXT)"
    )
    herb_rows = 0
    with HERB_MOL.open("r", encoding="utf-8-sig", newline="") as handle:
        batch = []
        for raw in csv.DictReader(handle):
            herb = clean(raw["中药中文名"])
            mol_id = clean(raw["TCMSP MOL_ID"]).upper()
            agg = tcmsp.get((herb, mol_id), {})
            batch.append(
                (
                    herb,
                    clean(raw["中药小分子"]),
                    mol_id,
                    mol_key(raw["molecule_ID"]),
                    agg.get("TCMSP分子对应靶点名称", ""),
                    agg.get("TCMSP分子对应靶点Gene Symbol", ""),
                    agg.get("TCMSP分子对应靶点UniProt编号", ""),
                )
            )
            if len(batch) >= 5000:
                connection.executemany("INSERT INTO herb_mol VALUES (?,?,?,?,?,?,?)", batch)
                herb_rows += len(batch)
                batch.clear()
        if batch:
            connection.executemany("INSERT INTO herb_mol VALUES (?,?,?,?,?,?,?)", batch)
            herb_rows += len(batch)
    connection.execute("CREATE INDEX idx_herb_mol_molecule_id ON herb_mol(molecule_id)")

    connection.execute(
        "CREATE TABLE edge (molecule_id TEXT, accession TEXT, target_name TEXT, gene TEXT, probability REAL, query_url TEXT)"
    )
    edge_rows = 0
    with TASK1_AUDIT.open("r", encoding="utf-8-sig", newline="") as handle:
        batch = []
        for raw in csv.DictReader(handle):
            accession = clean(raw["UniProt编号"]).upper()
            official = uniprot.get(accession, {})
            batch.append(
                (
                    mol_key(raw["规范化molecule_ID"]),
                    accession,
                    official.get("UniProt推荐蛋白名称", "") or clean(raw["靶点名称"]),
                    official.get("UniProt主Gene Symbol", "") or clean(raw["Gene Symbol"]),
                    float(raw["预测概率"]),
                    clean(raw["查询网站"]),
                )
            )
            if len(batch) >= 10000:
                connection.executemany("INSERT INTO edge VALUES (?,?,?,?,?,?)", batch)
                edge_rows += len(batch)
                batch.clear()
        if batch:
            connection.executemany("INSERT INTO edge VALUES (?,?,?,?,?,?)", batch)
            edge_rows += len(batch)
    connection.execute("CREATE INDEX idx_edge_molecule_id ON edge(molecule_id)")
    connection.execute("CREATE INDEX idx_edge_accession ON edge(accession)")

    connection.execute(
        "CREATE TABLE evidence (accession TEXT PRIMARY KEY, ad_gene TEXT, sentence TEXT, pmid TEXT, pubmed_url TEXT)"
    )
    connection.executemany(
        "INSERT INTO evidence VALUES (?,?,?,?,?)",
        [
            (
                accession,
                row.get("AD标准Gene Symbol", ""),
                row.get("AD相关证明句（英文原文）", ""),
                row.get("PMID", ""),
                row.get("PubMed链接", ""),
            )
            for accession, row in evidence.items()
        ],
    )
    connection.commit()
    return connection, {"herb_molecule_rows": herb_rows, "edge_rows": edge_rows}


def write_task2(connection: sqlite3.Connection) -> dict[str, int]:
    headers = [
        "中药名称",
        "中药分子",
        "TCMSP MOL_ID",
        "molecule_ID",
        "TCMSP分子对应靶点名称",
        "TCMSP分子对应靶点Gene Symbol",
        "TCMSP分子对应靶点UniProt编号",
        "Swiss预测靶点名称",
        "Swiss预测靶点Gene Symbol",
        "Swiss预测靶点UniProt编号",
        "Swiss预测概率",
        "Swiss查询网站",
        "AD相关证明句（英文原文）",
        "PMID",
        "PubMed链接",
    ]
    query = """
        SELECT h.herb, h.molecule, h.mol_id, h.molecule_id,
               h.t_names, h.t_genes, h.t_accessions,
               e.target_name, e.gene, e.accession, e.probability, e.query_url,
               a.sentence, a.pmid, a.pubmed_url
        FROM edge e
        JOIN herb_mol h ON h.molecule_id = e.molecule_id
        JOIN evidence a ON a.accession = e.accession
        ORDER BY e.accession, e.probability DESC, h.herb, h.molecule, h.mol_id
    """
    row_count = 0
    targets: set[str] = set()
    herbs: set[str] = set()
    molecules: set[str] = set()
    missing = {header: 0 for header in headers}
    with OUT2.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        cursor = connection.execute(query)
        for row in cursor:
            cleaned = [clean(value) if index != 10 else value for index, value in enumerate(row)]
            writer.writerow(cleaned)
            row_count += 1
            targets.add(cleaned[9])
            herbs.add(cleaned[0])
            molecules.add(cleaned[3])
            for index, value in enumerate(cleaned):
                if value == "" or value is None:
                    missing[headers[index]] += 1
    return {
        "rows": row_count,
        "unique_targets": len(targets),
        "unique_herbs": len(herbs),
        "unique_molecule_ids": len(molecules),
        "missing_required_cells": missing,
    }


def main() -> None:
    uniprot = read_dict(UNIPROT, "UniProt编号")
    evidence = read_dict(EVIDENCE, "AD靶点UniProt编号")
    tcmsp, tcmsp_qc = prepare_tcmsp()
    task1_qc = build_task1(uniprot)
    connection, join_qc = create_join_db(uniprot, evidence, tcmsp)
    task2_qc = write_task2(connection)
    connection.close()
    payload = {
        "task1": task1_qc,
        "task2": task2_qc,
        "tcmsp": {**tcmsp_qc, "aggregated_herb_molecule_keys": len(tcmsp)},
        "join_inputs": join_qc,
        "uniprot_official_targets": len(uniprot),
        "ad_evidence_targets": len(evidence),
        "unmapped_swiss_molecule_without_herb_source": "molecule_ID 8854 / STP03552",
    }
    QC.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
