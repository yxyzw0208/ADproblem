"""Offline, provenance-first SwissTargetPrediction × AD target intersection.

Inputs are immutable.  The program uses only project-local, previously
standardized UniProt data; it does not perform network lookups or infer
protein identities from accession patterns.  It emits a compact delivery CSV
and separate audit tables for every mapping and exclusion decision.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import iterparse

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SWISS_XLSX = ROOT / "小分子-靶点（swiss预测靶点）.xlsx"
AD_CSV = ROOT / "AD基因靶点及命名标准化" / "04_UniProt靶点标准化" / "采用uniprot去除靶点数据集（3699条数据记录）（数据集优先使用）.csv"
MOLECULE_CSV = ROOT / "中药小分子靶点_UniProt标准化结果_20260810" / "中药小分子靶点_UniProt标准化.csv"
FULL_TCM_XLSX = ROOT / "AD_中药_小分子_作用靶点_全量表.xlsx"
FULL_TCM_SHEET = "小分子汇总排名"

DELIVERY = OUT / "swiss_ad_common_targets_normalized_dedup.csv"
EDGE_AUDIT = OUT / "swiss_ad_intersection_edge_audit.csv"
UNMATCHED = OUT / "swiss_ad_intersection_unmatched_records.csv"
SUMMARY = OUT / "swiss_ad_intersection_audit_summary.json"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ACCESSION_RE = re.compile(
    r"(?<![A-Z0-9])(?:A0A[A-Z0-9]{7}|[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z0-9]{3}[0-9])(?:-\d+)?(?![A-Z0-9])",
    re.I,
)


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalized_gene(value: object) -> str:
    """Treat Swiss export placeholders as missing, never as a Gene Symbol."""
    gene = clean(value)
    return "" if gene.casefold() in {"n/a", "na", "none", "null", "-", "."} else gene


def field_key(value: object) -> str:
    return re.sub(r"\s+", "", clean(value)).casefold()


def mol_key(value: object) -> str:
    """Normalize TCMSP numeric molecule IDs without conflating nonnumeric IDs."""
    text = clean(value)
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        return str(int(float(text)))
    return text.casefold()


def parse_accessions(value: object) -> list[str]:
    found: list[str] = []
    for token in ACCESSION_RE.findall(clean(value).upper()):
        primary = re.sub(r"-\d+$", "", token)
        if primary not in found:
            found.append(primary)
    return found


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def excel_col_to_index(reference: str) -> int:
    value = 0
    for char in "".join(ch for ch in reference if ch.isalpha()):
        value = value * 26 + ord(char.upper()) - 64
    return value - 1


def shared_strings(book: zipfile.ZipFile) -> list[str]:
    strings: list[str] = []
    if "xl/sharedStrings.xml" not in book.namelist():
        return strings
    with book.open("xl/sharedStrings.xml") as handle:
        for _, element in iterparse(handle, events=("end",)):
            if element.tag == NS + "si":
                strings.append("".join(node.text or "" for node in element.iter(NS + "t")))
                element.clear()
    return strings


def sheet_xml_path(book: zipfile.ZipFile, wanted_sheet: str) -> str:
    """Resolve a workbook sheet title to its worksheet XML path."""
    workbook_xml = book.read("xl/workbook.xml")
    root = __import__("xml.etree.ElementTree", fromlist=["fromstring"]).fromstring(workbook_xml)
    relationship_id = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    relation = None
    for sheet in root.iter(NS + "sheet"):
        if sheet.get("name") == wanted_sheet:
            relation = sheet.get(relationship_id)
            break
    if not relation:
        raise RuntimeError(f"Worksheet not found: {wanted_sheet}")
    rel_root = __import__("xml.etree.ElementTree", fromlist=["fromstring"]).fromstring(book.read("xl/_rels/workbook.xml.rels"))
    for item in rel_root:
        if item.get("Id") == relation:
            target = item.get("Target", "")
            return target.lstrip("/") if target.startswith("xl/") else "xl/" + target.lstrip("/")
    raise RuntimeError(f"Missing workbook relationship for sheet: {wanted_sheet}")


def iter_xlsx_rows(path: Path, sheet_name: str | None = None):
    """Stream a flat sheet without loading the large source workbook into RAM."""
    with zipfile.ZipFile(path) as book:
        strings = shared_strings(book)
        xml_path = sheet_xml_path(book, sheet_name) if sheet_name else "xl/worksheets/sheet1.xml"
        with book.open(xml_path) as handle:
            for _, element in iterparse(handle, events=("end",)):
                if element.tag != NS + "row":
                    continue
                row: dict[int, str] = {}
                for cell in element.findall(NS + "c"):
                    column = excel_col_to_index(cell.get("r", "A1"))
                    cell_type = cell.get("t")
                    value_node = cell.find(NS + "v")
                    value = "" if value_node is None else (value_node.text or "")
                    if cell_type == "s" and value:
                        value = strings[int(value)]
                    elif cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(NS + "t"))
                    row[column] = value
                yield row
                element.clear()


def csv_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def value(row: dict[int, str], index: dict[str, int], *aliases: str) -> str:
    for alias in aliases:
        col = index.get(field_key(alias))
        if col is not None:
            return clean(row.get(col))
    return ""


def load_ad() -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], Counter[str]]:
    by_accession: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_gene: dict[str, list[dict[str, str]]] = defaultdict(list)
    status: Counter[str] = Counter()
    for row in csv_rows(AD_CSV):
        accession = clean(row.get("uniprotkb_primary_accession")).upper()
        gene = clean(row.get("hgnc_symbol")).upper()
        if accession:
            by_accession[accession].append(row)
        if gene:
            by_gene[gene].append(row)
        status[clean(row.get("accession_verification"))] += 1
    return by_accession, by_gene, status


def load_molecules() -> tuple[dict[str, list[dict[str, str]]], Counter[str]]:
    """Index approved project molecule labels by normalized molecule_ID.

    The current Swiss export omits molecule names/MOL IDs.  Exact molecule_ID
    is therefore primary; source SMILES can resolve an otherwise ambiguous key.
    """
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    rows = iter_xlsx_rows(FULL_TCM_XLSX, FULL_TCM_SHEET)
    header = next(rows)
    headers = [header.get(i, "") for i in range(max(header) + 1)]
    positions = {field_key(name): pos for pos, name in enumerate(headers) if field_key(name)}
    required = ["molecule_ID", "中药小分子", "TCMSP MOL_ID"]
    missing = [x for x in required if field_key(x) not in positions]
    if missing:
        raise RuntimeError(f"Full molecule sheet misses {missing}; headers={headers}")
    for row in rows:
        key = mol_key(value(row, positions, "molecule_ID"))
        name = value(row, positions, "中药小分子")
        mol_id = value(row, positions, "TCMSP MOL_ID")
        smiles = value(row, positions, "SMILES")
        if not key or not name:
            continue
        item = {"molecule_ID": key, "name": name, "mol_id": mol_id, "smiles": smiles, "source": "AD_中药_小分子_作用靶点_全量表/小分子汇总排名"}
        signature = (item["name"], item["mol_id"], item["smiles"])
        if signature not in {(x["name"], x["mol_id"], x["smiles"]) for x in index[key]}:
            index[key].append(item)
        counts[item["source"]] += 1
    return index, counts


def resolve_molecule(raw_id: str, raw_smiles: str, molecules: dict[str, list[dict[str, str]]]) -> tuple[dict[str, str] | None, str, int]:
    key = mol_key(raw_id)
    candidates = molecules.get(key, [])
    if len(candidates) == 1:
        return candidates[0], "molecule_ID_exact_unique", 1
    if len(candidates) > 1 and raw_smiles:
        exact = [x for x in candidates if x["smiles"] and x["smiles"] == raw_smiles]
        if len(exact) == 1:
            return exact[0], "molecule_ID_plus_SMILES_exact_unique", len(candidates)
        if len(exact) > 1:
            return None, "molecule_ID_plus_SMILES_multiple_candidates", len(candidates)
    if len(candidates) > 1:
        return None, "molecule_ID_ambiguous", len(candidates)
    return None, "molecule_ID_not_found_in_project_mapping", 0


def num(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return float("-inf")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    by_acc, by_gene, verification = load_ad()
    molecules, molecule_source_rows = load_molecules()
    rows = iter_xlsx_rows(SWISS_XLSX)
    header_row = next(rows)
    headers = [header_row.get(i, "") for i in range(max(header_row) + 1)]
    index = {field_key(name): pos for pos, name in enumerate(headers) if field_key(name)}
    required = ["molecule_ID", "靶点名称", "Gene Symbol", "UniProt ID", "概率"]
    missing = [name for name in required if field_key(name) not in index]
    if missing:
        raise RuntimeError(f"Swiss source lacks required fields {missing}; actual headers={headers}")

    source_rows = 0
    source_accession_blank = source_accession_multi = 0
    source_gene_blank = probability_blank = probability_bad = 0
    source_target_names: Counter[str] = Counter()
    molecule_resolution: Counter[str] = Counter()
    ad_match_basis: Counter[str] = Counter()
    gene_consistency: Counter[str] = Counter()
    rejected: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    unique_source_molecules: set[str] = set()
    unique_source_queries: set[str] = set()
    unique_source_accessions: set[str] = set()

    for source_number, row in enumerate(rows, 2):
        source_rows += 1
        raw_molecule_id = value(row, index, "molecule_ID")
        raw_smiles = value(row, index, "SMILES")
        source_query = value(row, index, "STP查询编号", "STP query ID")
        source_row_no = value(row, index, "原始行号") or str(source_number)
        raw_accession = value(row, index, "UniProt ID", "UniProt_ID")
        source_gene = normalized_gene(value(row, index, "Gene Symbol", "Gene symbol"))
        source_target = value(row, index, "靶点名称", "Target name")
        probability = value(row, index, "概率", "Probability")
        rank = value(row, index, "预测排名", "Rank")
        job_id = value(row, index, "STP Job ID", "STP JobID")
        url = value(row, index, "结果URL", "查询网站", "Result URL")
        if not url and job_id:
            url = f"https://www.swisstargetprediction.ch/result.php?job={job_id}&organism=Homo_sapiens"
        query_key = source_query or mol_key(raw_molecule_id) or source_row_no
        unique_source_molecules.add(mol_key(raw_molecule_id))
        unique_source_queries.add(query_key)
        source_target_names[source_target] += 1
        if not probability:
            probability_blank += 1
        elif num(probability) == float("-inf"):
            probability_bad += 1
        if not source_gene:
            source_gene_blank += 1

        molecule, molecule_basis, n_candidates = resolve_molecule(raw_molecule_id, raw_smiles, molecules)
        molecule_resolution[molecule_basis] += 1
        accessions = parse_accessions(raw_accession)
        if not accessions:
            source_accession_blank += 1
        if len(accessions) > 1:
            source_accession_multi += 1

        # UniProt primary accession exact match is authoritative.  A gene-symbol
        # fallback is only permitted where the source accession is absent and the
        # existing AD cache has exactly one primary accession for that symbol.
        matching: list[tuple[str, dict[str, str], str]] = []
        for accession in accessions:
            unique_source_accessions.add(accession)
            for ad in by_acc.get(accession, []):
                matching.append((accession, ad, "UniProt_primary_accession_exact"))
        if not matching and not accessions and source_gene:
            gene_matches = by_gene.get(source_gene.upper(), [])
            unique_acc = {clean(x.get("uniprotkb_primary_accession")).upper() for x in gene_matches}
            if len(unique_acc) == 1 and gene_matches:
                matching.append((next(iter(unique_acc)), gene_matches[0], "Gene_Symbol_exact_unique_AD_fallback"))

        if not molecule:
            rejected.append({
                "排除原因": molecule_basis, "Swiss原始行号": source_row_no, "Swiss_molecule_ID": raw_molecule_id,
                "Swiss_SMILES": raw_smiles, "Swiss_STP查询编号": source_query, "Swiss_UniProt原始值": raw_accession,
                "Swiss_Gene_Symbol": source_gene, "Swiss_靶点名称": source_target, "预测概率": probability,
                "AD匹配状态": "未进入AD匹配：小分子名称无法由项目规范化molecule_ID确定", "映射候选数": n_candidates,
            })
            continue
        if not matching:
            reason = "Swiss_UniProt未与AD标准化集合相交"
            if not accessions:
                reason = "Swiss_UniProt空白或无法解析，且无唯一AD_Gene_Symbol回退"
            rejected.append({
                "排除原因": reason, "Swiss原始行号": source_row_no, "Swiss_molecule_ID": raw_molecule_id,
                "Swiss_SMILES": raw_smiles, "Swiss_STP查询编号": source_query, "Swiss_UniProt原始值": raw_accession,
                "Swiss_Gene_Symbol": source_gene, "Swiss_靶点名称": source_target, "预测概率": probability,
                "AD匹配状态": "未匹配", "映射候选数": n_candidates,
            })
            continue

        for accession, ad, match_basis in matching:
            ad_match_basis[match_basis] += 1
            ad_gene = clean(ad.get("hgnc_symbol"))
            if source_gene and ad_gene:
                gene_flag = "Swiss与AD_Gene_Symbol一致" if source_gene.upper() == ad_gene.upper() else "Swiss与AD_Gene_Symbol不一致"
            elif source_gene:
                gene_flag = "AD_Gene_Symbol缺失"
            else:
                gene_flag = "Swiss_Gene_Symbol缺失，采用AD_HGNC"
            gene_consistency[gene_flag] += 1
            candidates.append({
                "中药小分子": molecule["name"], "UniProt编号": accession, "靶点名称": source_target,
                # AD master contains the project-local HGNC-standard symbol and
                # is authoritative after the accession-level exact match.
                "Gene Symbol": ad_gene or source_gene, "预测概率": probability, "查询网站": url,
                "Swiss原始行号": source_row_no, "Swiss_molecule_ID": raw_molecule_id,
                "规范化molecule_ID": molecule["molecule_ID"], "TCMSP MOL_ID": molecule["mol_id"],
                "Swiss_SMILES": raw_smiles, "Swiss_STP查询编号": source_query, "Swiss_预测排名": rank,
                "Swiss_UniProt原始值": raw_accession, "Swiss_Gene_Symbol": source_gene,
                "小分子映射依据": molecule_basis, "小分子映射候选数": n_candidates,
                "AD匹配依据": match_basis, "Gene_Symbol一致性": gene_flag,
                "AD_HGNC_Gene_Symbol": ad_gene, "AD_HGNC_ID": clean(ad.get("hgnc_id")),
                "AD_UniProt官方验证": clean(ad.get("accession_verification")),
                "AD_UniProt审核状态": clean(ad.get("reviewed_status")),
            })

    # A molecule-target biological edge is the deduplication unit.  If repeated
    # Swiss submissions predict the same edge, retain highest probability; ties
    # retain the earliest source row for deterministic provenance.
    dedup: dict[tuple[str, str], dict[str, object]] = {}
    duplicate_edges = 0
    for record in candidates:
        key = (clean(record["规范化molecule_ID"]), clean(record["UniProt编号"]))
        prior = dedup.get(key)
        if prior is None:
            dedup[key] = record
        else:
            duplicate_edges += 1
            if (num(clean(record["预测概率"])), -int(clean(record["Swiss原始行号"]) or "999999999")) > (num(clean(prior["预测概率"])), -int(clean(prior["Swiss原始行号"]) or "999999999")):
                dedup[key] = record

    final_audit_rows = sorted(dedup.values(), key=lambda x: (clean(x["中药小分子"]).casefold(), clean(x["UniProt编号"])))
    delivery_fields = ["中药小分子", "UniProt编号", "靶点名称", "Gene Symbol", "预测概率", "查询网站"]
    audit_fields = delivery_fields + [
        "Swiss原始行号", "Swiss_molecule_ID", "规范化molecule_ID", "TCMSP MOL_ID", "Swiss_SMILES", "Swiss_STP查询编号", "Swiss_预测排名",
        "Swiss_UniProt原始值", "Swiss_Gene_Symbol", "小分子映射依据", "小分子映射候选数", "AD匹配依据", "Gene_Symbol一致性",
        "AD_HGNC_Gene_Symbol", "AD_HGNC_ID", "AD_UniProt官方验证", "AD_UniProt审核状态",
    ]
    rejected_fields = ["排除原因", "Swiss原始行号", "Swiss_molecule_ID", "Swiss_SMILES", "Swiss_STP查询编号", "Swiss_UniProt原始值", "Swiss_Gene_Symbol", "Swiss_靶点名称", "预测概率", "AD匹配状态", "映射候选数"]
    write_csv(DELIVERY, delivery_fields, final_audit_rows)
    write_csv(EDGE_AUDIT, audit_fields, final_audit_rows)
    write_csv(UNMATCHED, rejected_fields, rejected)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {str(SWISS_XLSX): sha256(SWISS_XLSX), str(AD_CSV): sha256(AD_CSV), str(FULL_TCM_XLSX): sha256(FULL_TCM_XLSX)},
        "swiss_workbook": {"sheet": "sheet1.xml", "headers": headers, "rows_excluding_header": source_rows, "unique_normalized_molecule_ID": len(unique_source_molecules), "unique_query_keys": len(unique_source_queries), "unique_normalized_uniprot_accessions": len(unique_source_accessions), "blank_or_unparseable_uniprot_rows": source_accession_blank, "multi_accession_rows": source_accession_multi, "blank_gene_symbol_rows": source_gene_blank, "blank_probability_rows": probability_blank, "non_numeric_probability_rows": probability_bad},
        "existing_AD_uniprot_master": {"rows": sum(len(v) for v in by_acc.values()), "unique_primary_accessions": len(by_acc), "unique_hgnc_symbols": len(by_gene), "accession_verification_counts": dict(verification), "source_scope": "ACCESSIBLE_SUBSET; see existing manifest.json"},
        "molecule_mapping": {"source_workbook": str(FULL_TCM_XLSX), "source_sheet": FULL_TCM_SHEET, "unique_normalized_molecule_ID_in_project_index": len(molecules), "source_rows_loaded": dict(molecule_source_rows), "resolution_counts": dict(molecule_resolution), "rule": "exact normalized molecule_ID from full 4209-row molecule sheet; only when that key has multiple candidates use exact source SMILES; no name-only mapping"},
        "intersection": {"expanded_matched_rows_before_edge_dedup": len(candidates), "duplicate_molecule_target_edges_removed": duplicate_edges, "rows_after_edge_dedup": len(final_audit_rows), "unique_matched_uniprot_accessions": len({x["UniProt编号"] for x in final_audit_rows}), "unique_matched_normalized_molecule_ID": len({x["规范化molecule_ID"] for x in final_audit_rows}), "ad_match_basis_counts": dict(ad_match_basis), "gene_symbol_consistency_counts": dict(gene_consistency), "unmatched_or_unmapped_source_rows": len(rejected), "deduplication_key": "(normalized molecule_ID, normalized UniProt primary accession); retain highest Swiss probability; tie -> earliest source row", "uniprot_normalization": "extract valid accession token(s), strip isoform suffix, exact match against existing official-UniProt-verified AD primary accession first; Gene Symbol unique fallback only if Swiss accession is missing/unparseable"},
        "outputs": {"delivery_csv": str(DELIVERY), "edge_audit_csv": str(EDGE_AUDIT), "unmatched_csv": str(UNMATCHED)},
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
