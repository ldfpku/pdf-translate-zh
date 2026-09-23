# -*- coding: utf-8 -*-
"""位图内烧死英文的定位与汉化（SKILL 避坑 ㉑）。

矢量英文可以 redaction，位图里的抹不掉也提取不到 —— 文本层根本没有它，
首版必然漏译且自检查不出来。系统排查法：「与嵌入位图相交 且 矢量标注数为 0」
的插图是唯一可能藏有位图英文的地方。

本模块两个用途
  boxes()   按颜色找出候选文字块，报告**相对坐标**（不依赖具体 dpi）；
            工程图的标注常与引线同色，故一并报告长宽比与填充率，
            细长者是引线/尺寸线，须排除，绝不可连引线一起抹掉。
  redraw()  按相对矩形铺底色后写中文，字号自适配框宽（下限 4.6pt 等效）。

纯数值＋单位（3000 psi）与尺寸字母保留不译。
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import fontkit

ZH_FONT = fontkit.find("zh-bold")


def _mask_red(a, sat=110, hi=110, gb_max=115):
    """标注红（约 220,30,30）与鲑肉色零件体（约 240,150,120）必须分开。

    只用「r-g / r-b 差值」不够：鲑肉色的 r-g 已达 90。必须同时要求
    g、b 本身足够低 —— 否则整个零件体都会被当成标注红，
    抹除时把插图主体一并铺白。
    """
    r, g, b = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)
    return ((r > hi) & (r - g > sat) & (r - b > sat)
            & (g < gb_max) & (b < gb_max))


def _mask_dark(a, thr=110):
    return a.min(axis=2) < thr


MASKS = {"red": _mask_red, "dark": _mask_dark}


def boxes(path, kind="red", gap=14, min_px=40):
    """找出同色像素簇。返回 [(rel_rect, 绝对像素框, 像素数, 长宽比)]。

    gap 为簇间允许的空隙（像素）：文字行内字距小、行距略大，
    取 14 能把一行合成一块而不把两行并成一块。
    """
    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    H, W = a.shape[:2]
    m = MASKS[kind](a)
    if not m.any():
        return []

    # 逐行/逐列投影做粗聚类：工程图标注块之间留白充足，投影法足够且极快
    def runs(v, g):
        idx = np.where(v)[0]
        if not len(idx):
            return []
        out, s, p = [], idx[0], idx[0]
        for i in idx[1:]:
            if i - p > g:
                out.append((s, p))
                s = i
            p = i
        out.append((s, p))
        return out

    res = []
    for by0, by1 in runs(m.any(axis=1), gap):
        band = m[by0:by1 + 1]
        for x0, x1 in runs(band.any(axis=0), gap):
            sub = band[:, x0:x1 + 1]
            n = int(sub.sum())
            if n < min_px:
                continue
            # 收紧到该簇自身的真实上下界：行带是全幅投影得来的，
            # 同一行带里既有标注文字又有尺寸引线时，直接用带边界会把
            # 抹除框撑到引线的高度，铺白时连引线一起抹掉。
            rows = np.where(sub.any(axis=1))[0]
            y0, y1 = by0 + int(rows[0]), by0 + int(rows[-1])
            w, h = x1 - x0 + 1, y1 - y0 + 1
            res.append(dict(
                rel=(round(x0 / W, 4), round(y0 / H, 4),
                     round((x1 + 1) / W, 4), round((y1 + 1) / H, 4)),
                px=(int(x0), int(y0), int(x1 + 1), int(y1 + 1)),
                n=n, ar=round(w / max(h, 1), 2),
                fill=round(n / float(w * h), 3), wh=(int(w), int(h))))
    return res


def group(bs, gap_x=40, gap_y=18):
    """把同一条标注的分词簇合并成一个抹除框（「Pin」「and」「Box」→ 一块）。"""
    out = []
    for b in sorted(bs, key=lambda z: (z["px"][1], z["px"][0])):
        x0, y0, x1, y1 = b["px"]
        for o in out:
            ox0, oy0, ox1, oy1 = o["px"]
            if (x0 - ox1 <= gap_x and ox0 - x1 <= gap_x
                    and y0 - oy1 <= gap_y and oy0 - y1 <= gap_y):
                o["px"] = (min(ox0, x0), min(oy0, y0), max(ox1, x1), max(oy1, y1))
                o["n"] += b["n"]
                break
        else:
            out.append(dict(px=(x0, y0, x1, y1), n=b["n"]))
    return out


def report(path, kind="red", grouped=True, **kw):
    im = Image.open(path)
    W, H = im.width, im.height
    print(f"{os.path.basename(path)}  {W}x{H}px")
    bs = boxes(path, kind, **kw)
    for i, b in enumerate(bs, 1):
        ar = b["ar"]
        tag = ""
        if ar > 8 or ar < 0.15:      # 极扁或极瘦 = 引线/尺寸线，绝不可抹
            tag = "  ← 细长：引线/尺寸线，勿抹"
        elif b["fill"] > 0.12:
            tag = "  ← 疑为文字"
        print(f"  #{i} px={b['px']} {b['wh'][0]}x{b['wh'][1]} "
              f"n={b['n']} 长宽比={ar} 填充率={b['fill']}{tag}")
    if grouped:
        cand = [b for b in bs if 0.15 <= b["ar"] <= 8 and b["fill"] > 0.12]
        print("  -- 合并后的候选文字块（rel 坐标，可直接填 RASTER_ZH）--")
        for g in group(cand):
            x0, y0, x1, y1 = g["px"]
            print(f"     rel=({x0/W:.4f}, {y0/H:.4f}, {x1/W:.4f}, {y1/H:.4f})"
                  f"   px={g['px']}  {x1-x0}x{y1-y0}")


def _bg_color(a, px, pad=6):
    """取矩形外侧一圈的众数色作底色（多为纯白，但相片类可能不是）。"""
    x0, y0, x1, y1 = px
    H, W = a.shape[:2]
    ring = []
    for yy in range(max(0, y0 - pad), min(H, y1 + pad)):
        for xx in (max(0, x0 - pad), min(W - 1, x1 + pad - 1)):
            ring.append(tuple(a[yy, xx]))
    for xx in range(max(0, x0 - pad), min(W, x1 + pad)):
        for yy in (max(0, y0 - pad), min(H - 1, y1 + pad - 1)):
            ring.append(tuple(a[yy, xx]))
    if not ring:
        return (255, 255, 255)
    vals, cnt = np.unique(np.array(ring), axis=0, return_counts=True)
    return tuple(int(v) for v in vals[cnt.argmax()])


def redraw(src, dst, items, color=(210, 30, 30), align="left", pad_px=2):
    """items: [(rel_rect, 中文[, 对齐])]，对齐缺省取 align 参数。

    rel_rect 用相对坐标，故换 dpi 重渲后无需改动。
    多行用 <br/> 分隔。字号按框宽自适配。
    """
    im = Image.open(src).convert("RGB")
    a = np.asarray(im).copy()
    W, H = im.width, im.height
    d = ImageDraw.Draw(im)

    # 第一趟：全部铺底。逐条「铺底→写字」会让后一条的底色盖掉前一条的字脚
    # （SKILL ⑮ 同理）。
    px_list = []
    for it in items:
        rel, text = it[0], it[1]
        al = it[2] if len(it) > 2 else align
        x0, y0, x1, y1 = (int(rel[0] * W), int(rel[1] * H),
                          int(rel[2] * W), int(rel[3] * H))
        bx = (x0 - pad_px, y0 - pad_px, x1 + pad_px, y1 + pad_px)
        bg = _bg_color(a, (x0, y0, x1, y1))
        d.rectangle(bx, fill=bg)
        px_list.append(((x0, y0, x1, y1), text, al))

    # 第二趟：写字
    for (x0, y0, x1, y1), text, align in px_list:
        lines = text.split("<br/>") if isinstance(text, str) else list(text)
        bw, bh = x1 - x0, y1 - y0
        size = max(8, int(bh / max(len(lines), 1) * 0.86))
        while size > 8:
            f = ImageFont.truetype(ZH_FONT, size)
            wmax = max(d.textlength(s, font=f) for s in lines)
            if wmax <= bw and size * 1.18 * len(lines) <= bh * 1.08:
                break
            size -= 1
        f = ImageFont.truetype(ZH_FONT, size)
        lh = size * 1.18
        for i, s in enumerate(lines):
            tw = d.textlength(s, font=f)
            tx = x0 if align == "left" else x0 + (bw - tw) / 2.0
            d.text((tx, y0 + i * lh), s, font=f, fill=color)

    im.save(dst)
    return dst
