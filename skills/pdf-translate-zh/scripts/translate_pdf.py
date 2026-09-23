# -*- coding: utf-8 -*-
"""入口驱动：给定一个 PDF 或一个目录，建好工作区、定级、跑完素材提取。

    python translate_pdf.py <file.pdf|dir> [--dpi 300] [--outdir DIR]

目录约定：
    输入  .../某目录/xxx.pdf
    产出  .../某目录/translated/xxx_中文_v01.pdf     ← 译稿（版本号自动顺延）
          .../某目录/translated/xxx/                ← 该文档的工作区
                data/     提取物（blocks/prose_dump/tables/figures/route.json）
                figures/  纯净剪裁的插图
                qa/       拼贴核验图（必须目检）
                content/  内容层：_engine.py build.py content.py terms.py

本脚本只做与文档无关的部分。内容层（译文、术语、勘误）按 content/ 下生成的
骨架填写，再 `python content/build.py` 出稿并过闸门。

工作区可整体搬到别的机器：路径一律相对工作区；引擎位置由 content/_engine.py
按「环境变量 PDF_TRANSLATE_ZH_HOME → 创建时记录的路径 → 常见技能目录」查找。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse, json, os, re, subprocess, sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def next_version(outdir, stem):
    """已有 _v01 则返回 v02，依此类推。"""
    n = 0
    if os.path.isdir(outdir):
        for f in os.listdir(outdir):
            m = re.match(re.escape(stem) + r"_中文_v(\d+)\.pdf$", f)
            if m:
                n = max(n, int(m.group(1)))
    return f"v{n + 1:02d}"


ENGINE = '''# -*- coding: utf-8 -*-
"""把 pdf-translate-zh 的 scripts/ 加进 sys.path。build.py 第一行 import 它。

查找顺序：环境变量 PDF_TRANSLATE_ZH_HOME（技能根目录或其 scripts/）
        → 创建工作区时记录的路径 → 用户目录下常见的技能安装位置。
工作区搬到另一台机器后，只要技能装在常见位置或设了环境变量就能直接重跑。
"""
import os
import sys

sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_RECORDED = %r
_NAMES = ("pdf-translate-zh",)


def _candidates():
    env = os.environ.get("PDF_TRANSLATE_ZH_HOME")
    if env:
        yield env
        yield os.path.join(env, "scripts")
    yield _RECORDED
    home = os.path.expanduser("~")
    for base in (".claude/skills", ".agents/skills", ".codex/skills",
                 ".config/claude/skills", "skills"):
        for n in _NAMES:
            yield os.path.join(home, base, n, "scripts")


for _c in _candidates():
    if _c and os.path.isfile(os.path.join(_c, "zhlib.py")):
        if _c not in sys.path:
            sys.path.insert(0, _c)
        ENGINE_DIR = _c
        break
else:
    raise SystemExit("找不到 pdf-translate-zh 的 scripts/ 目录。"
                     "请设置环境变量 PDF_TRANSLATE_ZH_HOME 指向技能目录。")

# 依赖与中文字体自动就位（缺包自动装、Linux 只有 CFF 字体时一次性转换）
import bootstrap  # noqa: E402
bootstrap.ensure()
bootstrap.ensure_fonts()
'''

BUILD = '''# -*- coding: utf-8 -*-
"""构建入口：python content/build.py —— 出稿并跑完全部闸门（FAIL 即返回非 0）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _engine  # noqa: F401,E402  —— 定位技能引擎
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from driver import Job, run            # noqa: E402
from builder import A4, LETTER         # noqa: E402,F401
import content as C                    # noqa: E402
import terms as T                      # noqa: E402

WORK = os.path.dirname(HERE)                               # 工作区
SRC = os.path.normpath(os.path.join(WORK, %r))           # 原文（相对工作区）
OUT = os.path.normpath(os.path.join(WORK, %r))           # 译稿（相对工作区）

