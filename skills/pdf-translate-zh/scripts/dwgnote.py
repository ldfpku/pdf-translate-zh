# -*- coding: utf-8 -*-
"""工程图标题栏「除另有规定外」注记格的**标准重排**。

为什么不能叠印
--------------
这一格是**格式固定的样板注记**，三条特性让逐行叠印必然出错：

  ① **换行是物理的，不是语义的。** `FINISH: 125∨ MAX.; 63∨ ON ALL` 与
     下一行 `THREADS & RELIEF SURFACES.` 是**一句话**，被行边界切成两个
     待译单元，各自成句译出 —— 成品上读作「…适用于全部」「螺纹与退刀面。」
     两截。末句 `ALL UNSPECIFIED DIAMETERS TO / BE WITHIN .005 TIR.` 同理，
     且第二截为塞进原行框被缩到极小，挤压变形。
  ② **列对齐靠前导空格。** 源里就是
     `'                            .XX     .010'`，
     待译键一归一空白（keyclean 必做），`.XXX/.XX/.X` 的小数点对齐全丢。
  ③ **`±`、`°`、粗糙度 ∨ 是矢量，不在文本层。** 词表若在译文里补一个
     `±`，就与原矢量重影（实测「±2°-0′ **±** °」）；不补则整列没有 `±`。

⇒ 整格抹掉重排。`±`／`°`／`′` 一律改用真文字（雅黑齐备），
列对齐用 `reflow` 的 `("cols", …)` 定列块，偏移以 em 计随字号缩放。

公差值**逐图解析**，不写死 —— 实测 0019 是 `.X ±.040`、0032 是 `±.030`。
"""
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

import reflow

# 注记正文的字号上限：原版 5.9pt，中文同号偏挤，交给自动降号定
HI, LO = 6.6, 4.4

_KEYS = ("UNLESS OTHERWISE", "DIMENSIONS ARE IN", "FINISH", "THREADS & RELIEF",
         "BREAK ALL SHARP", "REMOVE ALL BURRS", "TOLERANCE", "ANGULAR",
         "DECIMAL", "FRACTIONAL", "UNSPECIFIED DIAMETERS", "BE WITHIN",
         ".XXX", ".XX", ".X")


def _note_lines(page):
    """注记格里的文本行 [(rect, 文本, 字号)]。按内容认，不按坐标认。

    **必须带字号**：粗糙度那两个数是 3.9pt 的小字，而正文 5.9pt ——
    靠**行高**区分它们会失手（实测行高 5.47 vs 阈值 5.4，差 0.07pt）。
    行高受升降部影响，字号才是那个稳定量。
    """
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            # 按**字号**把一行切成若干段：MuPDF 有时把浮在行上方的粗糙度小字
            # （3.9pt 的 `125`、`32`）并进 `FINISH: … MAX.; … ON ALL` 这一行
            # （实测随 CAD 导出方式而异），整行文本不再是纯数字，parse() 就认不出
            # 粗糙度值，成品上整句「表面粗糙度…」静默消失。
            groups = []
            for sp in ln["spans"]:
                if groups and abs(sp["size"] - groups[-1][-1]["size"]) < 0.8:
                    groups[-1].append(sp)
                else:
                    groups.append([sp])
            for g in groups:
                t = "".join(s["text"] for s in g)
                if not t.strip():
                    continue
                sz = max(s["size"] for s in g)
                if sz > 7.4:                       # 注记全是 4~6.7pt 的小字
                    continue
                r = fitz.Rect(g[0]["bbox"])
                for s in g[1:]:
                    r |= fitz.Rect(s["bbox"])
                out.append((r, t, sz))
    if not any("UNLESS OTHERWISE" in t.upper() for _r, t, _z in out):
        return []
    # 以 UNLESS 行为锚，取其左界与 y 起点，收同一栏内、其下的行
    anc = next(r for r, t, _z in out if "UNLESS OTHERWISE" in t.upper())
    keep = []
    for r, t, z in out:
        if r.y1 < anc.y0 - 1 or r.x0 < anc.x0 - 6 or r.x0 > anc.x0 + 90:
            continue
        if r.y0 > anc.y0 + 130:
            continue
        keep.append((r, t, z))
    keep.sort(key=lambda q: (round(q[0].y0, 1), q[0].x0))
    # 末行之后不再有注记内容：截到最后一个关键词行
    last = 0
    for i, (_r, t, _z) in enumerate(keep):
        if any(k in t.upper() for k in _KEYS):
            last = i
    return keep[:last + 1]


def _cell(page, rows):
    """注记格的**内框**：由文本两侧最近的竖线定左右界，再内缩留住框线。

    框线在这类图纸上常被导成**许多短段**（0032 全图 16,438 条路径），
    找不到「一个矩形」—— 只能按线段找。
    """
    tb = rows[0][0]
    for r, _t, _z in rows[1:]:
        tb = tb | r
    xs = []
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.width < 0.9 and r.height > 20 and r.y0 < tb.y1 and r.y1 > tb.y0:
            xs.append((r.x0 + r.x1) / 2.0)
        for it in d["items"]:
            pts = [q for q in it[1:] if isinstance(q, fitz.Point)]
            for a, b in zip(pts, pts[1:]):
                if abs(a.x - b.x) < 0.4 and abs(a.y - b.y) > 20 \
                        and min(a.y, b.y) < tb.y1 and max(a.y, b.y) > tb.y0:
                    xs.append(a.x)
    left = max([x for x in xs if x < tb.x0 - 0.5] or [tb.x0 - 3.0])
    right = min([x for x in xs if x > tb.x1 + 0.5] or [tb.x1 + 3.0])
    return fitz.Rect(left + 1.4, tb.y0 - 2.6, right - 1.4, tb.y1 + 2.6)


