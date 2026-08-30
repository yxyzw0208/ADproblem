# 逐靶点网络图：数据接口与执行约定

## 目标与版式

每个最终靶点输出 PDF 的单独一页：绿色倒三角为靶点，外圈六边形为中药，内圈圆形为该中药所含的小分子。一个中药分组使用同一种颜色；中药—分子、分子—靶点两类边也采用该组颜色。页面固定展示关联度前 6 味中药；每味中药展示 Swiss 预测概率最高的 8 个分子，以保持 4–6 个中药簇的可读结构。

同一小分子若来自多味中药，会在各中药分组中各显示一次。这些节点是同一分子的视觉副本，用于保证“按中药分组”清楚；页首的小分子计数为去重后的数目。页脚固定标注“可视化展示Top 6/8，完整关系见任务二表”。

## 唯一允许的输入

由主控从任务二最终表导出的 UTF-8 CSV，且每一行必须已经是 **SwissTargetPrediction 预测靶点与 AD 靶点的交集**。脚本不会读取旧项目中的表格或图谱数据。

必须存在以下四类信息（可使用相近列名，也可通过命令行显式指定列名）：

| 角色 | 优先自动识别的列名 |
|---|---|
| 中药 | `中药名称`、`中药中文名` |
| 小分子 | `中药小分子`、`中药分子` |
| 最终靶点（显示） | `Gene Symbol`、`Swiss预测靶点Gene Symbol` |
| UniProt（分页主键） | `Swiss预测靶点UniProt编号`、`UniProt编号` |
| Swiss 预测概率（排序） | `Swiss预测概率`、`预测概率` |

每一条有效关系为 `中药—中药小分子—UniProt accession`，Gene Symbol 仅用于显示。完全相同的三元关系会自动去重并保留最高 Swiss 预测概率；中药、小分子、Gene Symbol 或 UniProt 任一项为空的行不绘制，并会记录在可选 manifest 的计数中。CSV 会流式写入临时 SQLite 索引，不会将百万行原始记录同时保存在内存中。

## 主控调用模板

```powershell
& 'D:\codex\大创\12靶点知识图谱准备\知识图谱示例_BACE1_ECE1\.venv\Scripts\python.exe' `
  'D:\codex\大创\本轮任务_20260818\子任务3\draw_per_target_tcm_molecule_network.py' `
  '主控提供的最终关系表.csv' `
  'D:\codex\大创\本轮任务_20260818\中药_分子_靶点逐靶点网络图.pdf' `
  --manifest 'D:\codex\大创\本轮任务_20260818\子任务3\网络图_QA_manifest.json'
```

若列名不符合自动识别规则，追加：

```powershell
--herb-column '中药名称' --molecule-column '中药分子' `
--target-column 'Swiss预测靶点Gene Symbol' --accession-column 'Swiss预测靶点UniProt编号' `
--probability-column 'Swiss预测概率'
```

## 最终质检（在收到本轮 CSV 后执行）

1. 校验输入行数、去重后关系数和靶点数，与主控表一致。
2. 运行绘图脚本，确认 PDF 页数等于唯一 UniProt accession 数；核对每页全量关系数、展示关系数（最多 48 条）及 Top 6/8 规则。
3. 静态检查脚本，审计 PDF 的可嵌入文字与最小字号。
4. 将 PDF 所有页面渲染为 PNG，逐页检查中文字体、裁切、标签重叠、边可见性、页码与靶点名称。

PDF 使用嵌入式 TrueType 字体设置（`pdf.fonttype = 42`）；正式交付仅提供 PDF，不提供中间 PNG、CSV 或 manifest。
