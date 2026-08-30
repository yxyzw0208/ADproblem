"""逐靶点绘制“中药—小分子—靶点（AD交集）”网络图。

仅接受本轮经主控确认的关系表；不会读取任何历史图谱数据。每个靶点占 PDF
的一页。一个小分子若属于同一靶点下的多味中药，会在各中药扇区中分别显示为
视觉副本，以保持“中药分组”可读；统计中的小分子数仍按去重名称计算。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import textwrap
from collections import defaultdict
from colorsys import hls_to_rgb
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
MPL_CONFIG_DIR = SCRIPT_DIR / ".matplotlib"
MPL_CONFIG_DIR.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG_DIR))

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch


# 主控输出的中文列名优先；可通过命令行显式指定覆盖自动识别。
COLUMN_ALIASES = {
    "herb": ["中药名称", "中药中文名", "中药", "Herb", "herb"],
    "molecule": ["中药小分子", "中药分子", "小分子", "分子", "TCMSP分子", "Molecule", "molecule"],
    "target": [
        "Gene Symbol",
        "Swiss预测靶点Gene Symbol",
        "Swiss平台预测靶点Gene Symbol",
        "预测靶点Gene Symbol",
        "靶点标准基因符号",
        "靶点名称",
        "Target",
        "target",
    ],
    "accession": [
        "Swiss预测靶点UniProt编号",
        "Swiss平台预测靶点UniProt编号",
        "预测靶点UniProt编号",
        "UniProt编号",
        "uniprot编号",
        "UniProtKB主编号",
        "UniProt",
        "uniprot",
    ],
    "probability": [
        "Swiss预测概率",
        "Swiss预测靶点预测概率",
        "SwissTargetPrediction预测概率",
        "预测概率",
        "Prediction probability",
        "Probability",
        "probability",
    ],
}

BG = "#EEF4FB"
TARGET_COLOR = "#74B47D"
TARGET_EDGE = "#497A53"
TEXT = "#203040"
MUTED = "#5F7284"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configure_matplotlib() -> str:
    """Configure an embeddable Chinese font and return its name."""
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    font_path = next((path for path in candidates if path.exists()), None)
    if font_path is None:
        raise FileNotFoundError("未找到可嵌入的中文字体（需要 Microsoft YaHei 或 SimHei）")
    font_manager.fontManager.addfont(str(font_path))
    font_name = font_manager.FontProperties(fname=str(font_path)).get_name()
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_name, "DejaVu Sans"],
            "font.size": 7,
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "figure.facecolor": BG,
            "savefig.facecolor": BG,
        }
    )
    return font_name


def clean(value: object) -> str:
    return str(value or "").strip()


def resolve_column(fieldnames: Iterable[str], key: str, explicit: str | None) -> str:
    names = list(fieldnames)
    if explicit:
        if explicit not in names:
            raise ValueError(f"指定列不存在：{key}={explicit!r}；实际列为 {names}")
        return explicit
    for candidate in COLUMN_ALIASES[key]:
        if candidate in names:
            return candidate
    raise ValueError(
        f"无法识别 {key} 列。请使用 --{key}-column 指定；实际列为 {names}"
    )


def parse_probability(value: object) -> float:
    """Return a sortable Swiss probability; missing/unparseable values sort last."""
    text = clean(value)
    if not text:
        return -1.0
    try:
        if text.endswith("%"):
            return float(text[:-1].strip()) / 100.0
        number = float(text)
        return number if math.isfinite(number) else -1.0
    except ValueError:
        return -1.0


def stream_relations_to_database(
    source: Path,
    connection: sqlite3.Connection,
    herb_column: str | None,
    molecule_column: str | None,
    target_column: str | None,
    accession_column: str | None,
    probability_column: str | None,
) -> dict[str, int | str]:
    """Stream only plotting fields into a temporary on-disk index (no raw_rows list)."""
    if source.suffix.lower() != ".csv":
        raise ValueError("当前数据接口只接受主控导出的 UTF-8 CSV 文件")
    connection.executescript(
        """
        CREATE TABLE triples (
            target_accession TEXT NOT NULL,
            herb TEXT NOT NULL,
            molecule TEXT NOT NULL,
            probability REAL NOT NULL,
            PRIMARY KEY (target_accession, herb, molecule)
        );
        CREATE TABLE target_symbols (
            target_accession TEXT NOT NULL,
            gene_symbol TEXT NOT NULL,
            PRIMARY KEY (target_accession, gene_symbol)
        );
        """
    )
    source_rows = 0
    incomplete_rows = 0
    invalid_probability_rows = 0
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV 缺少表头")
        mapping = {
            "herb": resolve_column(reader.fieldnames, "herb", herb_column),
            "molecule": resolve_column(reader.fieldnames, "molecule", molecule_column),
            "target": resolve_column(reader.fieldnames, "target", target_column),
            "accession": resolve_column(reader.fieldnames, "accession", accession_column),
            "probability": resolve_column(reader.fieldnames, "probability", probability_column),
        }
        for row in reader:
            source_rows += 1
            herb = clean(row.get(mapping["herb"]))
            molecule = clean(row.get(mapping["molecule"]))
            symbol = clean(row.get(mapping["target"])).upper()
            accession = clean(row.get(mapping["accession"])).upper()
            probability_text = clean(row.get(mapping["probability"]))
            probability = parse_probability(probability_text)
            if not herb or not molecule or not symbol or not accession:
                incomplete_rows += 1
                continue
            if probability < 0:
                invalid_probability_rows += 1
            connection.execute(
                """
                INSERT INTO triples (target_accession, herb, molecule, probability)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(target_accession, herb, molecule) DO UPDATE SET
                    probability = MAX(triples.probability, excluded.probability)
                """,
                (accession, herb, molecule, probability),
            )
            connection.execute(
                "INSERT OR IGNORE INTO target_symbols (target_accession, gene_symbol) VALUES (?, ?)",
                (accession, symbol),
            )
    connection.commit()
    unique_relations = int(connection.execute("SELECT COUNT(*) FROM triples").fetchone()[0])
    if not unique_relations:
        raise ValueError("未得到有效的 中药—小分子—靶点 关系；请检查数据列与空值")
    return {
        "source_rows": source_rows,
        "valid_relation_rows_after_deduplication": unique_relations,
        "duplicate_or_incomplete_rows_removed": source_rows - unique_relations,
        "incomplete_rows_removed": incomplete_rows,
        "invalid_probability_rows_sorted_last": invalid_probability_rows,
        **{f"column_{key}": value for key, value in mapping.items()},
    }


def query_target_pages(connection: sqlite3.Connection) -> list[dict[str, object]]:
    """Select Top 6 herbs by relation degree and Top 8 molecules by Swiss probability."""
    accessions = [row[0] for row in connection.execute("SELECT DISTINCT target_accession FROM triples ORDER BY target_accession")]
    pages: list[dict[str, object]] = []
    for accession in accessions:
        symbols = [
            row[0]
            for row in connection.execute(
                "SELECT gene_symbol FROM target_symbols WHERE target_accession = ? ORDER BY gene_symbol", (accession,)
            )
        ]
        full_relation_count, full_herb_count, full_molecule_count = connection.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT herb), COUNT(DISTINCT molecule)
            FROM triples WHERE target_accession = ?
            """,
            (accession,),
        ).fetchone()
        top_herbs = [
            row[0]
            for row in connection.execute(
                """
                SELECT herb FROM triples WHERE target_accession = ?
                GROUP BY herb ORDER BY COUNT(*) DESC, herb ASC LIMIT 6
                """,
                (accession,),
            )
        ]
        displayed_relations: list[dict[str, object]] = []
        for herb in top_herbs:
            for molecule, probability in connection.execute(
                """
                SELECT molecule, probability FROM triples
                WHERE target_accession = ? AND herb = ?
                ORDER BY probability DESC, molecule ASC LIMIT 8
                """,
                (accession, herb),
            ):
                displayed_relations.append({"herb": herb, "molecule": molecule, "probability": probability})
        pages.append(
            {
                "accession": accession,
                "symbols": symbols,
                "displayed_relations": displayed_relations,
                "full_relations": int(full_relation_count),
                "full_herbs": int(full_herb_count),
                "full_unique_molecules": int(full_molecule_count),
            }
        )
    return pages