def parse(page):
    """解析注记格 → (clip, 数据)。认不出返回 (None, None)。"""
    rows = _note_lines(page)
    if len(rows) < 6:
        return None, None
    txt = " ".join(" ".join(t.split()) for _r, t, _z in rows)
    d = {}
    # 粗糙度的两个数**浮在行上方**（3.9pt，y 比 `FINISH:` 那行还小），
    # 按 y 排序时会跑到 `FINISH:` **前面** —— 拿 `FINISH:\s*(\d+)` 去搜
    # 永远搜不到。改按「注记里字号明显更小的纯数字」取，按 x 排序。
    body = max((z for _r, t, z in rows if len(t.strip()) > 6), default=6.0)
    tiny = sorted((r.x0, t.strip()) for r, t, z in rows
                  if t.strip().isdigit() and z < body * 0.85)
    d["fin1"] = tiny[0][1] if len(tiny) > 0 else None
    d["fin2"] = tiny[1][1] if len(tiny) > 1 else None
    # 角度可能带小数（0032 作 `0.5 - 0'`），整数模式认不出
    m = re.search(r"ANGULAR[:.]?\s*([\d.]+)\s*[-–]\s*([\d.]+)", txt, re.I)
    d["ang"] = (m.group(1), m.group(2)) if m else None
    d["dec"] = re.findall(r"(\.X{1,3})\s+(\.\d+)", txt)
    m = re.search(r"FRACTIONAL[:.]?\s*(\d+\s*/\s*\d+)", txt, re.I)
    d["frac"] = m.group(1).replace(" ", "") if m else None
    m = re.search(r"BE WITHIN\s*(\.\d+)\s*TIR", txt, re.I)
    d["tir"] = m.group(1) if m else None
    return _cell(page, rows), d


# 列偏移（em）：标签列 0、规格列 C1、数值列 C2。
# 原版三列的相对位置就是这个量级；以 em 计，字号一降列距同比收窄。
C1, C2 = 6.4, 10.4


def blocks(d):
    """由解析结果生成中文块 DSL。缺项自动跳过 —— 各图内容略有出入。"""
    out = [("p", "除另有规定外：", {"b": True, "before": 0.0}),
           ("p", "尺寸单位为英寸", {"before": 0.18})]
    if d.get("fin1") and d.get("fin2"):
        # ①：整句合并译出，绝不按物理换行切开
        out.append(("p", f"表面粗糙度：最大 {d['fin1']} µin；"
                         f"螺纹与退刀面 {d['fin2']} µin。", {"before": 0.18}))
    out += [("p", "所有尖角均须倒钝。", {"before": 0.18}),
            ("p", "去除全部毛刺。", {"before": 0.18}),
            ("p", "公差：", {"b": True, "before": 0.30})]
    if d.get("ang"):
        a, b = d["ang"]
        out.append(("cols", [(0, "角度："), (C2, f"± {a}°-{b}′")]))
    for i, (spec, val) in enumerate(d.get("dec") or []):
        lab = "小数：" if i == 0 else ""
        out.append(("cols", [(0, lab), (C1, spec), (C2, f"± {val}")]))
    if d.get("frac"):
        out.append(("cols", [(0, "分数："), (C2, f"± {d['frac']}")]))
    if d.get("tir"):
        # ③：末句一句话排完，由引擎按可用宽折行，不再逐行各自缩号
        out.append(("p", f"凡未注明的直径，全跳动均须在 {d['tir']} 以内。",
                    {"before": 0.30}))
    return out


def fix(page, src_page=None, verbose=False):
    """重排本页注记格。`src_page` 为**源页**，缺省时按本页解析。

    ⚠ 装配流程里**必须传源页**：成品页上英文早已换成中文，
    `UNLESS OTHERWISE SPECIFIED` 这些锚点一个都不在，解析必然失败
    （返回 False 而**不报错**，看着像"跳过了这一页"）。
    """
    clip, d = parse(src_page if src_page is not None else page)
    if clip is None:
        return False, 0.0
    opts = {"lead": 1.28, "hi": HI, "lo": LO, "step": 0.1,
            "bx": clip.x0 + 1.0}
    # `lineart=True`：把格内的 ±／°／∨ 矢量一并抹掉（它们**完全落在** clip
    # 内），改由文字重出；而格子的**边框**跨在 clip 之外，不会被删。
    size, _h, over = reflow.render(page, clip, blocks(d), opts,
                                   lineart=True, verbose=False)
    if verbose:
        print(f"    注记格 p{page.number + 1}  {size:.1f}pt"
              + ("  溢出!" if over else ""))
    return True, size


def fix_doc(doc, src_doc, verbose=False):
    """`src_doc` 是源 PDF —— 逐页配对解析。返回处理的页数。"""
    n = 0
    for i, pg in enumerate(doc):
        if i >= src_doc.page_count:
            break
        ok, _s = fix(pg, src_doc[i], verbose)
        n += 1 if ok else 0
    return n
