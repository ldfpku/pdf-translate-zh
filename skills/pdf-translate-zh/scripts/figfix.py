# -*- coding: utf-8 -*-
"""Pixel-level bitmap figure-label replacement and quality checks."""
import math
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

import figlabel
import fontkit


def ink_gray(arr):
    """Return the darkest RGB channel so saturated colored ink remains detectable."""
    a = np.asarray(arr.convert("RGB") if hasattr(arr, "convert") else arr)[..., :3]
    return a.min(axis=2)


def _box(box, w, h):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    return max(0, x0), max(0, y0), min(w - 1, x1), min(h - 1, y1)


def paper_is_white(im):
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    return (a.min(axis=2) >= 245).mean() > 0.5 and (a.max(axis=2) - a.min(axis=2)).mean() < 6


def erase_rect(im, box, pad=3):
    """Erase a label using white on white paper and a local sampled color otherwise."""
    x0, y0, x1, y1 = _box(box, im.width, im.height)
    if paper_is_white(im):
        color = (255, 255, 255)
    else:
        color = figlabel.bg_color(im, (x0, y0, x1, y1), grow=12)
        if min(color) >= 245 and max(color) - min(color) <= 12:
            color = (255, 255, 255)
    ImageDraw.Draw(im).rectangle(
        [max(0, x0 - pad), max(0, y0 - pad),
         min(im.width - 1, x1 + pad), min(im.height - 1, y1 + pad)],
        fill=color,
    )


def clean_halo(im, box, threshold=225, margin=24, pad=3):
    x0, y0, x1, y1 = _box(box, im.width, im.height)
    rx0, ry0 = max(0, x0 - 60), max(0, y0 - 60)
    rx1, ry1 = min(im.width, x1 + 61), min(im.height, y1 + 61)
    ref = ink_gray(im.crop((rx0, ry0, rx1, ry1)))
    ring = np.ones(ref.shape, bool)
    ax0, ay0 = max(0, x0 - 30 - ry0), max(0, y0 - 30 - rx0)
    bx0, by0 = max(0, x0 - 30 - rx0), max(0, y0 - 30 - ry0)
    ring[by0:min(ref.shape[0], y1 + 31 - ry0), bx0:min(ref.shape[1], x1 + 31 - rx0)] = False
    paper = ref[ring & (ref > 200)]
    if len(paper) < 50 or np.median(paper) < 245:
        return
    wx0, wy0 = max(0, x0 - pad - margin), max(0, y0 - pad - margin)
    wx1, wy1 = min(im.width, x1 + pad + margin + 1), min(im.height, y1 + pad + margin + 1)
    win = np.asarray(im.crop((wx0, wy0, wx1, wy1))).copy()
    win[win.min(axis=2) >= threshold] = 255
    im.paste(Image.fromarray(win), (wx0, wy0))


def clean_global(im, chroma_max=12, threshold=225):
    a = np.asarray(im.convert("RGB")).copy()
    lo, hi = a.min(axis=2), a.max(axis=2)
    mask = (lo >= threshold) & ((hi.astype(np.int16) - lo.astype(np.int16)) <= chroma_max)
    a[mask] = 255
    im.paste(Image.fromarray(a))