job = Job(
    name=%r,
    src=SRC, work=WORK, out=OUT,
    pages=C.CHAPTERS,
    flow=%r,                # R 级语义重排 = True；P/H 级 1:1 同源 = False
    geom=%s,                # 文本类文档用 A4；图纸/表单保持原幅面
    mast_title=getattr(C, "MAST_TITLE", ""),
    foot=getattr(C, "FOOT", ("", "", "")),
    used_figs=getattr(C, "USED_FIGS", ()),
    labels_zh=getattr(C, "LABELS_ZH", None),   # 图内矢量英文 → 中文（data/figures.json 的 labels）
    glossary=T.GLOSSARY, jia=T.JIA, yi=T.YI, bing=T.BING,
    errata_intro=getattr(T, "ERRATA_INTRO", None),   # 附录 A 引言：行业判定与依据
    whitelist_add=getattr(T, "WHITELIST_ADD", ()),
    token_ignore=getattr(T, "TOKEN_IGNORE", ()),
)

if __name__ == "__main__":
    sys.exit(0 if run(job) else 1)
'''

CONTENT = '''# -*- coding: utf-8 -*-
"""内容层：逐章块列表（块 DSL 见 scripts/render.py 顶部）。

填写前先通读 ../data/prose_dump.txt 与 ../data/tables_readable.txt，并确认
../data/route.json 的定级。R 级（默认）按**语义**组织：一段一个 ("p", …)，
列表一项一个条目 —— 物理断行不是翻译单元边界。

常用块：("h1"|"h2"|"h3", 文本)  ("p", 文本)  ("bul", [..])  ("ol", [..])
        ("step", 文本)  ("box", 文本, "warn"|"danger"|"note")
        ("fig", "文件名.png", 宽pt, "图 1  图题")   ("tbl", 表格工厂, "表 1  表题")
        ("pb",) 强制分页   ("cpb", 120) 剩余不足 120pt 即分页
表格用 lambda 工厂，并传 width=FW 把列宽按比例缩放到版心宽（否则可能冲出版心）：
        ("tbl", lambda: render.grid_table(rows, [3, 1, 1], S, width=FW), "表 1  …")
"""
import render  # noqa: F401
from builder import A4
from zhlib import styles

S = styles(flow=True)    # 与 build.py 的 Job(flow=True) 一致
FW = A4.fw               # 版心宽（pt）；换幅面时同步改

MAST_TITLE = ""          # 页眉题名（原版有抬头时填）
FOOT = ("", "", "")      # 页脚 左/中/右
USED_FIGS = ()           # 正文引用到的 figures/ 文件名
# 图内矢量英文（extract 已抹掉并记在 data/figures.json 的 labels 里）→ 中文。
# 构建时自动回叠到 figures/*.png；尺寸代号/件号/商标写成与原文相同即「保留」。
LABELS_ZH = {}

CHAPTERS = [
    [("h1", "1  概述"),
     ("p", "（在此填入译文）")],
]
'''

TERMS = '''# -*- coding: utf-8 -*-
"""术语与附录数据。附录 A/B 由此自动生成，排在译文之后、各自另起一页。"""

# 附录 A 引言：行业判定与依据（§1 第 0 步的结论写在这里）
ERRATA_INTRO = ""

# 附录 B《中英术语对照表》：{类别: [(英文, 中文), ...]}
GLOSSARY = {
    # "动力段": [("stator", "定子"), ("rotor", "转子")],
}

# 附录 A《译校勘误说明》——行首「序号」列自动补
JIA = []    # 甲 原文缺陷与勘正：(原文位置, 英文原文/问题, 问题类型, 勘正与译文, 依据)
YI = []     # 乙 存疑保留：(原文位置, 存疑内容, 冲突对象, 本稿处理, 须确认事项)
BING = []   # 丙 版式与插图修复：(涉及部位, 原始问题, 修复处理)

