# -*- coding: utf-8 -*-
"""图内烧死英文标注 → 中文回叠（通用，不针对特定文档）。

坐标来源必须是 `figcrop.safe_extent()` 检测出的 `hits`，经 crop 脚本换算成
裁图内像素坐标后落盘（labels.json）。**不要手估像素框**——手估的坐标与
实际裁框来自两次独立判断，一旦裁框微调（哪怕 2pt）就全部错位；而检测
坐标与裁框同源，天然一致。

译名由调用方给出 `{英文原文: 中文}` 映射：英文原文即 hits 里的文本，
键一律按「压缩连续空白」归一（PDF 抽出的文本常含不定量空格）。
"""
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

import fontkit

DEFAULT_FONT = fontkit.find("zh-bold")


def norm(s):
    return " ".join(str(s or "").split())


def bg_color(im, box, grow=6.0):
    """描白贴片的底色：采样框（含外扩）区域的**亮部中位色**。

    纯白贴片贴在灰色图面上是块刺眼的白斑（实测「转子」贴在浅灰转子
    面正中）；JPEG 纸面也不是纯白（≈250 灰），纯白补丁四边会显出
    边界。⇒ 按局部环境色填充：深色像素（被抹的文字、引线）先剔除，
    取其余像素的中位数——转子面得灰、纸面得米白，贴片隐形。
    """
    import numpy as np
    a = np.asarray(im)
    h, w = a.shape[:2]
    x0, y0, x1, y1 = box
    X0 = max(0, int(x0 - grow)); Y0 = max(0, int(y0 - grow))
    X1 = min(w, int(x1 + grow)); Y1 = min(h, int(y1 + grow))
    reg = a[Y0:Y1, X0:X1].reshape(-1, a.shape[2])[:, :3].astype(int)
    if not len(reg):
        return (255, 255, 255)
    lum = reg.mean(axis=1)
    bright = reg[lum > max(120, lum.mean() - 10)]
    med = np.median(bright if len(bright) else reg, axis=0)
    return tuple(int(v) for v in med)


def _fit(draw, text, maxw, maxh, font_path, hi=64, lo=8):
    """在给定框内能放下的最大字号；支持 \n 多行。

    ⚠ hi 不设上限时是「能放多大放多大」——检测框偏大（多行并块、
    蹭进图形）时中文会放大填满，同图字号忽大忽小（避坑 77）。
    调用方应传 uniform 字号作 hi（见 overlay 的 uniform_px）。
    """
    lines = text.split("\n")
    s = hi
    while s > lo:
        f = ImageFont.truetype(font_path, s)
        w = max(draw.textbbox((0, 0), ln, font=f)[2] for ln in lines)
        h = sum(draw.textbbox((0, 0), ln, font=f)[3] for ln in lines) \
            + int(s * 0.25) * (len(lines) - 1)
        if w <= maxw and h <= maxh:
            return f, w, h, lines
        s -= 1
    f = ImageFont.truetype(font_path, lo)
    w = max(draw.textbbox((0, 0), ln, font=f)[2] for ln in lines)
    h = sum(draw.textbbox((0, 0), ln, font=f)[3] for ln in lines)
    return f, w, h, lines


