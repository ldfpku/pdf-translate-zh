# -*- coding: utf-8 -*-
"""在粗框内取**全部深色像素的包围盒** —— 比连通块分析稳得多。

`vectext.snap()` 走的是连通块 + 同行合并，对**下采样过的位图小字**不稳：
实测 手册 A 第 11 页 26 条标注里有 24 条只吸附到单个字符（2~3pt 宽）。
本函数换一条更笨也更可靠的路：粗框内本来只有那一条标注、其余是白底，
所以「框内所有深像素的包围盒」就是标注框。前提是**粗框不能碰到插图**。
"""
try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz


def inkbox(page, rough, dpi=220, thresh=170, pad=0.6):
    R = fitz.Rect(rough)
    z = dpi / 72.0
    pm = page.get_pixmap(clip=R, matrix=fitz.Matrix(z, z), colorspace=fitz.csGRAY)
    w, h, sm = pm.width, pm.height, pm.samples
    xs0, ys0, xs1, ys1 = w, h, -1, -1
    for y in range(h):
        row = sm[y * pm.stride:y * pm.stride + w]
        for x in range(w):
            if row[x] < thresh:
                if x < xs0:
                    xs0 = x
                if x > xs1:
                    xs1 = x
                if y < ys0:
                    ys0 = y
                if y > ys1:
                    ys1 = y
    if xs1 < 0:
        return None
    return fitz.Rect(R.x0 + xs0 / z - pad, R.y0 + ys0 / z - pad,
                     R.x0 + (xs1 + 1) / z + pad, R.y0 + (ys1 + 1) / z + pad)
