# -*- coding: utf-8 -*-
"""位图插图流水线（R 级重排用）：提取原图 → 超分 → 检测图内文字 → 回叠中文 + 件号气泡重绘 → 漏译排查。

「机器给框、人读字」：坐标全部来自检测，内容层只按**框号**给译名，禁止手估像素框（figures.md §3、§16、§17）。

    python figpipe.py extract <源.pdf> <工作区>      提取嵌入位图（SMask 合成白底）→ figures_src/xNN.png、data/images.json
    python sr.py <工作区>/figures_src <工作区>/figures_sr --places <工作区>/data/images.json --min-dpi 150
    python figpipe.py detect  <工作区> [--src figures_sr]   逐幅检测文字块 → data/det_boxes.json、qa/det_*.png（带框号）
    python figpipe.py apply   <工作区> <labels.py>          按 LABELS 回叠中文、按 BUBBLES 重绘气泡 → figures/
    python figpipe.py sweep   <工作区> <labels.py>          成品图漏译排查：检测到的文字块 − 已处置区 → qa/sweep_*.png
    python figpipe.py sheet   <工作区> <labels.py>          全部件号气泡放大拼贴 → qa/bubbles_*.png（交付前目检）

labels.py（内容层）：
    from figpipe import KEEP, SKIP
    LABELS = {"x12": {0: "剖视图 A-A", 1: KEEP, 2: SKIP, ("opt", 0): {"bold": True, "anchor": "left", "union": [3]}}}
    BUBBLES = {"x12": {1: "01", 4: "02"}}          # 框号 → 判读后的件号（与步骤文字、零件表对账）
    BUBBLE_LIKE = {"x12": {7: 1}}                  # 可选：几何求不出时参照同图另一气泡的尺寸
    FONT_SCALE = 0.98                              # 可选：中文字号 = 原文行高中位数 × 此值
KEEP = 保留原文（件号气泡、商标、尺寸代号）；SKIP = 碎屑/非文字（引线、零件轮廓）；**未列出的框视为漏译并报错**。
("opt", i) 选项：union=[并入的框号]、bold、anchor(left|right|center)、px（字号）、dx/dy、grow（铺底外扩）。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()

import importlib.util
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

import bubbles
import figlabel
import fontkit
import tightbox

KEEP, SKIP = "__KEEP__", "__SKIP__"
# 4 倍超分图上的检测参数：原图标注字高 8~11 px → 超分后 32~44 px（figures.md §16.1）
DET_KW_4X = dict(thr=150, min_area=40, max_h=70, line_gap=8, word_gap=52, para_gap=22)
DET_KW_1X = dict(thr=150, min_area=6, max_h=24, line_gap=2, word_gap=13, para_gap=6)
MIN_WH_4X, MIN_WH_1X = (18, 16), (5, 4)


def _paths(work):
    return dict(src=os.path.join(work, "figures_src"), sr=os.path.join(work, "figures_sr"),
                out=os.path.join(work, "figures"), qa=os.path.join(work, "qa"),
                data=os.path.join(work, "data"))


def _load_labels(path):
    spec = importlib.util.spec_from_file_location("labels_zh", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("figpipe", sys.modules[__name__])
    spec.loader.exec_module(mod)
    return (getattr(mod, "LABELS", {}), getattr(mod, "BUBBLES", {}), getattr(mod, "BUBBLE_LIKE", {}),
            getattr(mod, "FONT_SCALE", 0.98))


# ---------------------------------------------------------------- 提取
def extract(pdf, work, min_pt=40):
    """按 xref 提取嵌入位图（同一 xref 多处放置只存一份），软掩膜按掩膜尺寸合成到白底（避坑 106）。"""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    P = _paths(work)
    os.makedirs(P["src"], exist_ok=True)
    os.makedirs(P["data"], exist_ok=True)
    meta = {}
    with fitz.open(pdf) as doc:
        for pno, page in enumerate(doc):
            for info in page.get_images(full=True):
                xref, smask = info[0], info[1]
                rects = [r for r in page.get_image_rects(xref) if r.width >= min_pt or r.height >= min_pt]
                if not rects:
                    continue
                stem = "x%d" % xref
                if stem not in meta:
                    d = doc.extract_image(xref)
                    im = Image.open(io.BytesIO(d["image"])).convert("RGB")
                    if smask:
                        m = Image.open(io.BytesIO(doc.extract_image(smask)["image"])).convert("L")
                        if m.size != im.size:
                            im = im.resize(m.size, Image.LANCZOS)
                        bg = Image.new("RGB", im.size, (255, 255, 255))
                        bg.paste(im, (0, 0), m)
                        im = bg
                    im.save(os.path.join(P["src"], stem + ".png"))
                    meta[stem] = dict(file=stem + ".png", xref=xref, w=im.width, h=im.height, places=[])
                for r in rects:
                    meta[stem]["places"].append(dict(page=pno + 1, rect=[round(v, 2) for v in r]))
    for stem, m in meta.items():
        ws = [p["rect"][2] - p["rect"][0] for p in m["places"]]
        m["eff_dpi"] = round(m["w"] / max(ws) * 72, 1)
    json.dump(meta, open(os.path.join(P["data"], "images.json"), "w", encoding="utf-8"), indent=1)
    for stem, m in sorted(meta.items(), key=lambda kv: kv[1]["places"][0]["page"]):
        print("  %-6s p%-3d %4dx%-4d  放置 %3.0f pt  有效 %5.1f dpi  %s" % (
            stem, m["places"][0]["page"], m["w"], m["h"], m["places"][0]["rect"][2] - m["places"][0]["rect"][0],
            m["eff_dpi"], "→ 需超分" if m["eff_dpi"] < 150 else ""))
    return meta


# ---------------------------------------------------------------- 检测
def _det_kw(im):
    return (DET_KW_4X, MIN_WH_4X) if im.width >= 1200 else (DET_KW_1X, MIN_WH_1X)


def detect(work, src="figures_sr", stems=None):
    P = _paths(work)
    sdir = os.path.join(work, src) if os.path.isdir(os.path.join(work, src)) else P["src"]
    os.makedirs(P["qa"], exist_ok=True)
    fnt = fontkit.pil("mono-bold", 26)
    boxes = {}
    for f in sorted(os.listdir(sdir)):
        if not f.endswith(".png") or f.endswith("_rgba.png"):
            continue
        stem = f[:-4]
        if stems and stem not in stems:
            continue
        p = os.path.join(sdir, f)
        im = Image.open(p).convert("RGB")
        kw, (mw, mh) = _det_kw(im)
        bs = [b for b in figlabel.detect_raster_labels(p, **kw) if b[2] - b[0] >= mw and b[3] - b[1] >= mh]
        boxes[stem] = [list(map(int, b)) for b in bs]
        d = ImageDraw.Draw(im)
        for i, b in enumerate(bs):
            d.rectangle(b, outline=(255, 0, 0), width=3)
            d.text((b[0], max(0, b[1] - 30)), str(i), font=fnt, fill=(0, 0, 255))
        im.save(os.path.join(P["qa"], "det_%s.png" % stem))
        print("  %s: %d 个文字块 → qa/det_%s.png" % (stem, len(bs), stem))
    json.dump({"src": os.path.basename(sdir), "boxes": boxes},
              open(os.path.join(P["data"], "det_boxes.json"), "w", encoding="utf-8"), indent=1)
    return boxes


def _det(work):
    d = json.load(open(os.path.join(_paths(work)["data"], "det_boxes.json"), encoding="utf-8"))
    return os.path.join(work, d["src"]), d["boxes"]


# ---------------------------------------------------------------- 回叠
def apply(work, LABELS, BUBBLES=None, LIKE=None, font_scale=0.98):
    """并框 → tighten 收紧到文字本体 → 采样底色铺底（两趟：先铺完再写字）→ 同图字号按原文行高中位数统一
    → 按锚点写中文 → 件号气泡按 BUBBLES 在原环心重绘 + 残留判据。大图另存 JPEG q92 4:4:4。"""
    BUBBLES, LIKE = BUBBLES or {}, LIKE or {}
    P = _paths(work)
    sdir, boxes = _det(work)
    os.makedirs(P["out"], exist_ok=True)
    f_reg, f_bold = fontkit.find("zh"), fontkit.find("zh-bold")
    errors, covered, report, breport = [], {}, {}, {}
    for f in sorted(os.listdir(sdir)):
        if not f.endswith(".png") or f.endswith("_rgba.png"):
            continue
        stem = f[:-4]
        im = Image.open(os.path.join(sdir, f)).convert("RGB")
        bs = boxes.get(stem, [])
        lab = LABELS.get(stem, {})
        unl = [i for i in range(len(bs)) if i not in lab]
        if unl:
            errors.append((stem, "未处置框", unl))
        d = ImageDraw.Draw(im)
        cov, rep, plans = [], [], []
        for i in range(len(bs)):
            z = lab.get(i)
            if z in (None, KEEP, SKIP):
                continue
            spec = lab.get(("opt", i), {})
            x0, y0, x1, y1 = bs[i]
            for j in spec.get("union", []):
                bx = bs[j]
                x0, y0, x1, y1 = min(x0, bx[0]), min(y0, bx[1]), max(x1, bx[2]), max(y1, bx[3])
            tb, lh, ok = tightbox.tighten(im, (x0, y0, x1, y1))
            plans.append((i, z, spec, tb, lh))
            cov.append([x0, y0, x1, y1])      # 原检测框整体算已处置（框内保留的引线/箭头不再报漏译）
            rep.append((i, z.replace("\n", "/"), (x0, y0, x1, y1), list(tb), lh, ok))
        lhs = sorted(p[4] for p in plans if p[4])
        base = lhs[len(lhs) // 2] if lhs else 36
        px_default = max(12, int(base * font_scale))
        texts = []
        for i, z, spec, (x0, y0, x1, y1), lh in plans:
            grow = spec.get("grow", 5)
            bg = figlabel.bg_color(im, (x0, y0, x1, y1), grow=grow + 4)
            d.rectangle([x0 - grow, y0 - grow, x1 + grow, y1 + grow], fill=bg)
            cov.append([x0 - grow, y0 - grow, x1 + grow, y1 + grow])
            size = int(spec.get("px", px_default))
            fnt = ImageFont.truetype(f_bold if spec.get("bold") else f_reg, size)
            lines = z.split("\n")
            lhp = int(size * 1.2)
            widths = [d.textbbox((0, 0), ln, font=fnt)[2] for ln in lines]
            tw, th = max(widths), lhp * len(lines)
            anchor = spec.get("anchor", "center")
            lx = x0 if anchor == "left" else (x1 - tw if anchor == "right" else (x0 + x1) / 2 - tw / 2)
            lx = min(max(2, lx + spec.get("dx", 0)), im.width - tw - 2)
            ly = (y0 + y1) / 2 - th / 2 + spec.get("dy", 0)
            pad = 3
            d.rectangle([lx - pad, ly - pad, lx + tw + pad, ly + th + pad], fill=bg)
            cov.append([lx - pad, ly - pad, lx + tw + pad, ly + th + pad])
            texts.append((lines, widths, fnt, lhp, lx, ly, tw, anchor, bg))
        for lines, widths, fnt, lhp, lx, ly, tw, anchor, bg in texts:
            fg = (0, 0, 0) if sum(bg) / 3 >= 140 else (255, 255, 255)
            for k, ln in enumerate(lines):
                w = widths[k]
                tx = lx if anchor == "left" else (lx + tw - w if anchor == "right" else lx + (tw - w) / 2)
                d.text((tx, ly + k * lhp), ln, font=fnt, fill=fg)
        mapping = BUBBLES.get(stem, {})
        for i in mapping:
            if lab.get(i) != KEEP:
                errors.append((stem, "气泡框须标 KEEP", i))
        geos, bcov, bad = bubbles.apply_image(im, bs, {i: t for i, t in mapping.items() if lab.get(i) == KEEP},
                                              LIKE.get(stem, {}))
        cov += [list(r) for r in bcov]
        errors += [(stem, "气泡") + tuple(b) for b in bad]
        for i in range(len(bs)):
            if lab.get(i) in (KEEP, SKIP):
                cov.append(bs[i])
        covered[stem], report[stem] = cov, rep
        breport[stem] = {str(i): {k: (round(v, 1) if isinstance(v, float) else v) for k, v in g.items()
                                  if k in ("cx", "cy", "rout_x", "rout_y", "method", "fit", "residue")} for i, g in geos.items()}
        im.save(os.path.join(P["out"], f))
        if im.width >= 1200:
            im.save(os.path.join(P["out"], stem + ".jpg"), quality=92, subsampling=0, optimize=True)
    for name, obj in (("covered", covered), ("apply_report", report), ("bubble_report", breport)):
        json.dump(obj, open(os.path.join(P["data"], name + ".json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, default=str)
    return errors


def sweep(work, LABELS):
    """成品图上重新检测；落在已处置区（含 KEEP/SKIP 框）之外的文字块即疑似漏译。"""
    P = _paths(work)
    _sdir, boxes = _det(work)
    covered = json.load(open(os.path.join(P["data"], "covered.json"), encoding="utf-8"))
    left_all = {}
    for stem, bs in boxes.items():
        p = os.path.join(P["out"], stem + ".png")
        if not os.path.exists(p):
            continue
        kw, (mw, mh) = _det_kw(Image.open(p))
        left = figlabel.sweep(p, covered.get(stem, []), out_path=os.path.join(P["qa"], "sweep_%s.png" % stem),
                              min_w=mw, min_h=mh, **kw)
        if left:
            left_all[stem] = left
            print("  %s: 未处置文字块 %d → qa/sweep_%s.png" % (stem, len(left), stem))
    return left_all


def sheet(work, BUBBLES):
    P = _paths(work)
    _sdir, boxes = _det(work)
    out = os.path.join(P["qa"], "bubbles.png")
    bubbles.sheet(P["out"], BUBBLES, boxes, out)
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "extract":
        extract(sys.argv[2], sys.argv[3])
        return 0
    work = sys.argv[2]
    if cmd == "detect":
        src = sys.argv[sys.argv.index("--src") + 1] if "--src" in sys.argv else "figures_sr"
        detect(work, src)
        return 0
    LABELS, BUBBLES, LIKE, FS = _load_labels(sys.argv[3])
    if cmd == "apply":
        errs = apply(work, LABELS, BUBBLES, LIKE, font_scale=FS)
        for e in errs:
            print("  ERR", e)
        print("回叠完成：%s" % ("无错误" if not errs else "%d 处错误" % len(errs)))
        return 1 if errs else 0
    if cmd == "sweep":
        left = sweep(work, LABELS)
        print("漏译排查：%s" % ("0 处" if not left else "%d 处" % sum(len(v) for v in left.values())))
        return 1 if left else 0
    if cmd == "sheet":
        print("气泡拼贴：", sheet(work, BUBBLES))
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
