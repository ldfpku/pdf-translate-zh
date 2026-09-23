# -*- coding: utf-8 -*-
"""裁框净空（figure-crop clearance）—— 图与图题之间不许留残迹。

**根因**：裁一幅图有三个坐标来源（位图 bbox、矢量簇并集、标注外扩），
三者都只描述「图画到哪里」，**没有一个知道英文图题在哪里**。再各加几 pt
余量，裁框就顺势吃进图题顶端几 pt —— 成品上是一条「Figure 4-7」的上半截
横在中文图题正上方。实测 规范 G 24 幅里 16 幅、规范 H 6 幅里 1 幅中招。

**为什么七道关全绿**：图题是位图，不进文本层；残留英文关扫的是文本层。
⇒ 判据必须回到**源页几何**上做：裁框内不得与任何未处置的文本 span 相交。

⚠ 不能用 `page.get_text(clip=)` 求「框内还有什么字」——MuPDF 对 clip 用的是
   部分包含判据，实测同样是图题顶端：4.8pt 落在框内会返回，2.7pt 就不返回。
   判据自己漏报比没有判据更糟（避坑 59）⇒ 取整页 span 自求矩形相交。
"""
import re
try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

LATIN = re.compile(r"[A-Za-z]{3,}")
# 已含中文的 span 一律不算残留 —— 译文里本就嵌着 TMP／NC／O-ring
# 这类保留原文，实测「标准 TMP 斜向器总成」被当成残留英文，裁框
# 一路收到源高的 52%（判据自己造假阳比没有判据更糟，避坑 59）。
CJK = re.compile("[" + chr(0x4e00) + "-" + chr(0x9fff) + chr(0x3000) + "-" + chr(0x303f) + chr(0xff00) + "-" + chr(0xffef) + "]")


def spans(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                if s["text"].strip():
                    out.append(s)
    return out


def residual(page, clip, keep=None, _spans=None):
    """裁框内残留的英文 span：[(文本, rect, 交叠比例), ...]。

    `keep` 是**允许留在图内的原文**正则（商标、代号、实物上的字）。
    """
    kp = re.compile(keep) if keep else None
    out = []
    for s in (_spans if _spans is not None else spans(page)):
        t = s["text"].strip()
        if not t or not LATIN.search(t) or CJK.search(t) or (kp and kp.search(t)):
            continue
        r = fitz.Rect(s["bbox"])
        if r.intersects(clip):
            out.append((t, r, (r & clip).get_area() / max(r.get_area(), .01)))
    return out


def clearance(page, clip, keep=None, minfrac=0.55, eps=0.5, rounds=4):
    """把裁框向内收到不含任何残留英文，返回 (新框, 被让开的文本, 警告)。

    只在**离框心近的那一侧**收 —— 图题在下就抬底边，上一条图题在上就压顶边。
    收得比 `minfrac` 还狠说明这个框本身就定错了（比如整段正文压在图上），
    此时照收但把警告抛给调用方，不静默（避坑 59）。
    """
    sp = spans(page)
    c = fitz.Rect(clip)
    moved, warn = [], []
    h0, w0 = c.height, c.width
    for _ in range(rounds):
        res = residual(page, c, keep, _spans=sp)
        if not res:
            break
        for t, r, _ov in res:
            cy = (r.y0 + r.y1) / 2.0
            cx = (r.x0 + r.x1) / 2.0
            # 先动 y：图题、正文都在图的上下方，横向让位会切掉图形
            if r.x0 <= c.x0 + 1 and r.x1 >= c.x1 - 1 or not (
                    cx < c.x0 or cx > c.x1):
                if cy < (c.y0 + c.y1) / 2.0:
                    ny = min(r.y1 + eps, c.y1)
                    if ny > c.y0:
                        c.y0 = ny
                else:
                    ny = max(r.y0 - eps, c.y0)
                    if ny < c.y1:
                        c.y1 = ny
            else:
                if cx < (c.x0 + c.x1) / 2.0:
                    c.x0 = min(r.x1 + eps, c.x1)
                else:
                    c.x1 = max(r.x0 - eps, c.x0)
            moved.append(t)
    if h0 and c.height < minfrac * h0:
        warn.append("裁框高度收到 %.0f%%（%.1f→%.1f）" % (100 * c.height / h0, h0, c.height))
    if w0 and c.width < minfrac * w0:
        warn.append("裁框宽度收到 %.0f%%（%.1f→%.1f）" % (100 * c.width / w0, w0, c.width))
    return c, moved, warn


def zh_extent(page, fontnames=("zhb",)):
    """本页**新插入的中文**的墨迹范围 —— 裁框至少要盖住它。

    中文比英文短窄是常态，但「（与斜向器背面齐平）」这类整句会比原文宽；
    裁框是按**英文** span 算的，不撑开就会把中文切掉半个字。
    """
    box = None
    for s in spans(page):
        if s["font"] not in fontnames and not any(f in (s["font"] or "") for f in fontnames):
            continue
        r = fitz.Rect(s["bbox"])
        box = r if box is None else (box | r)
    return box