def group_color(index: int, total: int) -> tuple[float, float, float]:
    """Deterministic, separated group palette (HLS -> RGB)."""
    hue = (0.02 + index / max(total, 1) * 0.96) % 1.0
    return hls_to_rgb(hue, 0.57, 0.63)


def wrap_label(label: str, width: int) -> str:
    label = re.sub(r"\s+", " ", label).strip()
    # 文本中没有空格的中药名亦可换行；英文优先在空格、连字符处换行。
    if len(label) <= width:
        return label
    return "\n".join(
        textwrap.wrap(label, width=width, break_long_words=True, break_on_hyphens=True)
    )


def add_edge(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[float, float, float],
    width: float,
    alpha: float,
    shrink_a: float,
    shrink_b: float,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=6.2,
            linewidth=width,
            color=color,
            alpha=alpha,
            shrinkA=shrink_a,
            shrinkB=shrink_b,
            connectionstyle="arc3,rad=0.0",
            zorder=1,
        )
    )


def page_geometry(group_count: int) -> tuple[float, float, float]:
    """Fixed, readable single-page geometry for the declared Top 6 × Top 8 view."""
    outer_radius = 5.15 + 0.21 * min(group_count, 6)
    return outer_radius, 16.5, 11.6


def draw_target_page(
    pdf: PdfPages,
    accession: str,
    symbols: list[str],
    relations: list[dict[str, object]],
    full_relations: int,
    full_herbs: int,
    full_unique_molecules: int,
    page_index: int,
    page_total: int,
    qa_preview_dir: Path | None,
) -> dict[str, int | str]:
    by_herb: dict[str, list[str]] = defaultdict(list)
    for row in relations:
        by_herb[row["herb"]].append(row["molecule"])
    herbs = sorted(by_herb, key=lambda value: value.casefold())
    for herb in herbs:
        by_herb[herb] = sorted(set(by_herb[herb]), key=lambda value: value.casefold())

    relation_count = sum(len(values) for values in by_herb.values())
    unique_molecule_count = len({molecule for values in by_herb.values() for molecule in values})
    outer_radius, fig_width, fig_height = page_geometry(len(herbs))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), constrained_layout=False)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_aspect("equal")
    ax.axis("off")
    margin = 1.35
    ax.set_xlim(-outer_radius - margin, outer_radius + margin)
    ax.set_ylim(-outer_radius - margin - 0.45, outer_radius + margin + 0.75)

    # 每个扇区是“中药 + 其所有小分子”的可读单元；同一小分子的多次出现为视觉副本。
    herb_positions: dict[str, tuple[float, float]] = {}
    molecule_items: list[tuple[str, str, tuple[float, float], tuple[float, float, float]]] = []
    target_pos = (0.0, 0.0)
    for index, herb in enumerate(herbs):
        theta = math.pi / 2 + 2 * math.pi * index / len(herbs)
        color = group_color(index, len(herbs))
        herb_pos = (outer_radius * math.cos(theta), outer_radius * math.sin(theta))
        herb_positions[herb] = herb_pos
        molecules = by_herb[herb]
        sector_width = 2 * math.pi / max(len(herbs), 1)
        fan_span = min(sector_width * 0.80, 1.18)
        inner_radius = outer_radius * 0.52
        for molecule_index, molecule in enumerate(molecules):
            slot_count = min(len(molecules), 4)
            slot_index = molecule_index % 4
            if len(molecules) == 1:
                molecule_theta = theta
            else:
                molecule_theta = theta - fan_span / 2 + fan_span * slot_index / max(slot_count - 1, 1)
            # 最多8个分子在两层扇面中排列，避免各组互相挤压。
            radial_offset = (molecule_index // 4) * 0.92
            molecule_radius = inner_radius + radial_offset
            molecule_pos = (
                molecule_radius * math.cos(molecule_theta),
                molecule_radius * math.sin(molecule_theta),
            )
            molecule_items.append((herb, molecule, molecule_pos, color))

    # 边在节点之前绘制，保证标签与节点可见。
    for herb, _molecule, molecule_pos, color in molecule_items:
        add_edge(ax, herb_positions[herb], molecule_pos, color, 0.86, 0.48, 12, 11)
        add_edge(ax, molecule_pos, target_pos, color, 1.02, 0.60, 11, 27)

    # 中药：外圈六边形；小分子：内圈圆形。同一味中药中的所有节点使用同一色相。
    for index, herb in enumerate(herbs):
        color = group_color(index, len(herbs))
        x, y = herb_positions[herb]
        ax.scatter([x], [y], s=880, marker="h", c=[color], edgecolors="white", linewidths=1.2, zorder=4)
        ax.text(
            x, y, wrap_label(herb, 7), ha="center", va="center", fontsize=6.4,
            color="#26313A", fontweight="bold", linespacing=0.94, zorder=6,
        )

    molecule_font = 5.6 if relation_count <= 36 else 5.4
    for _herb, molecule, (x, y), color in molecule_items:
        ax.scatter([x], [y], s=620, marker="o", c=[color], edgecolors="white", linewidths=1.05, zorder=4)
        # 标签贴近圆而非写入圆心，兼顾长英文分子名与节点形状的识别。
        direction = math.atan2(y, x)
        label_distance = 0.32
        ax.text(
            x + label_distance * math.cos(direction),
            y + label_distance * math.sin(direction),
            wrap_label(molecule, 15), ha="center", va="center", fontsize=molecule_font,
            color=TEXT, linespacing=0.93,
            bbox={"boxstyle": "round,pad=0.08", "facecolor": "white", "edgecolor": "none", "alpha": 0.83},
            zorder=6,
        )

    target_label = " / ".join(symbols) if symbols else "Gene Symbol 未提供"
    target_size = 3200
    ax.scatter([0], [0], s=target_size, marker="v", c=[TARGET_COLOR], edgecolors="white", linewidths=1.8, zorder=5)
    ax.text(0, 0.12, wrap_label(target_label, 16), ha="center", va="center", fontsize=9.4, color="white", fontweight="bold", zorder=7)
    ax.text(
        0, -0.64, accession, ha="center", va="center", fontsize=6.1, color=TARGET_EDGE,
        fontweight="bold", bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "#C8DEC9", "alpha": 0.96}, zorder=7,
    )

    fig.text(0.5, 0.972, f"中药—小分子—靶点网络｜{target_label}", ha="center", va="top", fontsize=14, fontweight="bold", color=TEXT)
    fig.text(
        0.5, 0.942,
        f"SwissTargetPrediction 与 AD 靶点交集；UniProt：{accession}；展示{len(herbs)}味中药 / {unique_molecule_count}个去重小分子 / {relation_count}条关系（全量：{full_herbs}味 / {full_unique_molecules}个 / {full_relations}条）",
        ha="center", va="top", fontsize=6.8, color=MUTED,
    )
    handles = [
        Line2D([0], [0], marker="h", color="none", markerfacecolor="#9A9A9A", markeredgecolor="white", markersize=8, label="中药（颜色表示中药分组）"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#9A9A9A", markeredgecolor="white", markersize=7, label="中药小分子（同组配色）"),
        Line2D([0], [0], marker="v", color="none", markerfacecolor=TARGET_COLOR, markeredgecolor="white", markersize=9, label="AD交集靶点（UniProt）"),
    ]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.055), ncol=3, frameon=False, fontsize=6.2, handletextpad=0.5, columnspacing=1.2)
    fig.text(
        0.5, 0.018,
        "注：可视化展示Top 6/8，完整关系见任务二表；同一分子跨中药时按组重复显示为视觉副本，连边不表示效应强弱或因果性。",
        ha="center", va="bottom", fontsize=5.7, color=MUTED,
    )
    fig.text(0.985, 0.018, f"{page_index}/{page_total}", ha="right", va="bottom", fontsize=5.7, color=MUTED)
    pdf.savefig(fig, facecolor=BG)
    # 仅在内部视觉 QA 时导出逐页预览；正式交付仍只有合并 PDF。
    if qa_preview_dir is not None:
        safe_target = re.sub(r"[^A-Za-z0-9_.-]+", "_", accession)
        qa_preview_dir.mkdir(parents=True, exist_ok=True)
        prefix = qa_preview_dir / f"{page_index:03d}_{safe_target}"
        fig.savefig(f"{prefix}.svg", bbox_inches="tight", facecolor=BG)
        fig.savefig(f"{prefix}.pdf", bbox_inches="tight", facecolor=BG)
        fig.savefig(f"{prefix}.png", dpi=600, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return {
        "herbs": len(herbs),
        "unique_molecules": unique_molecule_count,
        "visual_molecule_copies": relation_count,
        "displayed_relations": relation_count,
        "full_relations": full_relations,
        "full_herbs": full_herbs,
        "full_unique_molecules": full_unique_molecules,
        "display_rule": "Top 6 herbs by unique relation degree; Top 8 molecules per displayed herb by Swiss probability",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="基于本轮主控 CSV 输出逐靶点中药—分子—靶点网络 PDF")
    parser.add_argument("input_csv", type=Path, help="本轮任务二的最终关系 CSV（仅纳入 Swiss∩AD 靶点）")
    parser.add_argument("output_pdf", type=Path, help="输出 PDF 路径")
    parser.add_argument("--herb-column", help="中药列名；缺省时自动识别")
    parser.add_argument("--molecule-column", help="小分子列名；缺省时自动识别")
    parser.add_argument("--target-column", help="最终 AD 交集 Gene Symbol 列名；缺省时自动识别")
    parser.add_argument("--accession-column", help="最终靶点 UniProt 列名；缺省时自动识别")
    parser.add_argument("--probability-column", help="Swiss 预测概率列名；缺省时自动识别")
    parser.add_argument("--manifest", type=Path, help="可选：写入内部 QA/可复现性 JSON（不作为用户交付物）")
    parser.add_argument("--qa-preview-dir", type=Path, help="可选：内部 QA 的逐页 SVG/PDF/600 dpi PNG 预览目录")
    args = parser.parse_args()

    if not args.input_csv.exists():
        raise FileNotFoundError(f"输入文件不存在：{args.input_csv}")
    font_name = configure_matplotlib()
    args.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    # 使用子任务目录中的短生命周期索引，避免受控 Windows 临时目录的 ACL 限制。
    database_path = SCRIPT_DIR / "网络图_流式临时索引.sqlite"
    if database_path.exists():
        raise FileExistsError(f"检测到未清理的内部临时索引：{database_path}")
    connection = sqlite3.connect(database_path)
    try:
        stats = stream_relations_to_database(
            args.input_csv,
            connection,
            args.herb_column,
            args.molecule_column,
            args.target_column,
            args.accession_column,
            args.probability_column,
        )
        pages = query_target_pages(connection)
    finally:
        connection.close()
        database_path.unlink(missing_ok=True)
    page_stats: dict[str, dict[str, int | str]] = {}
    with PdfPages(args.output_pdf, metadata={"Title": "中药—小分子—靶点网络", "Author": "Python/matplotlib"}) as pdf:
        for page_index, page in enumerate(pages, start=1):
            accession = str(page["accession"])
            page_stats[accession] = draw_target_page(
                pdf,
                accession,
                list(page["symbols"]),
                list(page["displayed_relations"]),
                int(page["full_relations"]),
                int(page["full_herbs"]),
                int(page["full_unique_molecules"]),
                page_index,
                len(pages),
                args.qa_preview_dir,
            )
    if args.manifest:
        payload = {
            "backend": "Python/matplotlib",
            "font": font_name,
            "input": {"path": str(args.input_csv), "sha256": sha256(args.input_csv)},
            "output": {"path": str(args.output_pdf), "sha256": sha256(args.output_pdf)},
            "data_mapping_and_counts": stats,
            "pages": len(pages),
            "per_target": page_stats,
            "scope": "Only relationships supplied by the current input CSV are indexed; no historical dataset is loaded. Each page uses UniProt accession as the grouping key and displays Top 6 herbs by relation degree and Top 8 molecules per herb by Swiss probability. Full relation counts and displayed relation counts are recorded per target.",
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PDF: {args.output_pdf}")
    print(f"Targets/pages: {len(pages)}")
    print(f"Relations after de-duplication: {stats['valid_relation_rows_after_deduplication']}")


if __name__ == "__main__":
    main()
