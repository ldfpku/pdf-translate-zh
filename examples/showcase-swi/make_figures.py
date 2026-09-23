# -*- coding: utf-8 -*-
"""虚构展示文档的插图：程序化「CAD 渲染」零件 + 件号气泡 + 图内英文标注，再**故意降质**。

真实手册里常见的难题在这里一次复刻：
  · 系统导出只有约 85 dpi（510 px 放在 430 pt 宽），放大即糊，气泡里 "09" 像 "C9"；
  · 标注（DETAIL B、Subassembly、Side Fill Port …）烧死在位图里，文本层没有；
  · 局部放大圆、引线、相邻气泡。
全部图形由本脚本原创绘制（Tethys Downhole Tools 为虚构品牌）。

    python make_figures.py <输出目录>        # 生成 figs/*.jpg（降质版）与 figs_hi/*.png（未降质，仅供对照）
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "pdf-translate-zh", "scripts"))
import fontkit  # noqa: E402

FONT_B = fontkit.find("latin-bold", required=False) or fontkit.find("zh-bold")
W_HI = 2040          # 高清作画宽度（px）
W_LO = 510           # 降质后宽度：放在 430 pt 宽 ≈ 85 dpi

OLIVE = (122, 128, 70)
STEEL = (150, 156, 164)
BLUE = (40, 90, 200)
YELLOW = (225, 200, 40)
ORANGE = (230, 140, 40)
TEAL = (40, 180, 180)
PURPLE = (190, 60, 190)
DARK = (70, 72, 78)


def font(px):
    return ImageFont.truetype(FONT_B, px)


def shade(rgb, k):
    return tuple(int(max(0, min(255, c * k))) for c in rgb)


def cylinder(im, x0, x1, yc, r, rgb, cap=True):
    """横放圆柱：竖向朗伯明暗 + 高光带 + 右端椭圆端面。"""
    a = np.asarray(im).copy()
    H, W = a.shape[:2]
    y0, y1 = int(yc - r), int(yc + r)
    for y in range(max(0, y0), min(H, y1 + 1)):
        t = (y - yc) / float(r)
        if abs(t) > 1:
            continue
        n = math.sqrt(1 - t * t)
        k = 0.35 + 0.75 * n + 0.35 * math.exp(-((t + 0.45) ** 2) / 0.02)
        a[y, max(0, int(x0)):min(W, int(x1))] = shade(rgb, k)
    im.paste(Image.fromarray(a))
    d = ImageDraw.Draw(im)
    if cap:
        e = r * 0.32
        d.ellipse([x1 - e, yc - r, x1 + e, yc + r], fill=shade(rgb, 1.15), outline=shade(rgb, 0.5), width=2)
    d.line([x0, yc - r, x1, yc - r], fill=shade(rgb, 0.45), width=2)
    d.line([x0, yc + r, x1, yc + r], fill=shade(rgb, 0.4), width=2)


def ring(im, xc, yc, r, width, rgb, hole=0.6):
    """套在轴上的环（端面朝右）：短圆柱 + 带孔端面。"""
    cylinder(im, xc - width / 2, xc + width / 2, yc, r, rgb, cap=False)
    d = ImageDraw.Draw(im)
    e = r * 0.32
    x1 = xc + width / 2
    d.ellipse([x1 - e, yc - r, x1 + e, yc + r], fill=shade(rgb, 1.12), outline=shade(rgb, 0.5), width=2)
    d.ellipse([x1 - e * hole, yc - r * hole, x1 + e * hole, yc + r * hole], fill=shade(rgb, 0.45))


def threads(im, x0, x1, yc, r, step=14):
    d = ImageDraw.Draw(im)
    for x in range(int(x0), int(x1), step):
        d.line([x, yc - r + 3, x + step * 0.6, yc + r - 3], fill=(60, 60, 60), width=2)


def bubble(im, x, y, text, target=None, r=46):
    """件号气泡：粗圆环 + 编号 + 引线（先画引线再画环，环内填白）。"""
    d = ImageDraw.Draw(im)
    if target:
        ang = math.atan2(target[1] - y, target[0] - x)
        d.line([x + r * math.cos(ang), y + r * math.sin(ang), target[0], target[1]], fill=(20, 20, 20), width=5)
        d.ellipse([target[0] - 7, target[1] - 7, target[0] + 7, target[1] + 7], fill=(20, 20, 20))
    d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255), outline=(20, 20, 20), width=6)
    f = font(int(r * 0.95))
    bb = d.textbbox((0, 0), text, font=f)
    d.text((x - (bb[2] - bb[0]) / 2 - bb[0], y - (bb[3] - bb[1]) / 2 - bb[1]), text, font=f, fill=(20, 20, 20))


def label(im, x, y, text, px=44, anchor="la"):
    d = ImageDraw.Draw(im)
    d.multiline_text((x, y), text, font=font(px), fill=(25, 25, 25), anchor=anchor, spacing=10)


def detail_circle(im, src_xy, src_r, dst_xy, dst_r, zoom=2.6, color=(220, 50, 60)):
    """局部放大圆：把 src 区域放大贴进 dst 圆，红圈 + 连接线。"""
    sx, sy = src_xy
    crop = im.crop((int(sx - src_r), int(sy - src_r), int(sx + src_r), int(sy + src_r)))
    big = crop.resize((int(2 * dst_r), int(2 * dst_r)), Image.LANCZOS)
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, big.size[0] - 1, big.size[1] - 1], fill=255)
    d = ImageDraw.Draw(im)
    dx, dy = dst_xy
    d.line([sx, sy, dx, dy], fill=color, width=5)
    im.paste(big, (int(dx - dst_r), int(dy - dst_r)), mask)
    d.ellipse([dx - dst_r, dy - dst_r, dx + dst_r, dy + dst_r], outline=color, width=8)
    d.ellipse([sx - src_r, sy - src_r, sx + src_r, sy + src_r], outline=color, width=6)


def canvas(h):
    return Image.new("RGB", (W_HI, h), (255, 255, 255))


# ---------------------------------------------------------------- 各幅插图
def fig_exploded():
    """爆炸图：芯轴 + 各零件沿轴线排开，12 个件号气泡，剖视/局部详图标签。"""
    im = canvas(1100)
    yc = 620
    cylinder(im, 120, 1900, yc, 70, OLIVE)                        # 01 芯轴
    threads(im, 1760, 1900, yc, 70)
    ring(im, 330, yc, 150, 120, STEEL)                            # 02 壳体端
    for i in range(8):                                            # 03 碟形弹簧组
        ring(im, 560 + i * 34, yc, 118 - (i % 2) * 18, 22, YELLOW, hole=0.72)
    ring(im, 930, yc, 110, 70, ORANGE)                            # 04 花键套
    ring(im, 1080, yc, 96, 26, TEAL, hole=0.78)                   # 05 防尘圈
    ring(im, 1210, yc, 104, 90, BLUE)                             # 06 密封座
    ring(im, 1350, yc, 92, 18, PURPLE, hole=0.8)                  # 07 O 形圈
    ring(im, 1420, yc, 92, 18, (60, 60, 60), hole=0.8)            # 08 挡圈
    ring(im, 1550, yc, 112, 60, STEEL)                            # 09 推力轴承
    ring(im, 1690, yc, 100, 50, DARK)                             # 10 锁紧螺母
    items = [("01", (200, 400), (220, yc - 60)), ("02", (330, 330), (330, yc - 150)),
             ("03", (640, 380), (640, yc - 118)), ("04", (930, 380), (930, yc - 110)),
             ("05", (1080, 880), (1080, yc + 96)), ("06", (1210, 880), (1210, yc + 104)),
             ("07", (1340, 400), (1350, yc - 92)), ("08", (1440, 880), (1420, yc + 92)),
             ("09", (1550, 380), (1550, yc - 112)), ("10", (1700, 880), (1690, yc + 100))]
    for t, p, tgt in items:
        bubble(im, p[0], p[1], t, tgt)
    detail_circle(im, (1385, yc - 70), 70, (1780, 230), 170)
    bubble(im, 1600, 150, "07", (1700, 200), r=40)
    bubble(im, 1960, 360, "08", (1880, 320), r=40)
    label(im, 60, 60, "SECTION A-A")
    label(im, 1640, 440, "DETAIL B")
    label(im, 60, 1000, "Mandrel stack, exploded view", px=38)
    return im


def fig_mandrel_clamp():
    im = canvas(620)
    yc = 360
    cylinder(im, 180, 1850, yc, 80, OLIVE)
    threads(im, 1700, 1850, yc, 80)
    d = ImageDraw.Draw(im)
    for x in (420, 1500):                                        # 夹具 V 形块
        d.polygon([(x - 90, yc + 150), (x + 90, yc + 150), (x + 40, yc + 70), (x - 40, yc + 70)], fill=(90, 90, 96))
    bubble(im, 900, 120, "01", (900, yc - 80))
    label(im, 640, 470, "Soft-jaw vise", px=42)
    return im


def fig_springs():
    im = canvas(760)
    yc = 470
    cylinder(im, 150, 1880, yc, 70, OLIVE)
    for i in range(8):
        ring(im, 700 + i * 40, yc, 125 - (i % 2) * 20, 24, YELLOW, hole=0.72)
    bubble(im, 360, 180, "01", (400, yc - 70))
    bubble(im, 860, 150, "03", (820, yc - 125))
    detail_circle(im, (760, yc - 100), 60, (1520, 220), 160)
    label(im, 1150, 590, "Convex face up,\nstack in series", px=40)
    return im


def fig_spline_sleeve():
    im = canvas(700)
    yc = 420
    cylinder(im, 150, 1880, yc, 70, OLIVE)
    ring(im, 1000, yc, 115, 260, ORANGE)
    d = ImageDraw.Draw(im)
    for k in range(6):                                            # 花键齿示意
        x = 900 + k * 40
        d.line([x, yc - 112, x, yc + 112], fill=shade(ORANGE, 0.55), width=4)
    bubble(im, 600, 150, "01", (620, yc - 70))
    bubble(im, 1000, 130, "04", (1000, yc - 115))
    label(im, 1240, 560, "Align spline keys", px=42)
    return im


def fig_seal_carrier():
    im = canvas(760)
    yc = 470
    cylinder(im, 150, 1880, yc, 70, OLIVE)
    ring(im, 1000, yc, 110, 110, BLUE)
    ring(im, 1110, yc, 100, 20, PURPLE, hole=0.82)
    ring(im, 1150, yc, 100, 20, (60, 60, 60), hole=0.82)
    ring(im, 870, yc, 102, 28, TEAL, hole=0.8)
    bubble(im, 870, 170, "05", (870, yc - 102))
    bubble(im, 1000, 150, "06", (1000, yc - 110))
    bubble(im, 1180, 180, "07", (1110, yc - 100), r=42)
    bubble(im, 1330, 280, "08", (1160, yc - 95), r=42)
    detail_circle(im, (1130, yc + 80), 60, (1620, 560), 150)
    label(im, 1500, 150, "Back-up ring on\nlow-pressure side", px=38)
    return im


def fig_housing_install():
    im = canvas(640)
    yc = 330
    cylinder(im, 80, 1400, yc, 120, STEEL)                        # 壳体
    cylinder(im, 1100, 1960, yc, 70, OLIVE)                       # 子总成
    ring(im, 1250, yc, 112, 90, BLUE)
    d = ImageDraw.Draw(im)
    d.rectangle([1140, yc - 60, 1330, yc + 60], outline=(230, 190, 0), width=8)
    label(im, 1180, 470, "Subassembly", px=44)
    bubble(im, 500, 110, "02", (500, yc - 120))
    d.line([1000, 540, 700, 540], fill=(20, 20, 20), width=6)
    d.polygon([(700, 520), (660, 540), (700, 560)], fill=(20, 20, 20))
    label(im, 780, 560, "Push", px=40)
    return im


def fig_grease_ports():
    im = canvas(680)
    yc = 380
    cylinder(im, 120, 1920, yc, 130, STEEL)
    d = ImageDraw.Draw(im)
    for x, y in ((700, yc + 60), (1350, yc - 128)):
        d.ellipse([x - 26, y - 14, x + 26, y + 14], fill=(40, 40, 40))
    label(im, 460, 560, "Side Fill Port", px=42)
    d.line([640, 555, 700, yc + 74], fill=(20, 20, 20), width=5)
    label(im, 1480, 110, "Top Vent Port", px=42)
    d.line([1490, 160, 1370, yc - 140], fill=(20, 20, 20), width=5)
    bubble(im, 1000, 610, "02", (1000, yc + 130))
    bubble(im, 1700, 610, "12", (1750, yc + 125), r=44)
    return im


def fig_locknut():
    im = canvas(640)
    yc = 360
    cylinder(im, 150, 1500, yc, 120, STEEL)
    cylinder(im, 1500, 1900, yc, 70, OLIVE)
    threads(im, 1560, 1900, yc, 70)
    ring(im, 1620, yc, 100, 70, DARK)
    bubble(im, 1620, 120, "10", (1620, yc - 100))
    bubble(im, 1860, 560, "11", (1700, yc + 60), r=44)
    label(im, 300, 540, "Torque per Table 3-1", px=44)
    return im


def ppe_icons():
    """PPE 图标栏：五枚蓝底白图形图标（护目镜、手套、安全鞋、安全帽、耳罩）。"""
    s = 160
    im = Image.new("RGB", (5 * s + 4 * 20, s), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for k in range(5):
        x = k * (s + 20)
        d.ellipse([x, 0, x + s, s], fill=(30, 110, 190))
        c = (255, 255, 255)
        if k == 0:
            d.ellipse([x + 30, 60, x + 75, 100], outline=c, width=8)
            d.ellipse([x + 85, 60, x + 130, 100], outline=c, width=8)
            d.line([x + 75, 78, x + 85, 78], fill=c, width=8)
        elif k == 1:
            d.rounded_rectangle([x + 55, 45, x + 105, 125], 18, fill=c)
            d.rectangle([x + 45, 30, x + 60, 80], fill=c)
        elif k == 2:
            d.polygon([(x + 45, 40), (x + 80, 40), (x + 80, 95), (x + 125, 105), (x + 125, 125), (x + 45, 125)], fill=c)
        elif k == 3:
            d.pieslice([x + 30, 40, x + 130, 140], 180, 360, fill=c)
            d.rectangle([x + 25, 88, x + 135, 100], fill=c)
        else:
            d.arc([x + 40, 35, x + 120, 115], 180, 360, fill=c, width=10)
            d.rounded_rectangle([x + 30, 75, x + 55, 120], 8, fill=c)
            d.rounded_rectangle([x + 105, 75, x + 130, 120], 8, fill=c)
    return im


FIGS = {
    "fig_exploded": fig_exploded, "fig_clamp": fig_mandrel_clamp, "fig_springs": fig_springs,
    "fig_sleeve": fig_spline_sleeve, "fig_seal": fig_seal_carrier, "fig_housing": fig_housing_install,
    "fig_ports": fig_grease_ports, "fig_locknut": fig_locknut,
}


def degrade(im, width=W_LO, q=55):
    """系统导出式降质：盒式下采样 + 轻微模糊 + 低质量 JPEG。"""
    h = int(im.height * width / im.width)
    lo = im.resize((width, h), Image.BOX).filter(ImageFilter.GaussianBlur(0.55))
    return lo, q


def main(out):
    lo_dir, hi_dir = os.path.join(out, "figs"), os.path.join(out, "figs_hi")
    os.makedirs(lo_dir, exist_ok=True)
    os.makedirs(hi_dir, exist_ok=True)
    for name, fn in FIGS.items():
        im = fn()
        im.save(os.path.join(hi_dir, name + ".png"))
        lo, q = degrade(im)
        lo.save(os.path.join(lo_dir, name + ".jpg"), quality=q)
    ppe = ppe_icons()
    ppe.save(os.path.join(hi_dir, "ppe.png"))
    lo = ppe.resize((ppe.width // 4, ppe.height // 4), Image.BOX)
    lo.save(os.path.join(lo_dir, "ppe.jpg"), quality=60)
    return lo_dir


if __name__ == "__main__":
    print(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build")))