def clean_fragments(im, source, boxes, white=None, margin=12, pad=3):
    """Remove small post-erase remnants that were connected to source text strokes."""
    white = paper_is_white(source) if white is None else white
    src_lum, dst_lum = ink_gray(source), ink_gray(im)
    out = np.asarray(im.convert("RGB")).copy()
    h, w = src_lum.shape
    removed = 0
    for box in boxes:
        x0, y0, x1, y1 = _box(box, w, h)
        wx0, wy0 = max(0, x0 - pad - margin), max(0, y0 - pad - margin)
        wx1, wy1 = min(w, x1 + pad + margin + 1), min(h, y1 + pad + margin + 1)
        src_win = src_lum[wy0:wy1, wx0:wx1] < 200
        dst_win = dst_lum[wy0:wy1, wx0:wx1] < 200
        sx0, sy0 = max(0, x0 - pad) - wx0, max(0, y0 - pad) - wy0
        sx1, sy1 = min(w, x1 + pad + 1) - wx0, min(h, y1 + pad + 1) - wy0
        src_labels, _ = ndimage.label(src_win, structure=np.ones((3, 3)))
        text_ids = set(np.unique(src_labels[sy0:sy1, sx0:sx1])) - {0}
        dst_labels, _ = ndimage.label(dst_win, structure=np.ones((3, 3)))
        for k, sl in enumerate(ndimage.find_objects(dst_labels), 1):
            if sl is None:
                continue
            ys, xs = sl
            if ys.start == 0 or xs.start == 0 or ys.stop == dst_win.shape[0] or xs.stop == dst_win.shape[1]:
                continue
            if max(ys.stop - ys.start, xs.stop - xs.start) > 0.9 * max(8, y1 - y0):
                continue
            mask = dst_labels == k
            if not (set(np.unique(src_labels[mask])) & text_ids):
                continue
            region = out[wy0:wy1, wx0:wx1]
            region[mask] = 255 if white else figlabel.bg_color(im, box, grow=12)
            removed += 1
    im.paste(Image.fromarray(out))
    return removed


def text_box(arr, box):
    """Tighten a detection box to text components; leave vertical text untouched."""
    a = np.asarray(arr.convert("RGB") if hasattr(arr, "convert") else arr)[..., :3]
    h, w = a.shape[:2]
    x0, y0, x1, y1 = _box(box, w, h)
    if y1 - y0 + 1 > 3 * max(1, x1 - x0 + 1):
        return (x0, y0, x1, y1)
    sub = ink_gray(a[y0:y1 + 1, x0:x1 + 1]) < 170
    clean = sub.copy()
    full_ink = ink_gray(a)
    span_y, span_x = sub.shape
    for xi in range(span_x):
        run = np.flatnonzero(sub[:, xi])
        if len(run) >= 15 and run[-1] - run[0] >= 14:
            ax = x0 + xi
            above = full_ink[max(0, y0 - 12):y0, ax] < 170
            below = full_ink[y1 + 1:min(h, y1 + 13), ax] < 170
            if above.sum() >= 8 or below.sum() >= 8:
                clean[:, max(0, xi - 1):min(span_x, xi + 2)] = False
    for yi in range(span_y):
        run = np.flatnonzero(sub[yi, :])
        if len(run) >= 15 and run[-1] - run[0] >= 14:
            ay = y0 + yi
            left = full_ink[ay, max(0, x0 - 12):x0] < 170
            right = full_ink[ay, x1 + 1:min(w, x1 + 13)] < 170
            if left.sum() >= 8 or right.sum() >= 8:
                clean[max(0, yi - 1):min(span_y, yi + 2), :] = False
    sub = clean
    labels, count = ndimage.label(sub, structure=np.ones((3, 3)))
    parts = []
    for k, sl in enumerate(ndimage.find_objects(labels), 1):
        if sl is None:
            continue
        ys, xs = sl
        hh, ww = ys.stop - ys.start, xs.stop - xs.start
        if hh <= 5 and ww >= 12 and (xs.start <= 6 or xs.stop >= sub.shape[1] - 6):
            continue
        if ww > 6 * max(hh, 1) and hh <= 5:
            continue
        if hh > 3 * max(ww, 1) and ww <= 4:
            continue
        parts.append((xs.start, ys.start, xs.stop - 1, ys.stop - 1))
    if not parts:
        return (x0, y0, x1, y1)
    bx0 = min(p[0] for p in parts) + x0 - 4
    by0 = min(p[1] for p in parts) + y0 - 4
    bx1 = max(p[2] for p in parts) + x0 + 4
    by1 = max(p[3] for p in parts) + y0 + 4
    if (bx1 - bx0 + 1) * (by1 - by0 + 1) < 0.05 * (x1 - x0 + 1) * (y1 - y0 + 1):
        return (x0, y0, x1, y1)
    return max(x0, bx0), max(y0, by0), min(x1, bx1), min(y1, by1)


