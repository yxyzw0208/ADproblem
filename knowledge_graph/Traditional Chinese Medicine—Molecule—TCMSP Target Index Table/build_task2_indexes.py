from __future__ import annotations

import html
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
from lxml import etree


ROOT = Path(r"D:\codex\大创")
OUT = Path(__file__).resolve().parent

# Do not use the 2026-08-14 Swiss output as the source of this run's
# predictions.  That release is used only to validate the matching contract.
SWISS_NEW = ROOT / "小分子-靶点（swiss预测靶点）.xlsx"
FULL_WORKBOOK = ROOT / "AD_中药_小分子_作用靶点_全量表.xlsx"
TCMSP_UNIPROT_DICTIONARY = (
    ROOT / "中药小分子靶点_UniProt标准化结果_20260810" / "中药小分子靶点_UniProt标准化.csv"
)
AD_UNIPROT = (
    ROOT
    / "AD基因靶点及命名标准化"
    / "04_UniProt靶点标准化"
    / "采用uniprot去除靶点数据集（3699条数据记录）（数据集优先使用）.csv"
)


def clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(html.unescape(str(value)).replace("\xa0", " ").split())


def mol_id(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    # Spreadsheet readers sometimes convert identifier 6 to 6.0.
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def accession(value: object) -> str:
    return clean(value).upper()


def write_csv(frame: pd.DataFrame, name: str) -> None:
    frame.to_csv(OUT / name, index=False, encoding="utf-8-sig")


def read_current_swiss_sheet(path: Path, sheet_xml: str) -> pd.DataFrame:
    """Stream the large current xlsx detail sheet without workbook-wide scans.

    The source workbook has no reliable worksheet dimension metadata. Pandas and
    openpyxl can therefore enumerate the full worksheet range. Parsing the known
    requested worksheet directly gives the same cell values while stopping at
    the XML end-of-sheet marker.
    """
    with zipfile.ZipFile(path) as book:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in book.namelist():
            with book.open("xl/sharedStrings.xml") as stream:
                for _, element in etree.iterparse(stream, events=("end",), tag="{*}si"):
                    shared.append("".join(element.itertext()))
                    element.clear()
        headers: list[str] | None = None
        records: list[list[str]] = []
        with book.open(sheet_xml) as stream:
            for _, row in etree.iterparse(stream, events=("end",), tag="{*}row"):
                values: dict[int, str] = {}
                for cell in row.findall("{*}c"):
                    ref = cell.get("r", "A1")
                    match = re.match(r"([A-Z]+)", ref)
                    if not match:
                        continue
                    col = 0
                    for char in match.group(1):
                        col = col * 26 + (ord(char) - 64)
                    cell_type = cell.get("t", "")
                    value_node = cell.find("{*}v")
                    value = value_node.text if value_node is not None and value_node.text else ""
                    if cell_type == "s" and value.isdigit():
                        value = shared[int(value)]
                    elif cell_type == "inlineStr":
                        value = "".join(cell.itertext())
                    values[col] = value
                if values:
                    row_values = [values.get(i, "") for i in range(1, max(values) + 1)]
                    if headers is None:
                        headers = row_values
                    else:
                        records.append(row_values + [""] * (len(headers) - len(row_values)))
                row.clear()
        if not headers:
            raise ValueError(f"未从本轮 Swiss 工作簿的 {sheet_xml} 读取到表头")
    return pd.DataFrame(records, columns=headers)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # The full workbook—not the historic 7,339-row strict subset—defines the
    # herb--molecule and TCMSP target edges for this task.
    herb_source = pd.read_excel(FULL_WORKBOOK, sheet_name="中药-小分子汇总", dtype=str)
    target_source = pd.read_excel(FULL_WORKBOOK, sheet_name="全量_中药小分子靶点", dtype=str)
    molecule_index = pd.read_excel(FULL_WORKBOOK, sheet_name="小分子汇总排名", dtype=str)
    # The summary sheet is deliberately used here: task 2 needs source mapping
    # coverage, while task 1 owns the current detail-level Swiss--AD intersection.
    swiss_summary = read_current_swiss_sheet(SWISS_NEW, "xl/worksheets/sheet2.xml")
    uniprot_dictionary = pd.read_csv(TCMSP_UNIPROT_DICTIONARY, encoding="utf-8-sig", low_memory=False)
    ad = pd.read_csv(AD_UNIPROT, encoding="utf-8-sig", low_memory=False)

    # Canonicalize source keys, preserving original display fields and values.
    for frame in (herb_source, target_source, molecule_index):
        frame["TCMSP MOL_ID"] = frame["TCMSP MOL_ID"].map(clean).str.upper()
        frame["molecule_ID"] = frame["molecule_ID"].map(mol_id)
        for col in ["中药中文名", "中药小分子"]:
            if col in frame:
                frame[col] = frame[col].map(clean)
    for col in ["作用靶点基因", "TCMSP靶点名称"]:
        target_source[col] = target_source[col].map(clean)
    target_source["作用靶点基因"] = target_source["作用靶点基因"].str.upper()

    swiss_summary["原始行号（去重映射）"] = swiss_summary["原始行号（去重映射）"].map(clean)
    swiss_summary["molecule_ID"] = swiss_summary["molecule_ID"].map(mol_id)
    for col in ["SMILES", "STP查询编号", "Top1靶点", "Top1 Gene Symbol", "结果URL"]:
        swiss_summary[col] = swiss_summary[col].map(clean)
    swiss_summary["Top1 Gene Symbol"] = swiss_summary["Top1 Gene Symbol"].str.upper()
    swiss_summary["Top1概率"] = pd.to_numeric(swiss_summary["Top1概率"], errors="coerce")

    uniprot_dictionary["作用靶点基因"] = uniprot_dictionary["作用靶点基因"].map(clean).str.upper()
    uniprot_dictionary["UniProtKB主编号"] = uniprot_dictionary["UniProtKB主编号"].map(accession)
    uniprot_dictionary["UniProt标准基因符号"] = uniprot_dictionary["UniProt标准基因符号"].map(clean).str.upper()

    ad["uniprotkb_primary_accession"] = ad["uniprotkb_primary_accession"].map(accession)
    for col in ["hgnc_symbol", "representative_evidence_sentence", "pmid", "pubmed_url"]:
        ad[col] = ad[col].map(clean)
    ad["hgnc_symbol"] = ad["hgnc_symbol"].str.upper()

    # One herb--molecule edge. molecule_ID is the current Swiss linkage key;
    # MOL_ID and SMILES remain audit fields and are never inferred.
    herb_mol_cols = [
        "中药中文名", "中药拼音", "中药拉丁名", "中药分类（中文）", "中药小分子",
        "TCMSP MOL_ID", "molecule_ID", "小分子全量排名", "小分子严格排名",
    ]
    herb_mol = herb_source[herb_mol_cols].drop_duplicates().sort_values(
        ["molecule_ID", "中药中文名", "TCMSP MOL_ID"], kind="stable"
    ).reset_index(drop=True)
    write_csv(herb_mol, "01_tcm_molecule_dedup_long_table.csv")

    # One herb--molecule--TCMSP-target edge with the pre-existing reviewed
    # UniProt accession. Rows lacking it are retained only in a separate QC file.
    tc_cols = herb_mol_cols + [
        "作用靶点基因", "TCMSP靶点名称", "target_ID", "DrugBank内部ID", "SVM_score", "RF_score", "边平均分",
    ]
    tc_long = target_source[tc_cols].rename(columns={
        "作用靶点基因": "TCMSP靶点Gene Symbol",
    })
    gene_dictionary = uniprot_dictionary[["作用靶点基因", "UniProt标准基因符号", "UniProtKB主编号"]].drop_duplicates(
        "作用靶点基因"
    ).rename(columns={
        "作用靶点基因": "TCMSP靶点Gene Symbol",
        "UniProt标准基因符号": "TCMSP靶点UniProt标准Gene Symbol",
        "UniProtKB主编号": "TCMSP靶点UniProt编号",
    })
    tc_long = tc_long.merge(gene_dictionary, on="TCMSP靶点Gene Symbol", how="left", validate="many_to_one")
    for col in ["TCMSP靶点UniProt标准Gene Symbol", "TCMSP靶点UniProt编号"]:
        tc_long[col] = tc_long[col].fillna("")
    tc_long = tc_long.drop_duplicates(
        ["中药中文名", "TCMSP MOL_ID", "TCMSP靶点Gene Symbol", "TCMSP靶点UniProt编号"]
    ).sort_values(
        ["molecule_ID", "中药中文名", "TCMSP靶点Gene Symbol", "TCMSP靶点UniProt编号"], kind="stable"
    ).reset_index(drop=True)
    write_csv(tc_long, "02_tcm_molecule_tcmsp_targets_uniprot_dedup_long_table.csv")
    write_csv(
        tc_long[tc_long["TCMSP靶点UniProt编号"].eq("")].copy(),
        "02a_tcmsp_targets_missing_uniprot_to_exclude.csv",
    )

    # One source-preserved AD evidence record per canonical UniProt accession.
    # The official normalized directory is the first-choice evidence source.
    evidence = ad[[
        "uniprotkb_primary_accession", "hgnc_symbol", "representative_evidence_sentence", "pmid", "pubmed_url",
        "uniprotkb_url", "accession_verification", "reviewed_status",
    ]].rename(columns={
        "uniprotkb_primary_accession": "AD靶点UniProt编号",
        "hgnc_symbol": "AD标准Gene Symbol",
        "representative_evidence_sentence": "AD相关证明句（英文原文）",
        "pmid": "PMID",
        "pubmed_url": "PubMed链接",
        "uniprotkb_url": "UniProt链接",
        "accession_verification": "UniProt验证方式",
        "reviewed_status": "UniProt审核状态",
    })
    evidence["AD证据来源"] = "AD基因靶点及命名标准化/04_UniProt靶点标准化/3699条数据集"
    evidence = evidence.drop_duplicates(["AD靶点UniProt编号"]).sort_values("AD靶点UniProt编号", kind="stable")
    write_csv(evidence, "03_ad_evidence_uniprot_index.csv")

    # New Swiss summary records only. They are joined strictly by molecule_ID.
    # No fallback to SMILES is permitted: full source sheets do not expose a
    # canonical SMILES column, and it would create collision-driven mappings.
    swiss_keys = swiss_summary[["原始行号（去重映射）", "molecule_ID", "SMILES", "STP查询编号", "预测状态", "去重预测靶点数"]].drop_duplicates()
    source_by_mol = herb_mol.groupby("molecule_ID", dropna=False).agg(
        中药数=("中药中文名", "nunique"),
        TCMSP_MOL_ID数=("TCMSP MOL_ID", "nunique"),
        分子名称数=("中药小分子", "nunique"),
    ).reset_index()
    audit = swiss_keys.merge(source_by_mol, on="molecule_ID", how="left", validate="many_to_one")
    audit["molecule_ID连接状态"] = audit["中药数"].notna().map({True: "molecule_ID精确匹配", False: "未匹配"})
    audit["SMILES审计"] = "全量源表未提供可核验SMILES；仅保留Swiss原始SMILES供原始行号审计"
    audit = audit.sort_values(["molecule_ID", "原始行号（去重映射）"], kind="stable")
    write_csv(audit, "04_swiss_molecules_tcm_source_join_audit.csv")

    # Task 1 will provide the filtered Swiss target rows. This one-row-per-Swiss
    # molecule mapping avoids materializing a false 400k-row × herb cross-product.
    swiss_molecule_lookup = swiss_summary.merge(
        molecule_index[["molecule_ID", "TCMSP MOL_ID", "中药小分子", "小分子全量排名", "小分子严格排名"]].drop_duplicates(),
        on="molecule_ID", how="left", validate="many_to_many",
    ).rename(columns={"Top1靶点": "Swiss Top1靶点名称", "Top1 Gene Symbol": "Swiss Top1 Gene Symbol", "Top1概率": "Swiss Top1概率", "结果URL": "Swiss查询网站"})
    swiss_molecule_lookup["molecule_ID连接状态"] = swiss_molecule_lookup["TCMSP MOL_ID"].notna().map({True: "molecule_ID精确匹配", False: "未匹配"})
    write_csv(swiss_molecule_lookup.sort_values(["molecule_ID", "TCMSP MOL_ID"], kind="stable"), "05_swiss_molecule_index_pending_ad_intersection_join.csv")

    summary = {
        "source_files": {
            "current_swiss": str(SWISS_NEW),
            "full_tcmsp_workbook": str(FULL_WORKBOOK),
            "tcmsp_uniprot_dictionary_13_targets": str(TCMSP_UNIPROT_DICTIONARY),
            "ad_uniprot_evidence": str(AD_UNIPROT),
        },
        "join_contract": {
            "primary_key": "规范化 molecule_ID（去除空白及纯数字 .0 尾缀）",
            "smiles_rule": "全量源表没有SMILES；仅保留Swiss原始SMILES和原始行号审计，不作为连接键",
            "raw_row_rule": "原始行号仅用于审计；不以其推断中药来源",
            "target_ad_filter": "由任务1提供本轮 Swiss-UniProt 与 AD-UniProt 交集后，以 Swiss UniProt ID 精确内连接",
        },
        "deduplication": {
            "herb_molecule": ["中药中文名", "TCMSP MOL_ID"],
            "tcmsp_target": ["中药中文名", "TCMSP MOL_ID", "TCMSP靶点Gene Symbol", "TCMSP靶点UniProt编号"],
            "ad_evidence": ["AD靶点UniProt编号"],
            "swiss_molecule_summary": ["原始行号（去重映射）", "molecule_ID", "STP查询编号"],
        },
        "counts": {
            "new_swiss_summary_rows": int(len(swiss_summary)),
            "new_swiss_unique_molecule_ids": int(swiss_summary["molecule_ID"].nunique()),
            "herb_molecule_edges": int(len(herb_mol)),
            "herb_count": int(herb_mol["中药中文名"].nunique()),
            "molecule_count": int(herb_mol["molecule_ID"].nunique()),
            "tcmsp_target_edges": int(len(tc_long)),
            "tcmsp_target_missing_uniprot": int(tc_long["TCMSP靶点UniProt编号"].eq("").sum()),
            "ad_evidence_uniprot_count": int(len(evidence)),
            "swiss_molecule_keys_matched": int(audit["molecule_ID连接状态"].eq("molecule_ID精确匹配").sum()),
            "swiss_molecule_keys_unmatched": int(audit["molecule_ID连接状态"].eq("未匹配").sum()),
            "swiss_smiles_not_joined": int(len(audit)),
            "swiss_molecule_lookup_rows": int(len(swiss_molecule_lookup)),
        },
        "missing_items": {
            "current_swiss_summary_missing_top1_gene_symbol": int(swiss_summary["Top1 Gene Symbol"].eq("").sum()),
            "current_swiss_summary_missing_top1_probability": int(swiss_summary["Top1概率"].isna().sum()),
            "ad_evidence_missing_sentence": int(evidence["AD相关证明句（英文原文）"].eq("").sum()),
            "ad_evidence_missing_pmid": int(evidence["PMID"].eq("").sum()),
        },
    }
    (OUT / "06_source_join_key_dedup_rules_missing.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
