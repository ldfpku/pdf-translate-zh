# -*- coding: utf-8 -*-
"""逐页出图 + 整册缩览拼贴，供目检（SKILL §2 的 10_preview）。

    python preview.py <pdf> <outdir> [--dpi 110] [--pages 1,2,5-7]
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse
import math
import os
import sys

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz


def parse_pages(spec, n):
    if not spec:
        return list(range(1, n + 1))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return [p for p in out if 1 <= p <= n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--pages", default="")
    ap.add_argument("--sheet", action="store_true", help="另出整册缩览拼贴")
    ap.add_argument("--cols", type=int, default=6)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(a.outdir, exist_ok=True)

    doc = fitz.open(a.pdf)
    pages = parse_pages(a.pages, doc.page_count)
    files = []
    for p in pages:
        f = os.path.join(a.outdir, f"q{p:03d}.png")
        doc[p - 1].get_pixmap(dpi=a.dpi).save(f)
        files.append(f)
    print(f"出图 {len(files)} 张 → {a.outdir}")

    if a.sheet and files:
        from PIL import Image, ImageDraw, ImageFont
        import fontkit
        fnt = fontkit.pil("mono", 15)
        cell = 300
        rows = math.ceil(len(files) / a.cols)
        sh = Image.new("RGB", (a.cols * (cell + 8) + 8, rows * (cell + 26) + 8),
                       "white")
        d = ImageDraw.Draw(sh)
        for k, f in enumerate(files):
            r, c = divmod(k, a.cols)
            x, y = 8 + c * (cell + 8), 8 + r * (cell + 26)
            im = Image.open(f).convert("RGB")
            im.thumbnail((cell, cell), Image.LANCZOS)
            d.rectangle([x, y + 20, x + cell, y + 20 + cell],
                        outline=(200, 200, 200))
            sh.paste(im, (x + (cell - im.width) // 2, y + 20))
            d.text((x + 2, y + 2), f"p{pages[k]}", fill=(180, 0, 0), font=fnt)
        out = os.path.join(a.outdir, "sheet.png")
        sh.save(out)
        print("缩览拼贴:", out)
    doc.close()


if __name__ == "__main__":
    main()
