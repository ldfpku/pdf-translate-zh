# -*- coding: utf-8 -*-
"""P 级（原页叠印）构建：TDT-650-0100 减震器总装图（虚构展示图纸）。

在 translate_pdf.py 生成的骨架上加了三处（都是图纸的常规做法，引擎不改）：
  1. 标题栏「除另有规定外」注记格交给 dwgnote 整格重排 —— 叠印阶段 keep() 跳过格内单元；
  2. 明细表按 dwg_bom 找到的外框做 tablefix 真网格重建（全表统一字号、合并格保留）；
  3. 同名表头按位置分译：修订栏的 DESCRIPTION =「说明」，明细表的 =「名称及规格」；
  4. 第 1 张的总注按标准列表重排（reflow）：英文两行的条目译成中文只剩一行，逐条叠印会在
     条目之间留下大小不一的空行；整块重排后行距统一、编号悬挂对齐。

    python content/build.py --dump   → 待译单元写到 content/pending.txt
    python content/build.py          → 出稿 + 六道关
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
import dwg_bom                          # noqa: E402
import dwgnote                          # noqa: E402
import fontkit                          # noqa: E402
import hybrid_overlay as hy             # noqa: E402
import reflow                           # noqa: E402
import sweep                            # noqa: E402
import tablefix                         # noqa: E402
import appendix                         # noqa: E402
import terms                            # noqa: E402

STEM = "tdt_650_0100_assembly"
WORK = os.path.dirname(HERE)
SRC = os.path.normpath(os.path.join(WORK, "../../TDT-650-0100_Assembly.pdf"))
OUT = os.path.normpath(os.path.join(WORK, "../TDT-650-0100_Assembly_中文_v01.pdf"))
TMP = OUT + ".tmp.pdf"
WHITELIST = "|".join(re.escape(w) for w in terms.WHITELIST_ADD)
DROP_FONT = None

# 注记格的范围按**源页**解析（成品页上英文锚点已不在，见 dwgnote.fix 的说明）
with fitz.open(SRC) as _s:
    NOTE_CLIP = {i + 1: dwgnote.parse(p)[0] for i, p in enumerate(_s)}
    BOM_CLIP = {i: dwg_bom.find_bom(p) for i, p in enumerate(_s)}


def keep(t, ctx=None):
    """保留原文不译的单元。⚠ 代号规则必须要求含数字（避坑 ㊱）。"""
    if ctx:
        clip = NOTE_CLIP.get(ctx[0])
        if clip is not None and fitz.Rect(ctx[1]).intersects(clip) \
                and clip.contains(fitz.Rect(ctx[1]).tl):
            return True             # 注记格：留给 dwgnote 整格重排
    return bool(BW.KEEP.match(t)) or not re.search(r"[A-Za-z]{2,}", t)


_base = BW.load(HERE, STEM)


def lookup(t, ctx=None):
    if t == "DESCRIPTION" and ctx and fitz.Rect(ctx[1]).y0 < 100:
        return "说明"               # 修订栏
    return _base(t)


if "--dump" in sys.argv:
    print(BW.dump(SRC, HERE, STEM, drop_font=DROP_FONT))
    sys.exit(0)

nb, nl, miss, over = hy.build(SRC, TMP, lookup, keep, auto_center=True,
                              drop_font=DROP_FONT, size_from="span")
with fitz.open(TMP) as d, fitz.open(SRC) as s:
    n_note = dwgnote.fix_doc(d, s)
    n_cell = 0
    for i, clip in BOM_CLIP.items():
        if clip is not None:
            c, m = tablefix.rebuild(d[i], clip + (-1, -1, 1, 1), lookup, base=7.5, keep=keep,
                                    src_page=s[i], page_no=i + 1)
            n_cell += c
            miss += m
    # 总注：以源页「NOTES:」为锚，收其下左界相同/悬挂缩进、纵向连续的编号条
    n_gen = 0
    for i, sp in enumerate(s):
        hits = sp.search_for("NOTES:")
        if not hits:
            continue
        a = hits[0]
        items = [(r, t) for r, t, _z, _k in hy.units_of(sp)
                 if re.match(r"\d+\.\s", t) and abs(r.x0 - a.x0) < 4 and r.y0 > a.y0]
        items.sort(key=lambda q: q[0].y0)
        if not items:
            continue
        ink = fitz.Rect(a)
        for r, _t in items:
            ink |= fitz.Rect(r.x0, r.y0, r.x0 + 1, r.y1)   # 写入框已向右放宽，只取纵向范围
        clip = fitz.Rect(ink.x0 - 1, ink.y0 - 1, 470, ink.y1 + 2)
        blocks = [("h", lookup("NOTES:"), {"before": 0.0})]
        for _r, t in items:
            zh = lookup(t) or t
            num, body = zh.split(" ", 1)
            blocks.append(("dt", num, body, {"before": 0.5}))
        reflow.render(d[i], clip, blocks, {"lead": 1.35, "hi": 7.6, "lo": 6.0, "bx": clip.x0 + 1})
        n_gen += 1
    d.saveIncr()
print(f"注记格重排 {n_note} 页；明细表重建 {n_cell} 格；总注重排 {n_gen} 页")
APX = appendix.append_to(TMP, terms)
size, how = fontkit.save_subset(TMP, OUT)
os.remove(TMP)
with fitz.open(OUT) as _o:          # 文档属性：源图纸的英文题名换成中文
    _o.set_metadata(dict(_o.metadata, title='TDT-650-0100 6-1/2" 减震器总成（双弹簧组）中文译本',
                         author="pdf-translate-zh 中文译本", subject="虚构展示图纸",
                         creator="pdf-translate-zh"))
    _o.saveIncr()
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
print("\n  " + ("PASS" if ok else "FAIL") + "  " + OUT)
sys.exit(0 if ok else 1)
