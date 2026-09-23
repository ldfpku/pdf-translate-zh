# 展示样例：TDT-650-0100 减震器总装图（虚构）

一份 3 张 B 号（11×17 in）的 CAD 工程图，复刻真实图纸翻译时最难的几类问题，用技能的**保位叠印（P 级）**路线做成中文图纸。
**品牌（Tethys Downhole Tools）、图号、零件号、人名缩写全部虚构，图形由 `make_drawing.py` 程序绘制。**
与 [showcase-swi](../showcase-swi/) 是同一件虚构产品：一份作业指导书、一份总装图。

成品与对比图在 [`docs/showcase/`](../../docs/showcase/)：

- 原图 [`TDT-650-0100_Assembly_en.pdf`](../../docs/showcase/TDT-650-0100_Assembly_en.pdf)（3 张）
- 译图 [`TDT-650-0100_Assembly_zh.pdf`](../../docs/showcase/TDT-650-0100_Assembly_zh.pdf)（3 张 + 附录 A、B，六道关全部 PASS）

## 复刻的难点 → 技能的处置

| 难点（原图） | 处置（译图） | 用到的模块 |
|---|---|---|
| 图纸的主体是剖面线、尺寸线、件号气泡、引线，版面坐标就是内容 | 原页叠印：只抹英文、线框不动，原位写中文；幅面与矢量图形数逐张核对 | `hybrid_overlay` |
| 标题栏「UNLESS OTHERWISE SPECIFIED」注记：± / ° / 粗糙度 ∨ 是矢量，小数点列靠前导空格对齐，长句被物理换行切开 | 整格抹掉按标准重排：整句译出，公差值逐图解析，± / ° 改为真文字 | `dwgnote` |
| 明细表：线条是路径 item；件号 2 的三种可选壳体用「缺行线」纵向合并；两处名称 CAD 导出时重影（同位写两遍） | 按外框做真网格重建，全表统一字号；合并格保留一个件号与数量；重影去重后只译一次 | `dwg_bom` + `tablefix` |
| 总注是悬挂缩进的编号条；专有声明 5.7pt 字、7.2pt 行距，逐行交错在右邻注记格之间；图名两行居中 | 续行拼回整句再译；总注按标准列表重排（行距统一、编号悬挂对齐） | `keyclean.join_wrapped`、`reflow` |
| 商号字标（17pt）与右侧地址行（5.6pt）底边齐平、空隙只有 2pt | 按字号断开：字标原样保留，地址行译出 | `dwg_overlay` |
| 竖排尺寸 `Ø6.50 OD`、`Ø4.25 SPRING BORE` | 旋转通道单独认领，按原方向竖排写回 | `hybrid_overlay.rot_lines` |
| 扭矩值、螺纹代号、零件号、标准号、分区编号 | 原样保留；保留项失踪关逐页核对 | `checks.check_kept_tokens` |
| 有意埋的两处原文缺陷：光壳体备注「USES ITEM #16」（应为件 15 耐磨套）；碟簧备注「每组 10 片 × 2 组」与数量栏 16、剖视图每组 8 片不一致 | 件号勘正并在格内注明原文，写进附录 A 甲；片数无法确证 → 保留原值加注，写进附录 A 乙 | 内容层 `terms.py` |
| — | 图纸之后附录 A《译校勘误说明》、附录 B《中英术语对照表》，各自另起一页（A4 竖排） | `appendix` |

## 复现

```bash
S=../../skills/pdf-translate-zh/scripts
python make_drawing.py                                             # 生成英文源图 build/TDT-650-0100_Assembly.pdf
cd build && python ../$S/translate_pdf.py TDT-650-0100_Assembly.pdf   # 定级（P）+ 叠印骨架
W=translated/TDT-650-0100_Assembly
cp ../content/*.py $W/content/                                     # 本目录的内容层（词表、附录数据、构建脚本）
python $W/content/build.py --dump                                  # 待译单元 → content/pending.txt（只剩注记格碎片：由 dwgnote 整格重排，不进词表）
python $W/content/build.py                                         # 叠印 + 注记格/明细表/总注重排 + 六道关
python ../make_showcase.py TDT-650-0100_Assembly.pdf translated/TDT-650-0100_Assembly_中文_v01.pdf ../../../docs/showcase
```

`content/build.py` 在 `translate_pdf.py` 生成的骨架上只加了图纸的常规处理（注记格、明细表、总注重排、同名表头按位置分译），引擎本身不改。
