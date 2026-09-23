# -*- coding: utf-8 -*-
"""件号气泡（callout：圆/椭圆环 + 编号 + 引线）的判读对账、统一重绘与残留判据（figures.md §17）。

低分辨率原图放大后气泡里的数字发虚、用户读不准（"09" 像 "C9"）。处置不是描白重写文字，而是
**在原环心位置重绘整个气泡**：擦旧环 → 补引线短截 → 画新环 → Arial Bold 编号。判读结果由内容层给
（{stem: {框号: "09" | "ST02"}}），判读须与步骤文字/零件表逐一对账，依据与存疑写进附录 A 乙。

    geo, rect = redraw(im, draw, box, "09", like=None)      # box = 检测到的编号框（像素）
    bad = residue_check(im, geo, others=[其它气泡 geo])      # 必须为空
    sheet(figdir, BUBBLES, boxes, out_png)                   # 全部气泡放大拼贴，交付前目检

几何三法（取与旧环吻合度最高者）：
  · 填洞法 `ring_by_holes`：环是闭合暗线，binary_fill_holes 后减暗像素即内腔，含编号框的内腔 bbox = 内椭圆；
    与引线是否相连无关（首选）。⚠ 编号框可能只是数字（内腔比框大），也可能是整个气泡连引线（内腔比框小，
    框中心偏离环心 15 px）—— 尺寸判据两头都要放行，环心不能取框中心；
  · 射线法 `ring_by_rays`：自**编号框边界**起算的 72 条射线找内/外沿，椭圆模型验证（≥75% 射线残差 ≤15%）。
    ⚠ 起点不能取半对角线：椭圆气泡（ST01/T01）竖向内半径小于半对角线，竖向射线会跳过环抓到远处物体；
  · 模板搜索 `template_center`：同图同规格气泡的半径 + 环路径墨迹密度搜索环心（受限 Hough），
    用于图边缘/紧贴虚线框而前两法失败的气泡。
擦除：每 5° 实测外沿 +2 px 的多边形 ∪ 拟合椭圆 +3 px（旧环偏心/毛边全盖住）；引线在环外 +7/+12 px
两圈同时为暗的角簇，擦后补画 rout−1 → rout+5 的短截。环厚**四向取最小**并封顶 0.3×内半径（引线方向
会把厚度拉长 —— 实测 "03" 画成实心黑盘）。
残留判据 `residue_check`：新环外 +4/+8 px 两圈上，扣除引线角簇（±12°）与相邻气泡椭圆内的点，
连续 ≥3 个采样角（≥15°）的暗弧即旧环残留。用户目测"旧序号露一截"= 新环与旧环没对齐，判据全书跑、不点名修。
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

import fontkit

# 编号用西文粗体（Arial Bold 或同度量的 Liberation Sans Bold）；都没有时退回中文粗体
FONT_NUM = fontkit.find("latin-bold", required=False) or fontkit.find("zh-bold")


def ellipse_samples(g, cx, cy, rx, ry, step=5):
    out = {}
    H, W = g.shape
    for deg in range(0, 360, step):
        th = np.deg2rad(deg)
        px, py = int(round(cx + rx * np.cos(th))), int(round(cy + ry * np.sin(th)))
        if 0 <= px < W and 0 <= py < H:
            out[deg] = int(g[py, px])
    return out


def ring_by_holes(g, box, dark=120, bright=200):
    x0, y0, x1, y1 = [int(v) for v in box]
    hw, hh = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    R = int(max(hw, hh) * 5 + 60)
    X0, Y0 = max(0, int(cx - R)), max(0, int(cy - R))
    X1, Y1 = min(g.shape[1], int(cx + R)), min(g.shape[0], int(cy + R))
    sub = g[Y0:Y1, X0:X1]
    dk = sub < dark
    interior = ndimage.binary_fill_holes(dk) & ~dk
    lbl, n = ndimage.label(interior)
    if n == 0:
        return None
    samples = [(cy, cx), (cy, cx - hw * 0.6), (cy, cx + hw * 0.6), (cy - hh - 3, cx), (cy + hh + 3, cx),
               (cy, cx - hw - 3), (cy, cx + hw + 3)]
    best = None
    for sy, sx in samples:
        iy, ix = int(round(sy - Y0)), int(round(sx - X0))
        if not (0 <= iy < lbl.shape[0] and 0 <= ix < lbl.shape[1]):
            continue
        k = lbl[iy, ix]
        if k == 0:
            continue
        yy, xx = np.where(lbl == k)
        bx0, bx1, by0, by1 = int(xx.min()), int(xx.max()) + 1, int(yy.min()), int(yy.max()) + 1
        w, h = bx1 - bx0, by1 - by0
        if w < 16 or h < 12 or w > 3 * (2 * hw + 10) or h > 3 * (2 * hh + 10):
            continue
        inside = lambda px, py: bx0 + X0 <= px <= bx1 + X0 and by0 + Y0 <= py <= by1 + Y0
        if not inside(cx, cy) and not inside(sx, sy):
            continue
        if best is None or w * h > best[0]:
            best = (w * h, bx0 + X0, by0 + Y0, bx1 + X0, by1 + Y0)
    if best is None:
        return None
    _, ix0, iy0, ix1, iy1 = best
    ncx, ncy = (ix0 + ix1) / 2.0, (iy0 + iy1) / 2.0
    a_in, b_in = (ix1 - ix0) / 2.0, (iy1 - iy0) / 2.0

    def _scan(x, y, dx, dy):
        k = 0
        while 0 <= x < g.shape[1] and 0 <= y < g.shape[0] and g[y, x] < bright and k < 40:
            x += dx
            y += dy
            k += 1
        return k
    cxi, cyi = int(round(ncx)), int(round(ncy))
    ts = [_scan(int(round(ix1)), cyi, 1, 0), _scan(int(round(ix0)) - 1, cyi, -1, 0),
          _scan(cxi, int(round(iy1)), 0, 1), _scan(cxi, int(round(iy0)) - 1, 0, -1)]
    ts = [v for v in ts if v >= 2]
    t = min(min(ts) if ts else 3, 0.3 * min(a_in, b_in))
    rays = {}
    for deg in range(0, 360, 5):
        th = np.deg2rad(deg)
        rin = a_in * b_in / np.sqrt((b_in * np.cos(th)) ** 2 + (a_in * np.sin(th)) ** 2)
        rays[deg] = (rin, rin + t)
    return dict(cx=ncx, cy=ncy, rin_x=a_in, rin_y=b_in, rout_x=a_in + t, rout_y=b_in + t, t=float(t),
                rays=rays, cx0=ncx, cy0=ncy, method="holes")


def ring_by_rays(g, box, dark=120, bright=200):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hw, hh = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    rmax = int(max(hw, hh) * 5 + 60)
    H, W = g.shape
    res = {}
    for deg in range(0, 360, 5):
        th = np.deg2rad(deg)
        dx, dy = np.cos(th), np.sin(th)
        d0 = min(hw / abs(dx) if abs(dx) > 1e-6 else 1e9, hh / abs(dy) if abs(dy) > 1e-6 else 1e9) + 2
        rin = rout = None
        d = d0
        while d < rmax:
            px, py = int(round(cx + d * dx)), int(round(cy + d * dy))
            if not (0 <= px < W and 0 <= py < H):
                break
            v = g[py, px]
            if rin is None:
                if v < dark:
                    rin = d
            elif v > bright:
                rout = d
                break
            d += 1
        if rin is not None and rout is not None:
            res[deg] = (rin, rout)
    if len(res) < 30:
        return None

    def med(keys, idx):
        vals = [res[k][idx] for k in keys if k in res]
        return float(np.median(vals)) if vals else None
    r_r = med([d for d in res if d <= 15 or d >= 345], 0)
    r_l = med([d for d in res if 165 <= d <= 195], 0)
    r_d = med([d for d in res if 75 <= d <= 105], 0)
    r_u = med([d for d in res if 255 <= d <= 285], 0)
    if None in (r_r, r_l, r_d, r_u):
        return None
    ncx, ncy = cx + (r_r - r_l) / 2.0, cy + (r_d - r_u) / 2.0
    a_in, b_in = (r_r + r_l) / 2.0, (r_d + r_u) / 2.0
    good, ths = 0, []
    for deg, (rin, rout) in res.items():
        th = np.deg2rad(deg)
        pred = a_in * b_in / np.sqrt((b_in * np.cos(th)) ** 2 + (a_in * np.sin(th)) ** 2)
        if abs(rin - pred) <= 0.15 * pred + 2:
            good += 1
            ths.append(rout - rin)
    if good < 0.75 * len(res) or not ths:
        return None
    t = float(np.median(ths))
    if t > 0.4 * min(a_in, b_in) or t < 1.5:
        return None
    return dict(cx=ncx, cy=ncy, rin_x=a_in, rin_y=b_in, rout_x=a_in + t, rout_y=b_in + t, t=t,
                rays=dict(res), cx0=cx, cy0=cy, method="rays")


def template_center(g, box, like):
    x0, y0, x1, y1 = box
    a, b_, t = like["rin_x"], like["rin_y"], like["t"]
    ra, rb = a + t / 2.0, b_ + t / 2.0
    ths = np.deg2rad(np.arange(0, 360, 5))
    best, bx, by = -1, (x0 + x1) / 2.0, (y0 + y1) / 2.0
    for yy in range(int(y0 - 6), int(y1 + 7)):
        for xx in range(int(x0 - 6), int(x1 + 7)):
            px = np.clip((xx + ra * np.cos(ths)).round().astype(int), 0, g.shape[1] - 1)
            py = np.clip((yy + rb * np.sin(ths)).round().astype(int), 0, g.shape[0] - 1)
            sc = float((255 - g[py, px]).mean())
            if sc > best:
                best, bx, by = sc, xx, yy
    return dict(cx=float(bx), cy=float(by), rin_x=a, rin_y=b_, rout_x=like["rout_x"], rout_y=like["rout_y"],
                t=t, rays={}, cx0=float(bx), cy0=float(by), method="template", score=best)


def fit_quality(g, geo):
    """环路径上的平均墨迹（高=吻合）+ 环外 +5 px 圈上的暗采样数（引线外应为 0）。"""
    cx, cy = geo["cx"], geo["cy"]
    on = ellipse_samples(g, cx, cy, geo["rin_x"] + geo["t"] / 2.0, geo["rin_y"] + geo["t"] / 2.0)
    on_dark = float(np.mean([255 - v for v in on.values()])) if on else 0.0
    out5 = ellipse_samples(g, cx, cy, geo["rout_x"] + 5, geo["rout_y"] + 5)
    return on_dark, sum(1 for v in out5.values() if v < 130)


def leader_angles(g, geo, dark=130):
    cx, cy, rox, roy = geo["cx"], geo["cy"], geo["rout_x"], geo["rout_y"]
    s1 = ellipse_samples(g, cx, cy, rox + 7, roy + 7)
    s2 = ellipse_samples(g, cx, cy, rox + 12, roy + 12)
    degs = sorted(d for d in s1 if s1[d] < dark and s2.get(d, 255) < dark)
    clusters = []
    for d in degs:
        if clusters and d - clusters[-1][-1] <= 10:
            clusters[-1].append(d)
        else:
            clusters.append([d])
    if len(clusters) > 1 and clusters[0][0] == 0 and clusters[-1][-1] >= 350:
        clusters[0] = clusters[-1] + clusters[0]
        clusters.pop()
    out = []
    for c in clusters:
        base = c[0]
        out.append((float(np.mean([x if x >= base else x + 360 for x in c])) % 360, len(c)))
    return out


def redraw(im, d, box, text, like=None, font=FONT_NUM):
    """返回 (几何字典 或 None, 覆盖矩形)。几何字典含 fit / leaders / method。"""
    g = np.array(im.convert("L"))
    cands = [x for x in (ring_by_holes(g, box), ring_by_rays(g, box)) if x is not None]
    if like is not None:
        cands.append(template_center(g, box, like))
    if not cands:
        return None, None
    scored = sorted(((fq[0] - 12.0 * fq[1], fq, geo) for geo in cands for fq in [fit_quality(g, geo)]),
                    key=lambda s: -s[0])
    _, (on_dark, n_out), geo = scored[0]
    cx, cy, rox, roy, rix, riy, t = (geo["cx"], geo["cy"], geo["rout_x"], geo["rout_y"],
                                    geo["rin_x"], geo["rin_y"], geo["t"])
    leaders = leader_angles(g, geo)
    poly = []
    for deg in range(0, 360, 5):
        th = np.deg2rad(deg)
        if deg in geo.get("rays", {}):
            r = geo["rays"][deg][1] + 2.0
            poly.append((geo["cx0"] + r * np.cos(th), geo["cy0"] + r * np.sin(th)))
        else:
            poly.append((cx + (rox + 3) * np.cos(th), cy + (roy + 3) * np.sin(th)))
    d.polygon(poly, fill=(255, 255, 255))
    d.ellipse([cx - rox - 3, cy - roy - 3, cx + rox + 3, cy + roy + 3], fill=(255, 255, 255))
    for ang, n in leaders:
        th = np.deg2rad(ang)
        w = min(6, max(2, int(round(n * 5 * np.pi / 180 * (rox + 9)))))
        d.line([(cx + (rox - 1) * np.cos(th), cy + (roy - 1) * np.sin(th)),
                (cx + (rox + 5) * np.cos(th), cy + (roy + 5) * np.sin(th))], fill=(0, 0, 0), width=w)
    d.ellipse([cx - rox, cy - roy, cx + rox, cy + roy], outline=(0, 0, 0), width=int(round(t)))
    size = int(round(2 * riy * 0.55))
    fnt = ImageFont.truetype(font, max(8, size))
    while size > 8 and d.textbbox((0, 0), text, font=fnt)[2] > 2 * rix * 0.86:
        size -= 1
        fnt = ImageFont.truetype(font, size)
    d.text((cx, cy), text, font=fnt, fill=(0, 0, 0), anchor="mm")
    geo = {k: v for k, v in geo.items() if k != "rays"}
    geo["fit"] = (round(on_dark, 1), n_out)
    geo["leaders"] = [(round(a_, 1), n) for a_, n in leaders]
    return geo, [cx - rox - 3, cy - roy - 3, cx + rox + 3, cy + roy + 3]


def residue_check(im_out, geo, others=(), dark=130):
    """成品图上的旧环残留：[(圈, 起角, 止角)]，必须为空。"""
    g = np.array(im_out.convert("L"))
    cx, cy, rox, roy = geo["cx"], geo["cy"], geo["rout_x"], geo["rout_y"]

    def in_other(px, py):
        for o in others:
            if ((px - o["cx"]) / (o["rout_x"] + 4)) ** 2 + ((py - o["cy"]) / (o["rout_y"] + 4)) ** 2 <= 1.0:
                return True
        return False
    bad = []
    for extra in (4, 8):
        darks = []
        for deg, v in ellipse_samples(g, cx, cy, rox + extra, roy + extra).items():
            if v >= dark:
                continue
            if any(min(abs(deg - a_), 360 - abs(deg - a_)) <= 12 for a_, _n in geo.get("leaders", [])):
                continue
            th = np.deg2rad(deg)
            if in_other(cx + (rox + extra) * np.cos(th), cy + (roy + extra) * np.sin(th)):
                continue
            darks.append(deg)
        runs, cur = [], []
        for dg in darks:
            if cur and dg - cur[-1] == 5:
                cur.append(dg)
            else:
                if cur:
                    runs.append(cur)
                cur = [dg]
        if cur:
            runs.append(cur)
        if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == 355:
            runs[0] = runs[-1] + runs[0]
            runs.pop()
        bad += [(extra, r[0], r[-1]) for r in runs if len(r) >= 3]
    return bad


def apply_image(im, boxes, mapping, like_map=None):
    """一幅图：mapping={框号: 编号}，like_map={框号: 参照框号}。返回 (geos, 覆盖矩形列表, 残留失败列表)。"""
    d = ImageDraw.Draw(im)
    like_map = like_map or {}
    geos, cov, bad = {}, [], []
    for i, txt in sorted(mapping.items(), key=lambda kv: kv[0] in like_map):
        geo, rect = redraw(im, d, boxes[i], txt, like=geos.get(like_map.get(i)))
        if geo is None:
            bad.append((i, txt, "geometry"))
            continue
        geos[i] = geo
        cov.append(rect)
    for i, geo in geos.items():
        res = residue_check(im, geo, others=[o for j, o in geos.items() if j != i])
        geo["residue"] = res
        if res:
            bad.append((i, mapping[i], "residue", res))
    return geos, cov, bad


def sheet(figdir, BUBBLES, boxes, out_png, cell=160, cols=8, label_font=None):
    """全部气泡放大拼贴（每格 150 px，标 stem#框号=编号），交付前必须目检一遍。"""
    import os
    fnt = (ImageFont.truetype(label_font, 16) if label_font
           else fontkit.pil("mono-bold", 16))
    items = []
    for stem in sorted(BUBBLES, key=lambda s: (len(s), s)):
        im = Image.open(os.path.join(figdir, stem + ".png")).convert("RGB")
        for i, txt in BUBBLES[stem].items():
            x0, y0, x1, y1 = boxes[stem][i]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r = max(x1 - x0, y1 - y0) * 1.5 + 30
            crop = im.crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r))).resize((150, 150), Image.LANCZOS)
            items.append((f"{stem}#{i}={txt}", crop))
    rows = (len(items) + cols - 1) // cols
    sh = Image.new("RGB", (cols * cell, max(1, rows) * (cell + 22)), "white")
    d = ImageDraw.Draw(sh)
    for j, (name, crop) in enumerate(items):
        x, y = (j % cols) * cell, (j // cols) * (cell + 22)
        sh.paste(crop, (x + 5, y + 20))
        d.text((x + 5, y + 2), name, font=fnt, fill=(200, 0, 0))
    sh.save(out_png)
    return len(items)