def protect_mask(im, box, others=(), pad=3, margin=40):
    """Capture long straight components crossing a text box for exact restoration."""
    x0, y0, x1, y1 = _box(box, im.width, im.height)
    rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
    rx1, ry1 = min(im.width, x1 + pad + 1), min(im.height, y1 + pad + 1)
    wx0, wy0 = max(0, rx0 - margin), max(0, ry0 - margin)
    wx1, wy1 = min(im.width, rx1 + margin), min(im.height, ry1 + margin)
    win = np.asarray(im.crop((wx0, wy0, wx1, wy1))).copy()
    dark = ink_gray(win) < 170
    ix0, iy0, ix1, iy1 = rx0 - wx0, ry0 - wy0, rx1 - wx0, ry1 - wy0
    for other in others:
        ox0, oy0, ox1, oy1 = _box(other, im.width, im.height)
        if (ox0, oy0, ox1, oy1) == (x0, y0, x1, y1):
            continue
        dark[max(0, oy0 - wy0):min(dark.shape[0], oy1 + 1 - wy0),
             max(0, ox0 - wx0):min(dark.shape[1], ox1 + 1 - wx0)] = False
    labels, count = ndimage.label(dark, structure=np.ones((3, 3)))
    candidates = np.zeros(dark.shape, bool)
    for k, sl in enumerate(ndimage.find_objects(labels), 1):
        if sl is None:
            continue
        ys, xs = sl
        if ys.stop <= iy0 or ys.start >= iy1 or xs.stop <= ix0 or xs.start >= ix1:
            continue
        extends = max(ix0 - xs.start, xs.stop - ix1, iy0 - ys.start, ys.stop - iy1)
        if extends >= 12:
            candidates |= labels == k
    region = np.zeros(dark.shape, bool)
    region[iy0:iy1, ix0:ix1] = True
    inside = candidates & region
    straight = (ndimage.binary_opening(inside, structure=np.ones((1, 15))) |
                ndimage.binary_opening(inside, structure=np.ones((15, 1))))
    protected = ndimage.binary_dilation(straight, iterations=1) & candidates & region
    protected = ndimage.binary_dilation(protected, iterations=1) & (ink_gray(win) < 235) & region
    if not protected.any():
        return None
    return wx0, wy0, protected, win[protected]


def leader_stubs(arr, box, anchor, exclude=()):
    """Find a thin line immediately outside the declared anchor side."""
    a = np.asarray(arr.convert("RGB") if hasattr(arr, "convert") else arr)[..., :3]
    h, w = a.shape[:2]
    x0, y0, x1, y1 = _box(box, w, h)
    sides = {"LR": ("L", "R"), "A": ("L", "R", "U", "D"),
             "L": ("L",), "R": ("R",), "D": ("D",), "U": ("U",)}.get(anchor, ())
    lum = ink_gray(a)
    found = []
    for side in sides:
        d = 44
        if side == "R":
            q = (x1 + 1, y0 - d, x1 + d, y1 + d)
        elif side == "L":
            q = (x0 - d, y0 - d, x0 - 1, y1 + d)
        elif side == "U":
            q = (x0 - d, y0 - d, x1 + d, y0 - 1)
        else:
            q = (x0 - d, y1 + 1, x1 + d, y1 + d)
        ax0, ay0, ax1, ay1 = max(0, q[0]), max(0, q[1]), min(w - 1, q[2]), min(h - 1, q[3])
        if ax1 <= ax0 or ay1 <= ay0:
            continue
        mask = lum[ay0:ay1 + 1, ax0:ax1 + 1] < 170
        for eb in exclude:
            ex0, ey0, ex1, ey1 = _box(eb, w, h)
            mask[max(0, ey0 - ay0):min(mask.shape[0], ey1 + 1 - ay0),
                 max(0, ex0 - ax0):min(mask.shape[1], ex1 + 1 - ax0)] = False
        labels, count = ndimage.label(mask, structure=np.ones((3, 3)))
        for k, sl in enumerate(ndimage.find_objects(labels), 1):
            if sl is None:
                continue
            ys, xs = np.where(labels[sl] == k)
            X, Y = xs + sl[1].start + ax0, ys + sl[0].start + ay0
            dist = np.hypot(np.maximum(np.maximum(x0 - X, 0), X - x1),
                            np.maximum(np.maximum(y0 - Y, 0), Y - y1))
            if dist.min() > 16 or max(np.ptp(X), np.ptp(Y)) < 10:
                continue
            if ((X <= ax0).any() and (X >= ax1).any()) or ((Y <= ay0).any() and (Y >= ay1).any()):
                continue
            j0, j2 = int(dist.argmin()), int(dist.argmax())
            p0 = np.array([X[j0], Y[j0]], dtype=float)
            p2 = np.array([X[j2], Y[j2]], dtype=float)
            points = np.column_stack((X, Y)).astype(float)
            direction = p2 - p0
            norm = np.linalg.norm(direction)
            if norm == 0:
                continue
            u = direction / norm
            if ((points - p0) @ u < -3).mean() > 0.05:
                continue
            if side in ("L", "R") and not y0 - 8 <= p0[1] <= y1 + 8:
                continue
            if side in ("U", "D") and not x0 - 8 <= p0[0] <= x1 + 8:
                continue
            if (side == "R" and u[0] < 0.5) or (side == "L" and u[0] > -0.5):
                continue
            if (side == "D" and u[1] < 0.5) or (side == "U" and u[1] > -0.5):
                continue
            width = len(X) / max(norm, 1)
            if width > 7:
                continue
            pixels = a[Y, X]
            depth = lum[Y, X]
            core = pixels[depth <= np.percentile(depth, 50)]
            found.append({
                "side": side, "X": X, "Y": Y, "p0": p0, "p2": p2, "p1": None,
                "gap": float(max(1, {"R": p0[0] - x1, "L": x0 - p0[0],
                                     "D": p0[1] - y1, "U": y0 - p0[1]}[side])),
                "width": max(1, int(round(width))),
                "cmid": tuple(int(v) for v in np.median(core, axis=0)),
            })
    best = {}
    for stub in found:
        if stub["side"] not in best or stub["gap"] < best[stub["side"]]["gap"]:
            best[stub["side"]] = stub
    return list(best.values())


