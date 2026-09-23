# -*- coding: utf-8 -*-
"""P 级（原页叠印）构建入口：python content/build.py —— 叠印 + 六道关，任何 FAIL 返回非 0。

填写顺序：
  1. python content/build.py --dump   → 待译单元写到 content/pending.txt（键 = units_of 清理后的串）
  2. 在 content/stator_housing_drawing_dict.py 的 D 里逐条写译文；量大时分批写 stator_housing_drawing_b01.py、_b02.py …
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

STEM = 'stator_housing_drawing'
WORK = os.path.dirname(HERE)
SRC = os.path.normpath(os.path.join(WORK, '../../stator_housing_drawing.pdf'))
OUT = os.path.normpath(os.path.join(WORK, '../stator_housing_drawing_中文_v01.pdf'))
TMP = OUT + ".tmp.pdf"
TABLE_PAGES = []        # 需要 tablefix 真网格重建的页（0 基）；图纸的明细表常用 —— 先确认 regions() 认对了
WHITELIST = r"Rev\b|NORTHSTAR DRILLING TOOLS"   # 公司名保留原文
DROP_FONT = None        # 水印字体名正则（有水印时填）


def keep(t, ctx=None):
    """保留原文不译的单元。⚠ 代号规则必须要求含数字（避坑 ㊱）。"""
    return bool(BW.KEEP.match(t)) or not re.search(r"[A-Za-z]{2,}", t)


lookup = BW.load(HERE, STEM)

if "--dump" in sys.argv:
    print(BW.dump(SRC, HERE, STEM, drop_font=DROP_FONT))
    sys.exit(0)

# size_from="span"：写入字号取源 span 真字号（旧缺省按字形框高，中文偏大约 18%）
nb, nl, miss, over = hy.build(SRC, TMP, lookup, keep, auto_center=True,
                              drop_font=DROP_FONT, size_from="span")
if TABLE_PAGES:
    import tablefix
    tn, tmiss = tablefix.fix_pages(TMP, SRC, TABLE_PAGES, lookup, keep, drop_font=DROP_FONT)
    miss += tmiss
size, how = fontkit.save_subset(TMP, OUT)
os.remove(TMP)
print(f"写入：段 {nb} 行 {nl}；成品 {size / 1e6:.2f} MB（{how}）")

ok = True
ok &= checks.report("1 未命中", miss, detail=15)
ok &= checks.report("2 溢出", over, detail=10)
eng, half = checks.check_text(OUT, whitelist=WHITELIST)
ok &= checks.report("3 残留英文", eng, detail=10)
ok &= checks.report("4 缺字", checks.check_glyphs(OUT), detail=10)
ok &= checks.report("5 中文重叠", checks.check_overlap(OUT), detail=10)
ok &= checks.report("6 保留项失踪", checks.check_kept_tokens(SRC, OUT), detail=10)
ok &= checks.report("6b 跨字号保留项", sweep.lost_tokens(SRC, OUT), detail=10)
ok &= checks.report("文本层异常码位（U+2011/U+00A0）", checks.check_codepoints(OUT), detail=6)
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