WHITELIST_ADD = ()   # 译版中合法保留的英文：品牌、型号、标准号
TOKEN_IGNORE = ()    # 内容对账允许消失的记号：原版页眉页脚的页码、修订号等
'''


BUILD_P = '''# -*- coding: utf-8 -*-
"""P 级（原页叠印）构建入口：python content/build.py —— 叠印 + 六道关，任何 FAIL 返回非 0。

填写顺序：
  1. python content/build.py --dump   → 待译单元写到 content/pending.txt（键 = units_of 清理后的串）
  2. 在 content/%(stem)s_dict.py 的 D 里逐条写译文；量大时分批写 %(stem)s_b01.py、_b02.py …
     （同样的 D + lookup；先加载者胜，重复键由闸门报）。空串 "" = 保留原文。
  3. python content/build.py          → 出稿 + 闸门；未命中清零为止
先读 references/overlay.md（待译单元不可信的五类、keep 规则、排版记号）。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _engine  # noqa: F401,E402
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
try:
    import pymupdf as fitz
except ImportError:
    import fitz
import batchwork as BW                  # noqa: E402
import checks                           # noqa: E402
import fontkit                          # noqa: E402
import hybrid_overlay as hy             # noqa: E402
import sweep                            # noqa: E402
import appendix                         # noqa: E402
import terms                            # noqa: E402  附录 A/B 的数据（content/terms.py）

STEM = %(stem)r
WORK = os.path.dirname(HERE)
SRC = os.path.normpath(os.path.join(WORK, %(src)r))
OUT = os.path.normpath(os.path.join(WORK, %(out)r))
TMP = OUT + ".tmp.pdf"
TABLE_PAGES = []        # 需要 tablefix 真网格重建的页（0 基）；图纸的明细表常用 —— 先确认 regions() 认对了
WHITELIST = r"Rev\\b"   # 成品里合法保留的英文（公司名、人名、商标）的正则
DROP_FONT = None        # 水印字体名正则（有水印时填）


def keep(t, ctx=None):
    """保留原文不译的单元。⚠ 代号规则必须要求含数字（避坑 ㊱）。"""
    return bool(BW.KEEP.match(t)) or not re.search(r"[A-Za-z]{2,}", t)


lookup = BW.load(HERE, STEM)

if "--dump" in sys.argv:
    print(BW.dump(SRC, HERE, STEM, drop_font=DROP_FONT))
    sys.exit(0)

# size_from="span"：写入字号取源 span 真字号（旧缺省按字形框高，中文偏大约 18%%）
nb, nl, miss, over = hy.build(SRC, TMP, lookup, keep, auto_center=True,
                              drop_font=DROP_FONT, size_from="span")
if TABLE_PAGES:
    import tablefix
    tn, tmiss = tablefix.fix_pages(TMP, SRC, TABLE_PAGES, lookup, keep, drop_font=DROP_FONT)
    miss += tmiss
# 附录 A《译校勘误说明》、B《中英术语对照表》追加在叠印正文之后，各自另起一页（A4 竖排）
APX = appendix.append_to(TMP, terms)
size, how = fontkit.save_subset(TMP, OUT)
os.remove(TMP)
print(f"写入：段 {nb} 行 {nl}；成品 {size / 1e6:.2f} MB（{how}）")

ok = True
ok &= checks.report("1 未命中", miss, detail=15)
ok &= checks.report("2 溢出", over, detail=10)
ok &= checks.report("附录分页（A、B 各自另起一页，不与正文同页）", checks.check_appendix_pages(OUT, APX))
eng, half = checks.check_text(OUT, allow_pages=appendix.apx_pages(APX), whitelist=WHITELIST)
ok &= checks.report("3 残留英文", eng, detail=10)
ok &= checks.report("4 缺字", checks.check_glyphs(OUT), detail=10)
ok &= checks.report("5 中文重叠", checks.check_overlap(OUT), detail=10)
ok &= checks.report("6 保留项失踪", checks.check_kept_tokens(SRC, OUT), detail=10)
ok &= checks.report("6b 跨字号保留项", sweep.lost_tokens(SRC, OUT), detail=10)
ok &= checks.report("文本层异常码位（别名码位，图号/汉字不可检索）", checks.check_codepoints(OUT), detail=6)
ok &= checks.report("词表重复键", BW.dupes(HERE, STEM))
with fitz.open(SRC) as a, fitz.open(OUT) as b:
    geo = [i + 1 for i in range(len(a))
           if a[i].rect != b[i].rect or len(a[i].get_drawings()) > len(b[i].get_drawings()) + 2]
ok &= checks.report("版面保持（幅面不变、矢量图形未被抹）", geo)
if size > 20 * os.path.getsize(SRC) and size > 3e6:
    print("  FAIL 成品体积异常（字体未子集化？）")
    ok = False
print("\\n  " + ("PASS" if ok else "FAIL") + "  " + OUT)
sys.exit(0 if ok else 1)
'''

DICT_P = '''# -*- coding: utf-8 -*-
"""%(stem)s 叠印词表。键 = hybrid_overlay.units_of() 清理后的单元（见 pending.txt）。