def cap_height(arr, box):
    x0, y0, x1, y1 = _box(box, arr.shape[1], arr.shape[0])
    mask = ink_gray(arr[y0:y1 + 1, x0:x1 + 1]) < 150
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    heights = [sl[0].stop - sl[0].start for sl in ndimage.find_objects(labels)
               if sl is not None and sl[0].stop - sl[0].start >= 6]
    if not heights:
        return None
    largest = max(heights)
    return float(np.median([v for v in heights if v >= 0.6 * largest]))


def font_cap_ratio(font):
    f = ImageFont.truetype(font, 200)
    box = f.getmask("0123456789HE").getbbox()
    return (box[3] - box[1]) / 200 if box else 1.0


def ink_color(arr, box, mode="sat"):
    x0, y0, x1, y1 = _box(box, arr.shape[1], arr.shape[0])
    pixels = np.asarray(arr)[y0:y1 + 1, x0:x1 + 1, :3].reshape(-1, 3).astype(np.int16)
    depth = 255 - pixels.min(axis=1)
    ink = pixels[depth >= 80]
    if len(ink) < 10:
        return 0, 0, 0
    core = ink[(255 - ink.min(axis=1)) >= np.percentile(255 - ink.min(axis=1), 70)]
    if mode == "sat":
        chroma = core.max(axis=1) - core.min(axis=1)
        if chroma.max(initial=0) >= 40:
            core = core[chroma >= np.percentile(chroma, 50)]
    return tuple(int(v) for v in np.median(core, axis=0))


_NO_HEAD = set("，。、；：！？）》」』】,.;:!?)%")


def wrap_zh(text, font, maxw):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    tokens = re.findall(r"[A-Za-z0-9.,/%+\-]+|\s+|.", text)
    lines, current = [], ""
    for token in tokens:
        trial = current + token
        if current and d.textbbox((0, 0), trial.rstrip(), font=font)[2] > maxw and not token.isspace():
            if token[0] in _NO_HEAD:
                current = trial
                continue
            cut = max(current.rfind(p) for p in "。；，")
            if cut > 0:
                lines.append(current[:cut + 1].rstrip())
                current = current[cut + 1:].lstrip() + token
            else:
                lines.append(current.rstrip())
                current = token.lstrip()
        else:
            current = trial
    if current.strip():
        lines.append(current.strip())
    return "\n".join(lines)


