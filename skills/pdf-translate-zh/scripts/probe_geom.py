# -*- coding: utf-8 -*-
"""量取源 PDF 的版心几何，供内容层照抄，免去逐份目测。

    python probe_geom.py <src.pdf> [--pages 1,2]

输出：页面尺寸、正文左右界（按 ≥9.6pt 文本行左界频次）、
      页眉带下沿、页脚带上沿、页脚横线 y、各页表格 bbox 的 x 跨度
      （半幅表 ⇒ 原版为「图左表右」并排，须照抄，见 SKILL §5）。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse
import sys
from collections import Counter

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

BODY_SZ = 9.6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    doc = fitz.open(a.pdf)
    sel = ([int(x) for x in a.pages.split(",") if x.strip()]
           if a.pages else list(range(1, doc.page_count + 1)))

    r0 = doc[0].rect
    print(f"页面 {r0.width:.1f} x {r0.height:.1f}   共 {doc.page_count} 页")

    L, R, TOPS, BOTS = Counter(), Counter(), [], []
    for pno in sel:
        pg = doc[pno - 1]
        ys = []
        for b in pg.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                if not "".join(s["text"] for s in ln["spans"]).strip():
                    continue
                sz = max(s["size"] for s in ln["spans"])
                if sz >= BODY_SZ:
                    L[round(ln["bbox"][0], 1)] += 1
                    R[round(ln["bbox"][2], 1)] += 1
                ys.append((ln["bbox"][1], ln["bbox"][3], round(sz, 1)))
        if ys:
            ys.sort()
            TOPS.append(ys[0][0])
            BOTS.append(ys[-1][1])

    print(f"正文左界（频次前 5）: {L.most_common(5)}")
    print(f"正文右界（频次前 5）: {R.most_common(5)}")
    if TOPS:
        print(f"最上文本行 y0: min={min(TOPS):.1f}  max={max(TOPS):.1f}")
        print(f"最下文本行 y1: min={min(BOTS):.1f}  max={max(BOTS):.1f}")

    print("\n横线（宽 > 200pt，疑为页眉/页脚分隔线）:")
    seen = Counter()
    for pno in sel:
        for d in doc[pno - 1].get_drawings():
            r = fitz.Rect(d["rect"])
            if r.height < 2.5 and r.width > 200:
                seen[(round(r.y0, 1), round(r.x0, 1), round(r.x1, 1))] += 1
    for (y, x0, x1), n in sorted(seen.items()):
        print(f"   y={y:7.1f}  x={x0:6.1f}~{x1:6.1f}   出现 {n} 页")

    print("\n表格 bbox（x 跨度只占半幅 ⇒ 原版为图左表右并排，须照抄）:")
    for pno in sel:
        pg = doc[pno - 1]
        try:
            tabs = pg.find_tables(strategy="lines_strict").tables
        except Exception:
            tabs = []
        for ti, t in enumerate(tabs):
            b = fitz.Rect(t.bbox)
            frac = b.width / r0.width
            flag = "  ← 半幅" if frac < 0.55 else ""
            print(f"   p{pno} #{ti}  x={b.x0:6.1f}~{b.x1:6.1f} "
                  f"y={b.y0:6.1f}~{b.y1:6.1f}  占宽 {frac:.0%}{flag}")

    print("\n嵌入位图放置矩形:")
    for pno in sel:
        pg = doc[pno - 1]
        for im in pg.get_images(full=True):
            for r in pg.get_image_rects(im[0]):
                print(f"   p{pno} xref={im[0]}  {[round(v,1) for v in r]}  "
                      f"{r.width:.1f}x{r.height:.1f}pt")
    doc.close()


if __name__ == "__main__":
    main()
