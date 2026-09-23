# 展示样例：SWI-650-SS 装配作业指导书（虚构）

这份样例复刻了真实工业作业指导书（SWI）翻译时最难的几类问题，用技能端到端做成中文出版级成品。
**文档、品牌（Tethys Downhole Tools）、产品、零件号、人名全部虚构，插图由 `make_figures.py` 程序化绘制。**

成品与对比图在 [`docs/showcase/`](../../docs/showcase/)：

- 原文 [`SWI-650-SS_Assembly_en.pdf`](../../docs/showcase/SWI-650-SS_Assembly_en.pdf)（11 页）
- 译稿 [`SWI-650-SS_Assembly_zh.pdf`](../../docs/showcase/SWI-650-SS_Assembly_zh.pdf)（10 页，全部闸门 PASS）

## 复刻的难点 → 技能的处置

| 难点（原文） | 处置（译稿） | 用到的模块 |
|---|---|---|
| 插图是系统导出的低清位图（85~132 dpi），放大即糊 | Real-ESRGAN x4plus 超分 4 倍，2040 px ≈ 340 dpi 嵌入 | `figpipe extract` + `sr.py` |
| 件号气泡 26 个，数字发虚（08/06、03/05 形近） | 按零件表 01~12、步骤正文、零件颜色逐个判读，原环心位置统一重绘；旧环残留判据归零 | `bubbles.py`（`figpipe apply`） |
| 11 处英文标注烧死在位图里（SECTION A-A、DETAIL B、Subassembly、Side Fill Port…） | 检测定位 → 按框号给译名 → 采样底色铺底、原位写中文，同图字号统一；漏译排查 0 处 | `figpipe detect/apply/sweep`、`tightbox.py` |
| 目录 + 22 条 PDF 书签（含每个工序步骤） | 目录按译版页码自动生成（点引线收敛、整行跳转）；章节 + 步骤书签全部保留 | `("toc",)` / `("mark",)` 块 |
| 页眉色带、PPE 图标栏、警示/说明图标行、多级步骤、零件表与扭矩表 | 语义重排：前置页接排、步骤与其插图不分页、表格用译文重建 | `driver.Job(flow=True)`、`("keep",)` |
| 原文有意埋了两处缺陷：步骤 3.3 误引「Table 3-2」；零件表碟形弹簧数量 6 与步骤「eight」不一致 | 表号勘正并写进附录 A 甲；数量无法确证 → 保留原值加注、写进附录 A 乙待确认 | 内容层 `terms.py` |
| — | 正文后附录 A《译校勘误说明》、附录 B《中英术语对照表》，各自另起一页；PDF 文档属性写入中文标题 | `appendix.py` |

## 复现

```bash
S=../../skills/pdf-translate-zh/scripts
python make_source.py build                                     # 生成英文源文档 build/SWI-650-SS_Assembly.pdf
cd build && python ../$S/translate_pdf.py SWI-650-SS_Assembly.pdf  # 定级（R）+ 提取 + 内容层骨架
W=translated/SWI-650-SS_Assembly
cp ../content/*.py $W/content/                                  # 本目录的内容层（译文、术语、图内标注译名）
python ../$S/figpipe.py extract SWI-650-SS_Assembly.pdf $W       # 提原图，报有效 dpi
python ../$S/sr.py $W/figures_src $W/figures_sr --places $W/data/images.json --min-dpi 150
python ../$S/figpipe.py detect $W                                # 出带框号核查图 qa/det_*.png
python ../$S/figpipe.py apply  $W $W/content/labels_zh.py        # 回叠中文 + 气泡重绘
python ../$S/figpipe.py sweep  $W $W/content/labels_zh.py        # 漏译排查（须为 0）
python $W/content/build.py                                       # 出稿 + 全部闸门
python ../make_showcase.py SWI-650-SS_Assembly.pdf translated/SWI-650-SS_Assembly_中文_v01.pdf $W ../../../docs/showcase
```

超分在 CPU 上约 1 分钟/幅（NVIDIA 显卡或 Apple 芯片快得多）；没有 torch 时 `sr.py` 自动退回 Lanczos 放大并在
`sr_report.json` 如实记录。检测框号取决于图像内容，改动插图后须重跑 `detect` 并按新核查图核对 `labels_zh.py`。