def _text_metrics(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b, max(0, b[2] - b[0]), max(0, b[3] - b[1])


def apply_labels(im, boxes, labels, opts=None):
    """Return (final image, report) after a two-pass erase-and-write operation."""
    opts = opts or {}
    source = im.convert("RGB").copy()
    original = np.asarray(source).copy()
    output = source.copy()
    plans, covered = [], []
    for index, value in labels.items():
        if not isinstance(index, int) or value in ("__KEEP__", "__SKIP__", None):
            continue
        spec = dict(value) if isinstance(value, dict) else {"zh": value}
        text = str(spec.get("zh", ""))
        if "box" in spec:
            erase_box = tuple(spec["box"])
        else:
            erase_box = tuple(boxes[index])
        union = spec.get("union", [])
        for j in union:
            b = boxes[j]
            erase_box = (min(erase_box[0], b[0]), min(erase_box[1], b[1]),
                         max(erase_box[2], b[2]), max(erase_box[3], b[3]))
        if spec.get("rot") not in (90, 270):
            erase_box = text_box(original, erase_box)
        anchor = spec.get("anchor", "C")
        endpoint = None
        if isinstance(anchor, str) and re.match(r"^[LRDU]:\d+,\d+$", anchor):
            side, xy = anchor.split(":")
            endpoint = tuple(map(int, xy.split(",")))
            anchor = side
        anchor = {"left": "L", "right": "R", "center": "C"}.get(anchor, anchor)
        spec["anchor"] = anchor
        plans.append({"index": index, "text": text, "box": erase_box, "spec": spec,
                      "endpoint": endpoint})
        covered.append(list(erase_box))

    regular = opts.get("font_path") or fontkit.find("zh")
    default_px = opts.get("size_px")
    if not default_px:
        caps = [cap_height(original, p["box"]) for p in plans if not p["spec"].get("title")]
        caps = [v for v in caps if v]
        default_px = max(12, int(round(float(np.median(caps)) / font_cap_ratio(regular)))) if caps else 24
    for plan in plans:
        plan["stubs"] = leader_stubs(original, plan["box"], plan["spec"]["anchor"], covered)

    for plan in plans:
        box = plan["box"]
        protected = protect_mask(output, box, covered)
        erase_rect(output, box)
        if protected is not None:
            x, y, mask, colors = protected
            win = np.asarray(output.crop((x, y, x + mask.shape[1], y + mask.shape[0]))).copy()
            win[mask] = colors
            output.paste(Image.fromarray(win), (x, y))
        clean_halo(output, box)
    clean_fragments(output, source, [p["box"] for p in plans])
    if paper_is_white(source):
        clean_global(output, chroma_max=12)

    erase_image = output.copy()
    erase_path = opts.get("erase_path")
    if erase_path:
        import os
        os.makedirs(os.path.dirname(erase_path), exist_ok=True)
        erase_image.save(erase_path)

    draw = ImageDraw.Draw(output)
    text_rects = []
    for plan in plans:
        spec, text = plan["spec"], plan["text"]
        x0, y0, x1, y1 = plan["box"]
        bold_font = fontkit.find("zh-bold") if spec.get("bold") else regular
        size = spec.get("size_px", spec.get("px", default_px))
        if spec.get("title"):
            cap = cap_height(original, plan["box"])
            if cap:
                size = max(12, int(round(cap / font_cap_ratio(bold_font))))
        font = ImageFont.truetype(bold_font, int(size))
        if spec.get("wrap"):
            text = wrap_zh(text.replace("\n", ""), font, max(1, x1 - x0))
        lines = text.split("\n")
        boxes_and_sizes = [_text_metrics(draw, line, font) for line in lines]
        widths = [v[1] for v in boxes_and_sizes]
        heights = [v[2] for v in boxes_and_sizes]
        line_h = max(int(size * 1.22), max(heights, default=0))
        tw, th = max(widths, default=0), line_h * len(lines)
        anchor = spec["anchor"]
        stubs = [s for s in plan["stubs"] if s["side"] == anchor]
        if anchor == "LR":
            stubs = [s for s in plan["stubs"] if s["side"] in ("L", "R")]
        stub = stubs[0] if stubs else None
        if plan["endpoint"]:
            px, py = plan["endpoint"]
            stub = {"p0": np.array([px, py], float), "gap": 8.0, "side": anchor}
        if anchor == "L":
            lx = (stub["p0"][0] + stub["gap"]) if stub else x0
        elif anchor == "R":
            lx = ((stub["p0"][0] - stub["gap"]) if stub else x1) - tw
        elif spec.get("align") == "L":
            lx = x0 + 4
        elif spec.get("align") == "R":
            lx = x1 - 4 - tw
        else:
            lx = (x0 + x1 - tw) / 2
        ly = (y0 + y1 - th) / 2
        if anchor == "D":
            ly = y1 - th
        elif anchor == "U":
            ly = y0
        elif stub and anchor in ("L", "R") and (y1 - y0) > 1.5 * th:
            ly = stub["p0"][1] - th / 2
        elif plan["endpoint"] and anchor in ("L", "R") and len(lines) > 1:
            ly = plan["endpoint"][1] - line_h / 2
        floor = max(1, int(default_px * (0.8 if anchor == "L" or spec.get("align") == "L" else 0.7)))
        while int(size) > floor and (lx < 4 or ly < 4 or lx + tw > output.width - 4 or ly + th > output.height - 4):
            size = int(size) - 1
            font = ImageFont.truetype(bold_font, int(size))
            boxes_and_sizes = [_text_metrics(draw, line, font) for line in lines]
            widths = [v[1] for v in boxes_and_sizes]
            heights = [v[2] for v in boxes_and_sizes]
            line_h = max(int(size * 1.22), max(heights, default=0))
            tw, th = max(widths, default=0), line_h * len(lines)
            if anchor == "L" and stub:
                lx = stub["p0"][0] + stub["gap"]
            elif anchor == "R" and stub:
                lx = stub["p0"][0] - stub["gap"] - tw
            elif spec.get("align") == "L":
                lx = x0 + 4
            elif spec.get("align") == "R":
                lx = x1 - 4 - tw
            else:
                lx = (x0 + x1 - tw) / 2
            ly = (y0 + y1 - th) / 2
        lx = min(max(4, lx), max(4, output.width - tw - 4))
        ly = min(max(4, ly), max(4, output.height - th - 4))
        lum = ink_gray(erase_image)
        if anchor in ("L", "R", "U", "D") and not plan["endpoint"]:
            lx, ly = _avoid_lines(lum, lx, ly, tw, th, anchor, output.width, output.height)

        fg = spec.get("fg")
        if fg == "auto":
            fg = ink_color(original, plan["box"], mode="sat")
        if fg is None:
            bg = figlabel.bg_color(erase_image, plan["box"], grow=12)
            fg = (0, 0, 0) if sum(bg) / 3 >= 140 else (255, 255, 255)
        elif not isinstance(fg, str):
            fg = tuple(fg)
        if spec.get("rot") in (90, 270):
            mask = Image.new("L", (max(1, tw + 8), max(1, th + 8)), 0)
            md = ImageDraw.Draw(mask)
            yy = 4
            for line, (bb, width, height) in zip(lines, boxes_and_sizes):
                md.text((4 - bb[0], yy - bb[1]), line, font=font, fill=255)
                yy += line_h
            mask = mask.rotate(spec["rot"], expand=True)
            lx, ly = round((x0 + x1 + 1 - mask.width) / 2), round((y0 + y1 + 1 - mask.height) / 2)
            output.paste(Image.new("RGB", mask.size, fg), (lx, ly), mask)
            text_rects.append((lx + 4, ly + 4, lx + mask.width - 4, ly + mask.height - 4))
            draw = ImageDraw.Draw(output)
            continue

        for row, (line, metrics) in enumerate(zip(lines, boxes_and_sizes)):
            bb, width, height = metrics
            if spec.get("align") == "L" or anchor == "L":
                tx = lx
            elif anchor == "R":
                tx = lx + tw - width
            else:
                tx = lx + (tw - width) / 2
            ty = ly + row * line_h
            draw.text((tx - bb[0], ty - bb[1]), line, font=font, fill=fg)
        text_rects.append((round(lx), round(ly), round(lx + tw), round(ly + th)))
        for stub in stubs:
            side = stub["side"]
            if side == "R":
                target = (lx + tw + stub["gap"], stub["p0"][1])
            elif side == "L":
                target = (lx - stub["gap"], stub["p0"][1])
            elif side == "D":
                target = (stub["p0"][0], ly + th + stub["gap"])
            else:
                target = (stub["p0"][0], ly - stub["gap"])
            p0 = tuple(stub["p0"])
            if math.dist(p0, target) > 2:
                draw.line([p0, target], fill=stub.get("cmid", (0, 0, 0)),
                          width=stub.get("width", 2))
    report = {
        "erase_boxes": covered,
        "text_boxes": text_rects,
        "erase_image": erase_image,
        "leaders": [len(p["stubs"]) for p in plans],
    }
    return output, report


def _avoid_lines(lum, x, y, width, height, anchor, w, h, pad=3, step=2, limit=80):
    original = (x, y)
    def dirty(px, py):
        x0, y0 = max(0, int(px - pad)), max(0, int(py - pad))
        x1, y1 = min(w, int(px + width + pad)), min(h, int(py + height + pad))
        return (lum[y0:y1, x0:x1] < 170).sum() > 3
    if not dirty(x, y):
        return x, y
    dx, dy = {"R": (-step, 0), "L": (step, 0), "D": (0, -step), "U": (0, step)}[anchor]
    for _ in range(limit // step):
        x, y = x + dx, y + dy
        if x < 4 or y < 4 or x + width > w - 4 or y + height > h - 4:
            break
        if not dirty(x, y):
            return x, y
    return original


def check_residual(source, erased, boxes, min_pixels=6):
    """Find surviving source-like dark components in the intended erase areas."""
    src, dst = ink_gray(source), ink_gray(erased)
    candidates = np.zeros(src.shape, bool)
    for b in boxes:
        x0, y0, x1, y1 = _box(b, src.shape[1], src.shape[0])
        candidates[y0:y1 + 1, x0:x1 + 1] = True
    mask = candidates & (src < 150) & (dst < 150)
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    return [(sl[1].start, sl[0].start, sl[1].stop - 1, sl[0].stop - 1)
            for sl in ndimage.find_objects(labels) if sl is not None
            and int((labels[sl] > 0).sum()) >= min_pixels]


def check_lost(source, final, erase_boxes, text_boxes=(), min_pixels=1):
    """Find original dark line pixels erased outside the text-body regions."""
    src, dst = ink_gray(source), ink_gray(final)
    text = np.zeros(src.shape, bool)
    for b in erase_boxes:
        if b[3] - b[1] > 3 * max(1, b[2] - b[0]):
            x0, y0, x1, y1 = _box(b, src.shape[1], src.shape[0])
            text[y0:y1 + 1, x0:x1 + 1] = True
    for b in text_boxes:
        x0, y0, x1, y1 = _box(b, src.shape[1], src.shape[0])
        text[max(0, y0 - 2):y1 + 3, max(0, x0 - 2):x1 + 3] = True
    allowed = np.zeros(src.shape, bool)
    for b in erase_boxes:
        x0, y0, x1, y1 = _box(b, src.shape[1], src.shape[0])
        allowed[y0:y1 + 1, x0:x1 + 1] = True
    mask = (src < 120) & (dst >= 235) & ~text & allowed
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    return [(sl[1].start, sl[0].start, sl[1].stop - 1, sl[0].stop - 1)
            for sl in ndimage.find_objects(labels) if sl is not None
            and int((labels[sl] > 0).sum()) >= min_pixels]


def check_overlap(erased, text_boxes, max_pixels=3):
    lum = ink_gray(erased)
    hits = []
    for i, b in enumerate(text_boxes):
        x0, y0, x1, y1 = _box(b, lum.shape[1], lum.shape[0])
        region = lum[max(0, y0 - 2):y1 + 3, max(0, x0 - 2):x1 + 3]
        count = int((region < 170).sum())
        if count > max_pixels:
            hits.append((i, count))
    return hits
