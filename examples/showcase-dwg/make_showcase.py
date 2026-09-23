# -*- coding: utf-8 -*-
"""生成 README「效果展示 · 工程图纸」用的前后对比图（docs/showcase/07_*.png、08_*.png）。

    python make_showcase.py <源.pdf> <译稿.pdf> <输出目录>
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
        pix = d[pno].get_pixmap(dpi=dpi, clip=clip)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def framed(im, title, pad=18, head=46):
    out = Image.new("RGB", (im.width + 2 * pad, im.height + head + pad), BG)
    d = ImageDraw.Draw(out)
    d.text((pad, 10), title, font=font(24), fill=ACC)
    out.paste(im, (pad, head))
    d.rectangle([pad - 1, head - 1, pad + im.width, head + im.height], outline=(200, 204, 210), width=1)
    return out


def row(items, gap=8):
    h = max(i.height for i in items)
    aw = 56
    w = sum(i.width for i in items) + (len(items) - 1) * (gap + aw)
    out = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(out)
    x = 0
    for k, i in enumerate(items):
        out.paste(i, (x, 0))
        x += i.width
        if k < len(items) - 1:
            cy = h // 2
            d.polygon([(x + gap + 10, cy - 18), (x + gap + 44, cy), (x + gap + 10, cy + 18)], fill=ACC)
            x += gap + aw
    return out


def col(items, gap=12):
    w = max(i.width for i in items)
    out = Image.new("RGB", (w, sum(i.height for i in items) + gap * (len(items) - 1)), BG)
    y = 0
    for i in items:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def banner(im, text):
    out = Image.new("RGB", (im.width, im.height + 64), BG)
    ImageDraw.Draw(out).text((18, 14), text, font=font(30), fill=INK)
    out.paste(im, (0, 64))
    return out


def fit_w(im, w):
    return im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)


def pair(src, out, pno, clip, w, t_en, t_zh, dpi=220):
    a = framed(fit_w(page_img(src, pno, dpi, clip), w), t_en)
    b = framed(fit_w(page_img(out, pno, dpi, clip), w), t_zh)
    return row([a, b])


def main(src, out, dst):
    os.makedirs(dst, exist_ok=True)
    # 7. 整张图纸：第 3 张
    a = framed(fit_w(page_img(src, 2, 150), 1000), "原图（英文，第 3 张）")
    b = framed(fit_w(page_img(out, 2, 150), 1000), "译图（中文，只换字、不动线）")
    banner(row([a, b]), "工程图纸：原页保位叠印 —— 剖面线、尺寸线、件号气泡与引线全部保持原始矢量").save(
        os.path.join(dst, "07_dwg_sheet.png"))

    # 8. 局部：标题栏注记格 / 明细表合并格 / 引线标注与局部详图
    parts = [
        pair(src, out, 0, fitz.Rect(710, 604, 1190, 758), 760,
             "标题栏：± ° ∨ 是矢量、小数点靠空格对齐", "整格标准重排：整句译出，公差逐图解析"),
        pair(src, out, 2, fitz.Rect(36, 580, 704, 744), 760,
             "明细表：件号 2 纵向合并三种可选件", "真网格重建：合并格保留，重影文字去重，误引件号勘正"),
        pair(src, out, 2, fitz.Rect(430, 96, 1060, 470), 760,
             "引线标注、扭矩值、局部详图", "扭矩值与螺纹代号保留，说明文字原位译出"),
        pair(src, out, 1, fitz.Rect(820, 205, 1150, 400), 760,
             "竖排尺寸 Ø4.25 SPRING BORE", "旋转文字按原方向写回"),
    ]
    banner(col(parts), "图纸细节：注记格重排 · 明细表重建 · 引线标注 · 竖排文字").save(
        os.path.join(dst, "08_dwg_details.png"))
    print("对比图已写入", dst)


if __name__ == "__main__":
    main(*sys.argv[1:4])