值 = 中文，尺寸/件号/螺纹代号/标准号原样写进译文；可用 "\\n" 显式分行（一个单元里
并了两行时，如「Ø6.75 OD Ø5.10 ID」→「外径 Ø6.75\\n内径 Ø5.10」）。
"" = 保留原文不动（公司名、商标、人名）—— 同时把它加进 build.py 的 WHITELIST，
否则残留英文关会报。"""
D = {
}


def lookup(t):
    return D.get(t)
'''


def _write_once(path, text):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def prepare(pdf, outroot, dpi):
    stem = os.path.splitext(os.path.basename(pdf))[0]
    work = os.path.join(outroot, stem)
    for sub in ("data", "figures", "render", "qa", "content"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)

    # 定级（R/H/P/S）写盘，供内容层与交付说明引用
    sys.path.insert(0, HERE)
    import route
    try:
        rt = route.classify(pdf)
        with open(os.path.join(work, "data", "route.json"), "w", encoding="utf-8") as fh:
            json.dump(rt, fh, ensure_ascii=False, indent=1)
        print(f"定级     : {rt['level']} —— {rt['reason']}")
        level = rt["level"]
    except Exception as e:                       # 定级失败不阻断提取
        print(f"定级失败 : {e}")
        level = "R"

    ver = next_version(outroot, stem)
    target = os.path.join(outroot, f"{stem}_中文_{ver}.pdf")
    cdir = os.path.join(work, "content")
    rel_src = os.path.relpath(os.path.abspath(pdf), work)
    rel_out = os.path.relpath(target, work)
    _write_once(os.path.join(cdir, "_engine.py"), ENGINE % HERE)
    if level in ("P", "S"):
        # 保位叠印：骨架直接是叠印构建 + 六道关（S 级另见 references/slides.md 的 slidekit 装配）
        dstem = re.sub(r"\\W+", "_", stem).strip("_").lower() or "doc"
        if dstem[0].isdigit():
            dstem = "d" + dstem
        _write_once(os.path.join(cdir, "build.py"),
                    BUILD_P % dict(stem=dstem, src=rel_src, out=rel_out))
        _write_once(os.path.join(cdir, f"{dstem}_dict.py"), DICT_P % dict(stem=dstem))
        _write_once(os.path.join(cdir, "terms.py"), TERMS)
    else:
        # R 级流式重排；H 级同样从这里起步，P 页另用叠印出单页后按序拼合
        _write_once(os.path.join(cdir, "build.py"),
                    BUILD % (rel_src, rel_out, stem, True, "A4"))
        _write_once(os.path.join(cdir, "content.py"), CONTENT)
        _write_once(os.path.join(cdir, "terms.py"), TERMS)

    r = subprocess.run([sys.executable, os.path.join(HERE, "extract.py"),
                        pdf, work, "--dpi", str(dpi)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=dict(os.environ, PYTHONUTF8="1"))
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return None
    print(f"工作区   : {work}")
    print(f"目标译稿 : {target}")
    return work, target


def main():
    _bs.ensure_fonts()          # Linux 上只有 CFF 中文字体时一次性转换（其他情况立即返回）
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="一个 PDF 文件，或一个含 PDF 的目录")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--outdir", default=None,
                    help="默认为输入同级目录下的 translated/")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    t = os.path.abspath(a.target)
    if os.path.isdir(t):
        pdfs = sorted(os.path.join(t, f) for f in os.listdir(t)
                      if f.lower().endswith(".pdf"))
        base = t
    else:
        pdfs, base = [t], os.path.dirname(t)
    if not pdfs:
        print("未找到 PDF")
        return 1

    outroot = a.outdir or os.path.join(base, "translated")
    os.makedirs(outroot, exist_ok=True)
    print(f"共 {len(pdfs)} 个 PDF，产出目录 {outroot}\n")
    for p in pdfs:
        print("=" * 70)
        print("处理:", os.path.basename(p))
        prepare(p, outroot, a.dpi)
    print("\n素材提取完成。请先目检 qa/contact_*.png，再填写 content/ 下的内容层。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
