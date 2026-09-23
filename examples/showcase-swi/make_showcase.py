# -*- coding: utf-8 -*-
"""生成 README「效果展示」用的前后对比图（docs/showcase/*.png）。

    python make_showcase.py <源.pdf> <译稿.pdf> <工作区> <输出目录>
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "pdf-translate-zh", "scripts"))
import bootstrap  # noqa: E402
bootstrap.ensure(quiet=True)
try:
    import pymupdf as fitz  # noqa: E402
except ImportError:
    import fitz  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import fontkit  # noqa: E402

BG = (246, 247, 249)
INK = (30, 34, 40)
ACC = (74, 111, 181)


def font(size, bold=True):
    return fontkit.pil("zh-bold" if bold else "zh", size)


def page_img(pdf, pno, dpi=110, clip=None):
    with fitz.open(pdf) as d:
        pg = d[pno]
        pix = pg.get_pixmap(dpi=dpi, clip=clip)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def framed(im, title, pad=18, head=46):
    out = Image.new("RGB", (im.width + 2 * pad, im.height + head + pad), BG)
    d = ImageDraw.Draw(out)
    d.text((pad, 10), title, font=font(24), fill=ACC)
    out.paste(im, (pad, head))
    d.rectangle([pad - 1, head - 1, pad + im.width, head + im.height], outline=(200, 204, 210), width=1)
    return out


def row(items, gap=8, arrow=True):
    h = max(i.height for i in items)
    aw = 56 if arrow else 0
    w = sum(i.width for i in items) + (len(items) - 1) * (gap + aw)
    out = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(out)
    x = 0
    for k, i in enumerate(items):
        out.paste(i, (x, 0))
        x += i.width
        if k < len(items) - 1:
            if arrow:
                cy = h // 2
                d.polygon([(x + gap + 10, cy - 18), (x + gap + 44, cy), (x + gap + 10, cy + 18)], fill=ACC)
            x += gap + aw
    return out


def banner(im, text):
    out = Image.new("RGB", (im.width, im.height + 64), BG)
    d = ImageDraw.Draw(out)
    d.text((18, 14), text, font=font(30), fill=INK)
    out.paste(im, (0, 64))
    return out


def fit_w(im, w):
    return im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)


def main(src, out_pdf, work, dst):
    os.makedirs(dst, exist_ok=True)
    fs, ff = os.path.join(work, "figures_src"), os.path.join(work, "figures")

    # 1. 整页：原版第 8 页 → 译版第 5 页
    a = framed(fit_w(page_img(src, 7), 700), "原版（英文，插图约 97 dpi）")
    b = framed(fit_w(page_img(out_pdf, 4), 700), "译版（中文，出版级重排）")
    banner(row([a, b]), "整页对比：语义重排 · 插图超分 · 图内文字译出 · 步骤与插图不分离").save(
        os.path.join(dst, "01_pages.png"))

    # 2. 超分 + 件号气泡重绘：爆炸图右上局部
    box_hi = (1180, 0, 2040, 520)
    lo = Image.open(os.path.join(fs, "x25.png")).convert("RGB")
    s = lo.width / 2040.0
    crop_lo = lo.crop(tuple(int(v * s) for v in box_hi)).resize((box_hi[2] - box_hi[0], box_hi[3] - box_hi[1]),
                                                                 Image.BICUBIC)
    crop_hi = Image.open(os.path.join(ff, "x25.png")).convert("RGB").crop(box_hi)
    a = framed(fit_w(crop_lo, 640), "原图放大：85 dpi，气泡 07/08/09 发虚")
    b = framed(fit_w(crop_hi, 640), "超分 4 倍 + 件号气泡原位重绘 + 标注译出")
    banner(row([a, b]), "插图复原：Real-ESRGAN 超分 · 件号气泡按零件表判读后重绘").save(
        os.path.join(dst, "02_sr_bubbles.png"))

    # 3. 图内烧死英文 → 中文
    pairs = []
    for stem, t in (("x33", "Subassembly / Push"), ("x28", "Convex face up, stack in series"), ("x36", "Side Fill Port / Top Vent Port")):
        lo = Image.open(os.path.join(fs, stem + ".png")).convert("RGB")
        lo = lo.resize((lo.width * 4, lo.height * 4), Image.BICUBIC)
        hi = Image.open(os.path.join(ff, stem + ".png")).convert("RGB")
        pairs.append(row([framed(fit_w(lo, 620), "原图：" + t), framed(fit_w(hi, 620), "译图")]))
    w = max(p.width for p in pairs)
    col = Image.new("RGB", (w, sum(p.height + 10 for p in pairs)), BG)
    y = 0
    for p in pairs:
        col.paste(p, (0, y))
        y += p.height + 10
    banner(col, "图内文字：位图里的英文标注检测定位，按原位、原字号层级写入中文").save(
        os.path.join(dst, "03_figure_text.png"))

    # 4. 目录与书签
    a = framed(fit_w(page_img(src, 4, clip=fitz.Rect(40, 30, 572, 330)), 620), "原版目录")
    b = framed(fit_w(page_img(out_pdf, 2, clip=fitz.Rect(40, 14, 555, 330)), 620), "译版目录（自动生成，整行可点跳转）")
    with fitz.open(out_pdf) as d:
        toc = d.get_toc()
    def short(t, n=21):
        return t if len(t) <= n else t[:n - 1] + "…"
    lines = [("    " * (lv - 1)) + short(t) + "  ……  " + str(p) for lv, t, p in toc]
    th = 28
    bm = Image.new("RGB", (620, th * len(lines) + 20), (255, 255, 255))
    dd = ImageDraw.Draw(bm)
    for k, ln in enumerate(lines):
        dd.text((12, 10 + k * th), ln, font=font(17, bold=ln[:1] != " "), fill=INK)
    c = framed(bm, "PDF 书签（章节 + 每个工序步骤）")
    banner(row([a, b, c], arrow=False), "目录与导航：译版页码自动回填 · 点引线对齐 · 跳转链接 · 书签").save(
        os.path.join(dst, "04_toc.png"))

    # 5. 附录 A / B
    with fitz.open(out_pdf) as d:
        n = d.page_count
    a = framed(fit_w(page_img(out_pdf, n - 2), 600), "附录 A　译校勘误说明（另起一页）")
    b = framed(fit_w(page_img(out_pdf, n - 1), 600), "附录 B　中英术语对照表（另起一页）")
    banner(row([a, b], arrow=False), "可追溯：勘误、存疑、版式修复逐条记录；术语双栏对照").save(
        os.path.join(dst, "05_appendix.png"))

    # 6. 全册缩览
    with fitz.open(out_pdf) as d:
        ims = []
        for pg in d:
            pix = pg.get_pixmap(dpi=42)
            ims.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    cols = 5
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 10) + 10, rows * (h + 10) + 10), BG)
    for k, im in enumerate(ims):
        sheet.paste(im, (10 + (k % cols) * (w + 10), 10 + (k // cols) * (h + 10)))
    banner(sheet, "全册缩览：封面 · 前置页 · 目录 · 四章工序 · 附录 A/B").save(os.path.join(dst, "06_all_pages.png"))
    print("对比图已写入", dst)


if __name__ == "__main__":
    main(*sys.argv[1:5])