def tighten_box(png_path, box, pad=3, want_h=None):
    """把检测框收紧到框内**真实文字行**的范围（避坑 77 之一）。

    检测框常把邻近图形（星形轮廓、十字线、引线）并进来——整框描白
    会把图形抹掉一块，字号也随框虚高。⇒ 在框内用严格参数二次检测，
    只认文字形态的块（高 14~48px、横长比 1.2~14），取其并集为新框；
    找不到就退回原框（宁大勿漏，英文必须被盖住）。
    """
    im = Image.open(png_path)
    x0, y0, x1, y1 = [int(v) for v in box]
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(im.width, x1); y1 = min(im.height, y1)
    if x1 - x0 < 20 or y1 - y0 < 12:
        return box
    import tempfile, os as _os
    tf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tf.close()
    im.crop((x0, y0, x1, y1)).save(tf.name)
    try:
        w, h = x1 - x0, y1 - y0
        cands = [b for b in detect_raster_labels(tf.name, max_h=48,
                                                 word_gap=30, para_gap=10)
                 if 14 <= b[3] - b[1] <= 48
                 and 1.2 <= (b[2] - b[0]) / max(b[3] - b[1], 1) <= 14
                 # 中带过滤：标签文字居框中，蹭进来的图形轮廓贴框缘——
                 # 不滤则轮廓碎片把并集重新撑回原框（实测「Rotor」框）
                 and (h < 60 or 0.15 * h < (b[1] + b[3]) / 2 < 0.85 * h)]
    finally:
        _os.unlink(tf.name)
    if not cands:
        return box
    if want_h:
        # 已知同图基准字高：只认接近该字高、且**最近框中心**的单候选——
        # 求并集时任何一个漏网的图形碎片都会把框重新撑大（实测「Rotor」）
        sized = [b for b in cands
                 if 0.55 * want_h <= b[3] - b[1] <= 1.6 * want_h]
        if sized:
            cx, cy = w / 2, h / 2
            b = min(sized, key=lambda q: ((q[0] + q[2]) / 2 - cx) ** 2 +
                                          ((q[1] + q[3]) / 2 - cy) ** 2)
            cands = [b]
    nx0 = min(b[0] for b in cands) + x0 - pad
    ny0 = min(b[1] for b in cands) + y0 - pad
    nx1 = max(b[2] for b in cands) + x0 + pad
    ny1 = max(b[3] for b in cands) + y0 + pad
    # 收紧只能变小不能变大；收得只剩一角（<25% 面积）不可信，退回原框
    area0 = (x1 - x0) * (y1 - y0)
    area1 = (nx1 - nx0) * (ny1 - ny0)
    if area1 < 0.05 * area0:
        return box
    return (max(x0, nx0), max(y0, ny0), min(x1, nx1), min(y1, ny1))


