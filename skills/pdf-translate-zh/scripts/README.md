# scripts/ 模块地图

> 这些模块经 **28 份文档全量交付**验证（六道关 28/28）。
> 与文档无关的部分都在这里，**换文档只改内容层**（词表 + 逐页译文 + build.py）。
>
> 模块名沿用工程期的历史命名，与调试记录、注释里的引用一一对应，**不要改名**。

---

## 入口

| 文件 | 用途 |
|---|---|
| `bootstrap.py` | **环境全自动**：入口脚本自动调用，缺包装进私有目录、Linux 字体自动转换、超分后端按需自动装；`python3 bootstrap.py [--sr]` 一次配齐 |
| `doctor.py` | 只报告的体检：依赖、中文字体解析、缓存、超分权重逐项自检（`--selftest` 引擎冒烟，`--install` 补装必需包，`--fonts` 把 Noto CJK 转 TrueType） |
| `translate_pdf.py` | **每份新文档的入口**：定级（写 `data/route.json`）+ 素材提取 + 生成内容层骨架。R/H 级：`content/_engine.py build.py content.py terms.py`；P/S 级：`build.py`（叠印 + 六道关，`--dump` 导出待译单元）+ `<名>_dict.py` |
| `route.py` | 单独定级：逐页判 R/H/P/S（V2 三级 + 幻灯片），给出 P 级页清单 |
| `fontkit.py` | 跨平台字体解析（所有脚本取字体的唯一入口）；`save_subset()` 叠印成品子集化存盘；`convert_system_cjk()` CFF→TrueType；`python fontkit.py` 打印本机解析结果 |
| `rebuild_all.py` / `build_all.py` | 全量重建 / 回归：`--root` 或环境变量 `PDF_ZH_PROJECTS` 指定项目根目录 |
| `sweep.py` | 全量成品体检（第六道关：保留项失踪 / 中文重叠 / 缺字） |

---

## 叠印路线

| 文件 | 行数 | 用途 |
|---|---|---|
| `hybrid_overlay.py` | 1.3k | **总装**。三通道分区、排版记号、几何对齐判据、下划线转粗体、表单标签对齐、中文预折行 |
| `dwg_overlay.py` | 650 | **行级**通道（表格区、表单）。含 `Overlay`、`lines_of`、`vrules`、水印过滤、`rescue_*` |
| `text_overlay.py` | 350 | **段级**通道（散文）。含 `BlockOverlay`、`blocks_of`、逐词块接回整行 |
| `keyclean.py` | 160 | 待译键清理：拼点导线、拼截断行、归一 PUA、折叠重复词 |
| `tablefix.py` | 480 | **表格真网格重建**：按行带定列 → 归格 → 全表统一字号重排 |
| `dwg_bom.py` | 270 | 线框几何：`segments()` 取水平/垂直线段（表格区自求的基础）、`find_bom`、`grid` |
| `vectext.py` | 420 | 图内文字定位与回叠：`runs`/`raster_runs`/`label_runs`/`snap`/**`inkbox`**/`overlay` |
| `genraster.py` | 60 | 图内位图英文流水线：粗框 → 墨迹框 → 生成 `raster_zh_pNN.py` + 画框出图 |
| `inkbox.py` | 35 | `inkbox()` 的独立副本（`vectext` 里也有一份，供单独调试） |
| `raster_text.py` | 200 | 位图内英文的另一套定位（比例坐标法），历史实现 |
| `toclinks.py` | 240 | 目录跳转链接 + PDF 书签；连续页码／**分节页码**／**文件编号**三种索引；幂等、层级由编号推出、支持页码勘正（`fix=`） |
| `reflow.py` | 471 | **标准重排通道**：整块抹掉按块 DSL 重排、**区域内字号统一**；目录点引线从右往左画 |
| `toccheck.py` | 393 | **封面与目录的八道判据**：数量／矩形／落点回验／页码右端／同级左界／保留项／残留英文／封面对齐 |
| `tocsweep.py` | 110 | 八道判据的全库驱动**模板**：按册登记封面页与目录页，换项目只改这张表 |
| `batchwork.py` | 130 | 分批词表加载（`load`）+ **重复键检查**（`dupes`，交付前必跑） |
| `slidekit.py` | 430 | **幻灯片专用**：`units` 两形态项目符号 + 按列聚类 + 字色；`flow_items`/`layout_flow` 列表整列重排；`bullet_ink` 符号实测重绘；`subscript_pass` 真下标；`orphans` 断句体检（见 `slides.md`） |

### 典型 build.py 骨架

```python
import hybrid_overlay as hy, tablefix, toclinks, batchwork as BW

_LOOKUP = BW.load(HERE, "myjob")        # myjob_dict.py + myjob_bNN.py
def keep(text, ctx=None): ...           # ⚠ 见 pitfalls ㊱
def lookup(text, ctx=None): ...         # 可接收 (页号, 矩形) 上下文

nb, nl, miss, over = hy.build(SRC, DST, lookup, keep,
                              auto_center=True,
                              col_split=fitz.Rect(30, 45, 590, 130),
                              drop_font=WM_FONT, wm_keep=False)

tablefix.fix_pages(DST, SRC, TABLE_PAGES, lookup, keep, drop_font=WM_FONT)
vectext.overlay(doc[pi], RASTER_ZH[pi])          # 图内位图英文
# …构建期六道关…
```

附录另起一个 `appendix.py`，**在 build 之后跑**（build 只写正文并删掉已合并的附录页）；
`toclinks.add()` 要在**合并附录之后**才加。

---

## 从零重建路线

