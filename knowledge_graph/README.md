# TCM–Small Molecule–Target–AD Knowledge Graph — Intersection & Full Paths, Plotting Code

中药—小分子—靶点—AD 知识图谱：交集与完整路径、绘图代码。

Snapshot of the analysis pipeline and result data for the
"中药—小分子—靶点—AD知识图谱" (TCM–small molecule–target–AD knowledge graph) project.
Original folder: `中药—小分子—靶点—AD知识图谱\进行交集以及完整路径，绘图所需代码`.

All file and folder names were translated from Chinese to English; the original
names are shown in the mapping below.

## Folder roles（各文件夹作用）

| Folder | 作用 (Role) |
|---|---|
| `Master Script and Final Delivery Table/` | **主控脚本与最终交付表**：主控/汇总脚本（`build_final_tables.py` 等）、UniProt 官方名称与补全表、最终交付的大表（含 709 MB 全路径表压缩包）与交付质控。Master control and summary scripts, UniProt official-name enrichment tables, the final delivery tables (incl. the zipped 709 MB full-path table) and delivery QC. |
| `Intersection of Swiss predicted targets and AD targets/` | **子任务1**：SwissTargetPrediction 预测靶点与 AD 靶点求交集，产出规范化去重表、逐边审计、未映射记录与审计摘要。Subtask 1: intersect SwissTargetPrediction predicted targets with AD targets; outputs the dedup table, edge audit, unmatched records and audit summary. |
| `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/` | **子任务2**：构建中药—分子—TCMSP 靶点去重长表、AD 证据 UniProt 索引等连接索引，供任务 1/3 使用。Subtask 2: build TCM—molecule—TCMSP target dedup long tables and the AD-evidence UniProt index used by tasks 1 and 3. |
| `Script for Drawing Targeted Network Diagrams and QA Records/` | **子任务3**：逐靶点绘制“中药—小分子—靶点（AD 交集）”网络图 PDF 的脚本、绘图输入数据，以及 QA manifest 与 QA 报告。Subtask 3: per-target network diagram plotting script, plot input CSV, and the QA manifest/report. |

## Layout (original → English)

| Original folder | English folder |
|---|---|
| 主控 | `Master Script and Final Delivery Table/` |
| 子任务1 | `Intersection of Swiss predicted targets and AD targets/` |
| 子任务2 | `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/` |
| 子任务3 | `Script for Drawing Targeted Network Diagrams and QA Records/` |

Key renamed items:

| Original name | English name |
|---|---|
| 02_中药-分子-靶点-AD完整路径_最终数据.csv (709 MB) | `Master Script and Final Delivery Table/02_tcm_molecule_target_ad_full_paths_final.csv.zip` |
| Swiss_AD交集_逐边审计.csv (112 MB) | `Intersection of Swiss predicted targets and AD targets/swiss_ad_intersection_edge_audit.csv.zip` |
| UniProt官方推荐名称_1035靶点.csv / .json | `Master Script and Final Delivery Table/uniprot_official_names_1035_targets.csv / .json` |
| UniProt官方补全_TCMSP缺失靶点.csv / .json | `Master Script and Final Delivery Table/uniprot_completion_tcmsp_missing_targets.csv / .json` |
| 最终交付质控.json | `Master Script and Final Delivery Table/final_delivery_qc.json` |
| Swiss_AD交集_审计摘要.json | `Intersection of Swiss predicted targets and AD targets/swiss_ad_intersection_audit_summary.json` |
| 01_中药_分子_去重长表.csv | `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/01_tcm_molecule_dedup_long_table.csv` |
| 02_中药_分子_TCMSP靶点_UniProt_去重长表.csv | `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/02_tcm_molecule_tcmsp_targets_uniprot_dedup_long_table.csv` |
| 03_AD证据_UniProt索引.csv | `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/03_ad_evidence_uniprot_index.csv` |
| 04_本轮Swiss分子_中药来源连接审计.csv | `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/04_swiss_molecules_tcm_source_join_audit.csv` |
| 05_本轮Swiss_分子索引_待任务1按AD交集连接.csv | `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/05_swiss_molecule_index_pending_ad_intersection_join.csv` |
| 06_来源_连接键_去重规则_缺失项.json | `Traditional Chinese Medicine—Molecule—TCMSP Target Index Table/06_source_join_key_dedup_rules_missing.json` |
| 仅剩余靶点_绘图输入.csv | `Script for Drawing Targeted Network Diagrams and QA Records/remaining_targets_only_plot_input.csv` |
| 剩余161靶点_网络图_QA_manifest.json | `Script for Drawing Targeted Network Diagrams and QA Records/remaining_161_targets_network_qa_manifest.json` |
| 剩余161靶点_网络图_QA报告.md | `Script for Drawing Targeted Network Diagrams and QA Records/remaining_161_targets_network_qa_report.md` |
| 数据接口说明.md | `Script for Drawing Targeted Network Diagrams and QA Records/data_interface_notes.md` |
| 新旧靶点差集审计.json | `Script for Drawing Targeted Network Diagrams and QA Records/new_old_targets_diff_audit.json` |
| 绘制逐靶点中药_分子_靶点网络.py | `Script for Drawing Targeted Network Diagrams and QA Records/draw_per_target_tcm_molecule_network.py` |

## Large files: zipped or excluded

The two CSVs above 100 MB (GitHub hard limit) are committed as zip archives;
unzip them in place to restore the plain CSV.

| File (original, size) | Status |
|---|---|
| 02_中药-分子-靶点-AD完整路径_最终数据.csv (709 MB) | zipped → 24.7 MB |
| Swiss_AD交集_逐边审计.csv (112 MB) | zipped → 12 MB |
| 01_Swiss预测靶点与AD交集_最终数据.csv (79 MB) | excluded (large) |
| final_join.sqlite (89 MB) | excluded (large) |
| artifact_final/task1_rows.ndjson (82 MB) | excluded (large) |
| Swiss预测靶点_AD共同靶点_规范化去重表.csv (48 MB) | excluded (large) |
| Swiss_AD交集_未映射或未匹配记录.csv (24 MB) | excluded (large) |
| 已停止_全量生成_不交付.pdf (15 MB) | excluded (marked "not delivered") |
| __pycache__ / .matplotlib / QA_页面渲染 | excluded (caches / QA renders) |

To include any excluded file later, copy it from the local original folder and
commit; or switch to Git LFS for files > 100 MB.

## Scripts

- Internal file and folder references inside the Python/MJS scripts were updated
  to the English names above so the snapshot is self-consistent.
- Some scripts still contain machine-specific absolute paths (e.g.
  `D:\codex\大创\...`) for inputs that are not part of this repo; adjust those
  paths if you re-run the pipeline.
- CSV column names inside scripts remain in Chinese on purpose — they are the
  data schema (CSV headers), not file names.