def uniform_size(boxes, factor=0.88, lo=14, hi=52):
    """同图标注的统一字号：单行框高的中位数 × factor（避坑 77 之二）。

    同一幅图的原版标注字号一致；译后字号跟着各自检测框走就会忽大忽小。
    多行框（高 > 1.7×中位）不参与统计。"""
    hs = sorted(b[3] - b[1] for b in boxes)
    if not hs:
        return None
    med = hs[len(hs) // 2]
    hs1 = [h for h in hs if h <= 1.7 * med]
    med = sorted(hs1)[len(hs1) // 2] if hs1 else med
    return int(min(hi, max(lo, med * factor)))


def overlay(png_path, hits, zh_map, font_path=DEFAULT_FONT, pad=1.0,
            grow=2.0, verbose=False, uniform_px=None):
    """在 `png_path` 上把 hits 里能查到译名的标注描白重写为中文。

    hits    [{"text": 英文, "bbox": [x0,y0,x1,y1]}]（裁图内像素坐标）
    zh_map  {归一化英文: 中文}；查不到（None）的**原样保留**（不擅自机翻，
            也不留空白——保留原文远好过抹掉信息）；译名为**空串**表示
            「只描白不写字」——该行语义已并入相邻标注（中文更紧凑，
            跨行英文常合并成一行中文），残段必须抹掉而不是保留。
            ⚠ 空串与 None 语义不同，判断用 `is None`，不能用真值——
            实测用真值判断把空串当 miss 过滤，计划抹白的英文残段
            全部原样留在成品图里。
    grow    描白框相对原框的外扩量（px），盖住抗锯齿残留的字边

    返回 (已译条数, 未查到译名的英文列表)。
    """
    im = Image.open(png_path).convert("RGB")
    d = ImageDraw.Draw(im)
    done, missing = 0, []
    for h in hits:
        en = norm(h["text"])
        zh = zh_map.get(en)
        if zh is None:
            missing.append(en)
            continue
        x0, y0, x1, y1 = h["bbox"]
        # 底色采样贴片（非纯白）：转子面得灰、纸面得米白，贴片隐形；
        # 外扩要盖住 JPEG 蚊噪与原英文的抗锯齿残晕（grow 建议 ≥6）
        bg = bg_color(im, (x0, y0, x1, y1), grow=grow + 3)
        d.rectangle([x0 - grow, y0 - grow, x1 + grow, y1 + grow], fill=bg)
        if not zh:                       # 空串：只贴片，无字可写
            done += 1
            continue
        fg = (0, 0, 0) if sum(bg) / 3 >= 140 else (255, 255, 255)
        hi = uniform_px if uniform_px else 64
        f, w, hh, lines = _fit(d, zh, (x1 - x0) - 2 * pad,
                               (y1 - y0) - 2 * pad, font_path, hi=hi)
        cy = (y0 + y1) / 2 - hh / 2
        for ln in lines:
            lw = d.textbbox((0, 0), ln, font=f)[2]
            d.text(((x0 + x1) / 2 - lw / 2, cy), ln, font=f, fill=fg)
            cy += d.textbbox((0, 0), ln, font=f)[3] + f.size * 0.25
        done += 1
    im.save(png_path)
    if verbose:
        print(f"  {os.path.basename(png_path)}: 译 {done} 条"
              + (f"，未收录 {len(missing)} 条" if missing else ""))
    return done, missing


def detect_raster_labels(png_path, thr=140, min_area=6, max_h=44,
                         line_gap=3, word_gap=40, para_gap=14):
    """检测**烧死在位图像素里**的文字块，返回像素 bbox 列表。

    位图内的标注取不到文本层（`figcrop` 只能拿到矢量文本），只能按像素找：
    文字是"深色、细小、成行"的连通块，图形轮廓则粗大连续。
    先按连通域取笔画，滤掉过高的（粗线条/轮廓），再按纵向重叠并成行、
    按行距并成段。返回的是**框**，框里是什么字仍需人读——本机无 OCR，
    这一步天然属于内容层（与「图内位图英文首版必然漏译」同源：
    机器只能告诉你"这里有字"，不能告诉你"这里写的是什么"）。
    """
    import numpy as np
    from scipy import ndimage

    a = np.array(Image.open(png_path).convert("L"))
    lbl, n = ndimage.label(a < thr, structure=np.ones((3, 3)))
    boxes = []
    for sl in ndimage.find_objects(lbl):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if h > max_h or h * w < min_area:
            continue
        boxes.append((xs.start, ys.start, xs.stop - 1, ys.stop - 1))

    def _merge(items, ygap, xgap):
        out = []
        for b in sorted(items, key=lambda q: (q[1], q[0])):
            hit = None
            for i, g in enumerate(out):
                vsep = b[1] > g[3] + ygap or b[3] < g[1] - ygap
                hsep = b[0] > g[2] + xgap or b[2] < g[0] - xgap
                if not vsep and not hsep:
                    hit = i
                    break
            if hit is None:
                out.append(b)
            else:
                g = out[hit]
                out[hit] = (min(g[0], b[0]), min(g[1], b[1]),
                            max(g[2], b[2]), max(g[3], b[3]))
        return out

    lines = _merge(boxes, line_gap, word_gap)
    return sorted(_merge(lines, para_gap, word_gap + 20),
                  key=lambda q: (q[1], q[0]))


def apply_raster(png_path, labels, font_path=DEFAULT_FONT, grow=2.0,
                 pad=1.0, verbose=False, smart=False, uniform_px=None):
    """按 [(x0,y0,x1,y1,中文)] 在位图上描白重写。坐标为该 png 的像素坐标。

    smart=True（推荐）：① 每框先 tighten_box 收紧到真实文字行——检测框
    蹭进图形时整框描白会抹掉图形、字号随框虚高（避坑 77，实测「Rotor」
    大框盖掉转子星形一角、译字放大数倍）；② 同图字号统一
    （uniform_size），超宽才降号。"""
    upx = uniform_px
    if smart:
        labels = [tuple(tighten_box(png_path, t[:4])) + (t[4],)
                  for t in labels]
        upx = uniform_px or uniform_size([t[:4] for t in labels])
        if upx:
            # 二次收紧：仍显著高于基准字高的框（收不动的并块）按
            # 基准字高选最近中心的单候选
            med = upx / 0.88
            # 多行译文（含 \n）与空白抹除框是有意的大框，不得二次收紧
            labels = [tuple(tighten_box(png_path, t[:4], want_h=med)) + (t[4],)
                      if (t[3] - t[1] > 1.7 * med and t[4]
                          and "\n" not in t[4]) else t
                      for t in labels]
    hits = [{"text": f"__raster_{i}", "bbox": [x0, y0, x1, y1]}
            for i, (x0, y0, x1, y1, _zh) in enumerate(labels)]
    zh_map = {f"__raster_{i}": zh
              for i, (_a, _b, _c, _d, zh) in enumerate(labels)}
    return overlay(png_path, hits, zh_map, font_path, pad=pad, grow=grow,
                   verbose=verbose, uniform_px=upx)


def sweep(png_path, covered, out_path=None, inflate=6, min_overlap=0.55,
          min_w=14, min_h=14, **det_kw):
    """成品图漏译排查（机器判据）：检测图上全部文字块，剔除落在
    「已处置区域」内的，余下的框即「疑似未译原文」。

    covered  已处置区域 [(x0,y0,x1,y1), …] = 矢量回叠框 ∪ 位图重写框 ∪
             图题剔除区 ∪ 白名单保留区（纯数字、单位、尺寸字母）。

    ⚠ 为什么必须**逐幅全查**：旧排查法「含嵌入位图 且 矢量标注数为 0
    的图才查位图英文」有判据漏洞——只要检出 1 条矢量文本（哪怕只是
    英文图题的折行残行），整幅图就躲过位图排查。实测一幅三联对照图：
    1 条矢量图题 + 11 条位图标签，全部漏译，旧判据完全放行。
    检出 ≠ 一定漏译（保留项合法），所以 out_path 输出描红核查图供
    人工确认；确认合法的加入 covered 白名单，复跑到检出为 0。

    min_w/min_h  低于此像素尺寸的检出直接丢弃：300dpi 下 14px ≈ 3.4pt，
    比可读文字下限还小，只能是图形碎屑（轮廓斑点、渐变边），
    不滤掉的话核查图上全是无意义的红点，真漏译反而被淹没。
    """
    boxes = [b for b in detect_raster_labels(png_path, **det_kw)
             if b[2] - b[0] >= min_w and b[3] - b[1] >= min_h]

    def _hit(b):
        bx0, by0, bx1, by1 = b
        area = max((bx1 - bx0) * (by1 - by0), 1)
        for cx0, cy0, cx1, cy1 in covered:
            ox = max(0, min(bx1, cx1 + inflate) - max(bx0, cx0 - inflate))
            oy = max(0, min(by1, cy1 + inflate) - max(by0, cy0 - inflate))
            if ox * oy >= min_overlap * area:
                return True
        return False

    left = [b for b in boxes if not _hit(b)]
    if out_path and left:
        im = Image.open(png_path).convert("RGB")
        d = ImageDraw.Draw(im)
        for b in left:
            d.rectangle(b, outline=(255, 0, 0), width=3)
        im.save(out_path)
    return left


def band_cells(png_path, rgb, tol=38, min_w=40, min_h=18):
    """按底色连通域求色带表头的单元格框（浅字深底的检测盲区，避坑 76）。

    暗字检测只认深色墨迹——绿带/蓝带上的白字表头整批漏检且 sweep 不报。
    ⇒ 反过来按**底色**找格子。⚠ 低 dpi 下格间白线只剩 1px，连通域会把
    整行粘成一格（实测 300dpi 蓝带 10 格粘成 1~2 块，表头重绘盖掉整行
    数据）——粘连块还要按**带内白色竖缝**二次切格：对每个连通块内部做
    列投影，底色覆盖率 < 55% 的列即缝，缝间即真单元格。
    返回按 (行, x) 排序的 [(x0,y0,x1,y1)]。
    """
    import numpy as np
    from scipy import ndimage
    a = np.array(Image.open(png_path).convert("RGB")).astype(int)
    mask = (abs(a - np.array(rgb)).sum(axis=2) < tol * 3)
    lbl, _n = ndimage.label(mask)
    out = []
    for sl in ndimage.find_objects(lbl):
        if sl is None:
            continue
        ys, xs = sl
        w, h = xs.stop - xs.start, ys.stop - ys.start
        if w < min_w or h < min_h:
            continue
        sub = mask[ys, xs]
        colfrac = sub.mean(axis=0)
        runs, s = [], None
        for i, ok in enumerate(colfrac >= 0.55):
            if ok and s is None:
                s = i
            elif not ok and s is not None:
                runs.append((s, i)); s = None
        if s is not None:
            runs.append((s, w))
        for r0, r1 in runs:
            if r1 - r0 >= min_w:
                out.append((xs.start + r0, ys.start, xs.start + r1, ys.stop))
    return sorted(out, key=lambda b: (round(b[1] / 40), b[0]))


def repaint_cell(im, box, rgb, zh, font_path=DEFAULT_FONT,
                 fg=(255, 255, 255)):
    """色带单元格整格重绘底色 + 居中写字（配合 band_cells）。

    im 为已打开的 PIL Image（就地修改）；zh 为 None 时不动该格。
    """
    if zh is None:
        return
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = box
    d.rectangle([x0, y0, x1, y1], fill=rgb)
    px = max(12, int((y1 - y0) * 0.52))
    f = ImageFont.truetype(font_path, px)
    bb = d.textbbox((0, 0), zh, font=f)
    while bb[2] - bb[0] > (x1 - x0) - 8 and px > 10:
        px -= 1
        f = ImageFont.truetype(font_path, px)
        bb = d.textbbox((0, 0), zh, font=f)
    d.text(((x0 + x1) / 2 - (bb[2] - bb[0]) / 2 - bb[0],
            (y0 + y1) / 2 - (bb[3] - bb[1]) / 2 - bb[1]),
           zh, font=f, fill=fg)


def apply_manifest(figdir, zh_map, font_path=DEFAULT_FONT, verbose=True):
    """按 figdir/labels.json 批量回叠。返回全部未收录英文（去重、排序）。

    ⚠ 必须在**重新裁图之后**跑；裁图会覆盖 png，把上一轮叠的中文抹掉，
    这是**有意为之**——始终从干净原图描白，避免反复叠字导致的重影。
    """
    mf = os.path.join(figdir, "labels.json")
    with open(mf, encoding="utf-8") as f:
        manifest = json.load(f)
    miss = set()
    for name, hits in manifest.items():
        p = os.path.join(figdir, name)
        if not hits or not os.path.exists(p):
            continue
        _n, m = overlay(p, hits, zh_map, font_path, verbose=verbose)
        miss |= set(m)
    return sorted(miss)


def apply_figures_json(work, zh_map, font_path=None, verbose=True):
    """R 级：把 extract.py 抹掉的图内矢量英文（data/figures.json 的 labels）回叠成中文。

    extract 裁图时已把标注 redaction 掉并记下**裁框内的 pt 坐标**；这里按各图的
    渲染 dpi 换算成像素框交给 overlay()。坐标与裁框同源，不手估。

    幂等：首次运行把干净底图备份到 figures/_clean/，之后每次都从干净底图重叠，
    重复构建不会叠出重影。返回全部未收录译名的英文（去重、排序）。
    """
    import shutil
    font_path = font_path or DEFAULT_FONT
    fp = os.path.join(work, "data", "figures.json")
    if not os.path.exists(fp):
        return []
    with open(fp, encoding="utf-8") as fh:
        figs = json.load(fh)
    zmap = {norm(k): v for k, v in (zh_map or {}).items()}
    figdir = os.path.join(work, "figures")
    clean = os.path.join(figdir, "_clean")
    miss = set()
    for m in figs:
        labels = m.get("labels") or []
        p = os.path.join(figdir, m["file"])
        if not labels or not os.path.exists(p):
            continue
        os.makedirs(clean, exist_ok=True)
        c = os.path.join(clean, m["file"])
        if not os.path.exists(c):
            shutil.copy2(p, c)
        shutil.copy2(c, p)
        k = float(m.get("dpi", 300)) / 72.0
        hits = [dict(text=lb["text"],
                     bbox=[lb["x"] * k, lb["y"] * k,
                           (lb["x"] + lb["w"]) * k, (lb["y"] + lb["h"]) * k])
                for lb in labels]
        _n, mm = overlay(p, hits, zmap, font_path, verbose=verbose)
        miss |= set(mm)
    return sorted(miss)
