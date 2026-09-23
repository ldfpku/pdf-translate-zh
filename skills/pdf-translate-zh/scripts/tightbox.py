# -*- coding: utf-8 -*-
"""检测框收紧到**文字本体**（`tighten`）—— 位图内英文标注回叠前的必经一步。

检测框（`figlabel.detect_raster_labels`，尤其是并框之后）常把引线、箭头头、相邻零件的暗色碎片
一起圈进来。整框描白会抹掉引线（实测 x48 一整条引线被描白）；字号随框走会忽大忽小。
五条规则，每条都对应一次实测失败（figures.md §16.3）：

  ① 细**且长**的连通块（h<9 或 w>4h，且 w≥18）是引线/下划线，剔除；**紧贴**它的小块是箭头头，一并剔除；
  ② 1 px 噪点**不算**引线 —— 早先把 h<9 的一切都当引线，紧邻噪点的字母（"y"、"A"、"i" 的主体）被连坐剔除，
     成品留下 "y"/"A" 残字；
  ③ **不按横长比过滤单个字母** —— "W"/"e"/"n" 横长比 <1.25，按 1.25 过滤就留下 "W"/"e"/"n" 残字；
  ④ 高 >64 px（4 倍超分图）的是图形，剔除；
  ⑤ 合并成行后，行的周边**亮部中位数必须近白**（≥225）——并框伸进彩色零件区时，零件面上的暗色碎片会
     冒充文字把框重新撑大。
返回 ((x0,y0,x1,y1), 行高中位数, 是否成功)。找不到文字形态的块时退回原框（宁大勿漏，英文必须被盖住）。
**字号按行高中位数取**（× 0.9~1.0），不能按框高 —— 两行标注的框高是行高的两倍，字会大一倍。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import numpy as np
from PIL import Image
from scipy import ndimage


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
            out[hit] = (min(g[0], b[0]), min(g[1], b[1]), max(g[2], b[2]), max(g[3], b[3]))
    return out


def _near(a, b, tol):
    return not (a[0] > b[2] + tol or a[2] < b[0] - tol or a[1] > b[3] + tol or a[3] < b[1] - tol)


def tighten(im, box, thr=150, max_h=64, min_line_len=18, white=225):
    """im: PIL 图；box: (x0,y0,x1,y1) 像素框（4 倍超分图口径：字高 ≈ 32~44 px）。"""
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, x1), min(im.height, y1)
    g = np.array(im.crop((x0, y0, x1, y1)).convert("L"))
    lbl, _n = ndimage.label(g < thr, structure=np.ones((3, 3)))
    comps, lines_art = [], []
    for sl in ndimage.find_objects(lbl):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        bb = (xs.start, ys.start, xs.stop - 1, ys.stop - 1)
        if h > max_h:
            continue
        if (h < 9 and w >= min_line_len) or (w > 4 * h and w >= min_line_len):
            lines_art.append(bb)
            continue
        if h < 9 or h * w < 20:
            continue
        comps.append(bb)
    comps = [c for c in comps if not any(_near(c, e, 3) for e in lines_art)]
    cands = []
    for b in _merge(comps, 6, 30):
        if not (16 <= b[3] - b[1] <= max_h):
            continue
        X0, Y0 = max(0, b[0] - 8), max(0, b[1] - 8)
        X1, Y1 = min(g.shape[1], b[2] + 9), min(g.shape[0], b[3] + 9)
        reg = g[Y0:Y1, X0:X1]
        bright = reg[reg > 100]
        if len(bright) and np.median(bright) < white:
            continue
        cands.append(b)
    if not cands:
        return (x0, y0, x1, y1), None, False
    hs = sorted(b[3] - b[1] for b in cands)
    nx0 = min(b[0] for b in cands) + x0 - 2
    ny0 = min(b[1] for b in cands) + y0 - 2
    nx1 = max(b[2] for b in cands) + x0 + 3
    ny1 = max(b[3] for b in cands) + y0 + 3
    return (max(x0, nx0), max(y0, ny0), min(x1, nx1), min(y1, ny1)), hs[len(hs) // 2], True


if __name__ == "__main__":
    import sys
    im = Image.open(sys.argv[1])
    print(tighten(im, tuple(int(v) for v in sys.argv[2:6])))