| 文件 | 用途 |
|---|---|
| `extract.py` | 素材提取：勘察、渲染转储、表格抽取、插图剪裁、contact sheet |
| `builder.py` | 版式引擎：页面几何（`A4`/`LETTER`/…）、抬头/页脚装饰、**流式装配（R 级）或 1:1 装配（P/H 级）**、逐页装配自检 |
| `render.py` | 块 DSL → ReportLab flowable（含 `("pb",)` 强制分页、`("cpb", h)` 条件分页） |
| `driver.py` | 标准构建驱动：每份文档的 `build.py` 只填 Job 配置；`Job(flow=True)` = R 级语义重排，附带内容对账 + 页数预算两道关 |
| `formkit.py` | 可填写表单的译文重建 |
| `probe_geom.py` | 量取源 PDF 的版心几何，供内容层照抄 |
| `verify.py` | 交付前闸门：版心外杂物、页边墨迹像素级比对、页脚净空 |

---

## 两条路线共用

| 文件 | 用途 |
|---|---|
| `zhlib.py` | 中文字体注册（经 `fontkit`）、`zh()` 全角规范化、样式表（`styles(flow=True)` 标题不落页底）、品牌色（`set_brand()` 在 build.py 里换，不改引擎）、`pick_glyph()` 按本机字体挑符号 |
| `checks.py` | 残留英文（纯单位/代号行自动放行）、缺字（按实际写入字体逐 span 查）、文本层码位、行首/行尾禁则、中文重叠、页码序列、目录交叉回验、**整册内容对账** `check_content_tokens` |
| `appendix.py` | 附录 A《译校勘误说明》甲/乙/丙 + 附录 B《中英术语对照表》 |
| `preview.py` | 逐页出图 + 整册缩览拼贴（目检用） |
| `sr.py` | **插图超分**：Real-ESRGAN x4plus，按有效 dpi 筛选（<150 才处理）；后端 torch（CUDA/MPS/CPU）→ onnxruntime（`--export-onnx` 导出的模型）→ Lanczos 兜底；分块推理控内存；权重多源下载 + SHA-256；`--fetch` 预下载；处置方式写 `sr_report.json` |
| `tightbox.py` | 检测框**收紧到文字本体**：引线/箭头头/噪点/单字母/彩底五条规则，返回行高供定字号 |
| `bubbles.py` | **件号气泡**：填洞/射线/模板三法求环心 → 擦旧环补引线 → 重绘环与 Arial Bold 编号 → 旧环残留判据 → 放大拼贴 |
| `uniq_desc.py` | 列出「零件描述」的唯一串，建规则化译名用 |
| `selftest.py` | 引擎冒烟自检：`zh()` 单测、块 DSL 参数位置、装配与几何 |

---

## `examples/`

| 文件 | 示范了什么 |
|---|---|
| `toc_pages_example.py` | `tocsweep.py --pages` 的登记表格式（封面页 / 目录页 / 白名单 / 明示豁免） |

客户专属的术语表、页眉块、白名单放在各项目自己的内容层（`translated/<册>/content/`）里，不放进技能。

---

## 依赖与可移植性

```
（不用手动装）入口脚本自动补装依赖；想一次配齐：python3 bootstrap.py [--sr]
没有 Python 的机器：sh ../setup.sh  /  powershell -ExecutionPolicy Bypass -File ..\setup.ps1
只看不改：python3 doctor.py
```

| 项 | 说明 |
|---|---|
| 必需包 | PyMuPDF（`import pymupdf`，旧版退回 `fitz`）、reportlab、Pillow、numpy、fonttools |
| 可选包 | scipy（件号气泡）；插图超分二选一：torch（macOS 自带 MPS；Windows+NVIDIA 装 CUDA 版）或 onnxruntime + ONNX 模型；都没有时 Lanczos 兜底 |
| Python 命令 | macOS / Linux 用 `python3`，Windows 用 `py`；系统 Python 禁止 pip（PEP 668）时 `doctor.py --install` 给出建虚拟环境的命令 |
| 中文字体 | `fontkit` 按「环境变量 → 技能 `fonts/` → 系统字体 → PyMuPDF 内置 Droid Sans Fallback」解析。Windows 仍优先微软雅黑；macOS 取苹方/华文黑体；Linux 取 Noto/思源/文泉驿。ReportLab 只认 TrueType 轮廓，CFF 字体自动跳过 |
| 固定字体 | 环境变量 `PDF_ZH_FONT`、`PDF_ZH_FONT_BOLD`（值为字体文件路径，TTC 可写 `路径#序号`），或把字体文件放进技能根目录的 `fonts/` —— 各机器产出一致 |
| 缓存 | 抽出的 TTC 子字体与超分权重放用户缓存（Windows `%LOCALAPPDATA%\pdf-translate-zh\cache`，其他 `~/.cache/pdf-translate-zh`）；`PDF_ZH_CACHE` 可改 |
| 超分权重 | `RealESRGAN_x4plus.pth` 67 MB 不随技能分发，首次超分或 `doctor.py --sr` 时依次从 GitHub / HF 镜像下载并校验；`PDF_ZH_SR_URL` 指定自己的镜像；离线放进 `scripts/models/` 或设 `PDF_ZH_SR_WEIGHTS`；ONNX 模型设 `PDF_ZH_SR_ONNX` 或放 `scripts/models/RealESRGAN_x4plus.onnx` |
| 工作区 | 路径一律相对工作区；`content/_engine.py` 按 `PDF_TRANSLATE_ZH_HOME` → 创建时路径 → 常见技能目录找引擎，工作区可整体拷到别的机器重跑 |
| 技能目录 | 引擎不往技能目录写任何东西（自检产物写临时目录），只读安装也能用 |
