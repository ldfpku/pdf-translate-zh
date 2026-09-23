# -*- coding: utf-8 -*-
"""图纸族 J 图纸的明细表（BOM）抽取 —— 按线框几何，不靠 find_tables。

为何不能用 find_tables：这类 D 号图纸上它会把**整张图纸**误判成一个大表
（整页文字挤在 r00 一格里），顺带把明细表的 NOTES 列吞掉 ——
tables_raw.json 里页 1 的明细表只剩 4 列，而原版有 5 列。

为何不能用 get_drawings() 的 rect：该 PDF 的线条是**路径内的 item**，
一条路径可含上百个 item，其 rect 是整条路径的包围盒。
必须下潜到 dr["items"] 逐个取 "l"（线段）与 "re"（矩形）。

实测（图纸 J-1 页 1）：
    明细表外框  x=36.3~727.0   y=620.3~735.5
    行线        620.3 / 634.7 / … / 735.5，行高 14.4pt
    列边界      36.3 | 80.3 | 153.9 | 429.3 | 470.7 | 727.0
                （ITEM # | PART # | PART NAME | QTY | NOTES）
**ITEM # 与 QTY 两列的部分行线缺失 —— 那正是纵向合并的编码方式**
（一个件号对应 BORED/SOLID 两种可选件时，件号与数量只写一次）。
本模块据此还原合并区间，不可把它拆成两行各写 1。

    python dwg_bom.py <src.pdf>
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import sys

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz


def _norm(s):
    return " ".join(str(s or "").split())


def segments(page, min_h=30.0, min_v=8.0):
    """下潜到路径 item，取出全部水平/垂直线段。"""
    H, V = set(), set()

    def add(x0, y0, x1, y1):
        if abs(y1 - y0) < 0.6 and abs(x1 - x0) >= min_h:
            H.add((round(y0, 1), round(min(x0, x1), 1), round(max(x0, x1), 1)))
        if abs(x1 - x0) < 0.6 and abs(y1 - y0) >= min_v:
            V.add((round(x0, 1), round(min(y0, y1), 1), round(max(y0, y1), 1)))

    for dr in page.get_drawings():
        # **退化路径整条即一条线**：CorelDRAW 导出的直线常被写成
        # `l` + 若干 `c`（控制点共线的贝塞尔）。逐 item 取只能得到几个
        # 零长小段，`_coalesce` 也接不起来 —— 实测 手册 E 第 6 页零件表的
        # 5 条列线（x=349/373/513/566/590，y 67~502）就是这样整条丢掉的，
        # 表格因此一个行带都定不出列。
        # 路径 bbox 若在某个方向退化成 0 宽，它本身就是那条线。
        r = fitz.Rect(dr["rect"])
        if r.width < 0.6 or r.height < 0.6:
            add(r.x0, r.y0, r.x1, r.y1)
            continue
        for it in dr.get("items", []):
            if it[0] == "l":
                add(it[1].x, it[1].y, it[2].x, it[2].y)
            elif it[0] == "re":
                r = fitz.Rect(it[1])
                add(r.x0, r.y0, r.x1, r.y0)
                add(r.x0, r.y1, r.x1, r.y1)
                add(r.x0, r.y0, r.x0, r.y1)
                add(r.x1, r.y0, r.x1, r.y1)
    return _coalesce(H), _coalesce(V)


def _coalesce(segs, gap=1.5):
    """把同一条直线上首尾相接/重叠的短段并成一段。

    各图纸的导出方式不同：多数把一条框线导成一条 line，
    而 图纸 J-2 把整张图导成 16,438 条独立路径，
    框线被切成许多短段 —— 不先合并就找不到任何「贯通」的框线。
    """
    by = {}
    for a, b0, b1 in segs:
        by.setdefault(a, []).append((b0, b1))
    out = set()
    for a, runs in by.items():
        runs.sort()
        cur0, cur1 = runs[0]
        for b0, b1 in runs[1:]:
            if b0 <= cur1 + gap:
                cur1 = max(cur1, b1)
            else:
                out.add((a, round(cur0, 1), round(cur1, 1)))
                cur0, cur1 = b0, b1
        out.add((a, round(cur0, 1), round(cur1, 1)))
    return out


def find_bom(page):
    """明细表外框。

    判据：明细表的**上下两条外框线端点完全相同**（同一 x0、同一 x1），
    位于图纸下部，且宽度明显小于图纸边框（边框会一直画到 x≈1187）。
    不可用「全局最小 x0」定左边界 —— 图纸外还有一条 x0=0 的整页边框线，
    会把左界拉到 0 而与明细表 36.3 对不上。
    """
    H, _ = segments(page)
    if not H:
        return None
    W, Hh = page.rect.width, page.rect.height
    # 不可按 y 过滤**成员**：明细表行数多时上边框会高到版面中部
    # （实测页 3 上边框 y=378.9，页 1 才 620.3）。
    # 只按「该组最低的一条线位于图纸下部」过滤整组。
    groups = {}
    for y, x0, x1 in H:
        w = x1 - x0
        if w < W * 0.25 or x1 > W * 0.9:
            continue
        groups.setdefault((round(x0), round(x1)), []).append(y)
    cand = [(x0, x1, sorted(ys)) for (x0, x1), ys in groups.items()
            if len(ys) >= 2 and max(ys) > Hh * 0.6]
    if not cand:
        return None
    # 取最宽的一组：明细表比标题栏内部的任何分格都宽
    x0, x1, ys = max(cand, key=lambda t: t[1] - t[0])
    return fitz.Rect(x0, ys[0], x1, ys[-1])


def grid(page, rect, tol=2.0):
    """明细表的行线 y 列表与列边界 x 列表（由线段端点聚类求得）。"""
    H, V = segments(page, min_h=20.0, min_v=6.0)
    ys = sorted({h[0] for h in H
                 if rect.y0 - tol <= h[0] <= rect.y1 + tol
                 and h[1] >= rect.x0 - tol and h[2] <= rect.x1 + tol})
    xs = set()
    for h in H:
        if rect.y0 - tol <= h[0] <= rect.y1 + tol:
            for v in (h[1], h[2]):
                if rect.x0 - tol <= v <= rect.x1 + tol:
                    xs.add(round(v, 1))
    for v in V:
        if v[2] > rect.y0 and v[1] < rect.y1 and rect.x0 - tol <= v[0] <= rect.x1 + tol:
            xs.add(round(v[0], 1))

    def merge(vals):
        out = []
        for x in sorted(vals):
            if out and x - out[-1] <= tol:
                continue
            out.append(x)
        return out

    return merge(ys), merge(xs)


def cells(page, rect, ys, xs):
    """按行带 × 列带把文字装桶。空串表示该格被上方合并（或本就空白）。"""
    words = page.get_text("words", clip=rect + (-2, -2, 2, 2))
    rows = []
    for r in range(len(ys) - 1):
        y0, y1 = ys[r], ys[r + 1]
        row = []
        for c in range(len(xs) - 1):
            x0, x1 = xs[c], xs[c + 1]
            got = [w for w in words
                   if x0 - 1 < (w[0] + w[2]) / 2 < x1 + 1
                   and y0 - 1 < (w[1] + w[3]) / 2 < y1 + 1]
            got.sort(key=lambda w: (round(w[1], 1), w[0]))
            # 叠印去重（SKILL 避坑 ⑳）：原版常把同一串按不同字号叠印数份，
            # 英文完全重合、肉眼无异常，但按词装桶就成了「O-RING O-RING」。
            # 判据取「文本相同 且 位置相差 < 3pt」，不可按纯文本去重 ——
            # 同一格内本就可能合法地重复同一个词。
            seen, uniq = set(), []
            for w in got:
                k = (w[4], round(w[0] / 3.0), round(w[1] / 3.0))
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(w)
            row.append(_norm(" ".join(w[4] for w in uniq)))
        rows.append(row)
    return rows


def merges(page, rect, ys, xs, tol=1.6):
    """纵向合并：某列在某条行线处**没有**横线段 ⇒ 该格与下一格合并。

    这正是原版编码合并的方式（一个 ITEM # 对应 BORED/SOLID 两种可选件时，
    件号与数量只写一次，故其行线不画）。绝不可拆成两行各写一遍。
    返回 {(列, 行): True} 表示该格向下合并。
    """
    H, _ = segments(page, min_h=8.0, min_v=6.0)
    out = {}
    for c in range(len(xs) - 1):
        cx0, cx1 = xs[c], xs[c + 1]
        for r in range(len(ys) - 2):          # 末行下边界是外框，不判
            y = ys[r + 1]
            has = any(abs(h[0] - y) < tol and h[1] <= cx0 + tol
                      and h[2] >= cx1 - tol for h in H)
            if not has:
                out[(c, r)] = True
    return out


def bom(page):
    """返回 (rect, ys, xs, rows, mg)；rows[0] 为表头。识别不到返回 None。"""
    rect = find_bom(page)
    if rect is None:
        return None
    ys, xs = grid(page, rect)
    if len(ys) < 2 or len(xs) < 3:
        return None
    rows = cells(page, rect, ys, xs)
    mg = merges(page, rect, ys, xs)
    spans = normalize(rows, mg, len(xs) - 1)
    return rect, ys, xs, rows, spans


def normalize(rows, mg, ncol):
    """把纵向合并区间内唯一的那个值归位到区间首行，并返回合并区间清单。

    合并格的文字在原版中垂直居中，跨 3~4 行时会落在**中间**那一行
    （实测件号 8 有 MANDREL/SLICK/IB 三种可选件，「8」落在第 2 行；
    件号 18 有四种，「18」落在第 2 行）。若不归位，重建时会把件号排错行。
    返回 [(列, 起行, 止行), ...]，行号以数据行计（0 = 表头下第一行）。
    """
    out = []
    for c in range(ncol):
        r = 0
        while r < len(rows) - 1:
            if (c, r) not in mg:
                r += 1
                continue
            e = r
            while (c, e) in mg and e < len(rows) - 1:
                e += 1
            vals = [rows[k][c] for k in range(r, e + 1) if rows[k][c]]
            uniq = []
            for v in vals:
                if v not in uniq:
                    uniq.append(v)
            for k in range(r, e + 1):
                rows[k][c] = ""
            rows[r][c] = " ".join(uniq)
            out.append((c, r, e))
            r = e + 1
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    doc = fitz.open(sys.argv[1])
    for i, page in enumerate(doc, 1):
        r = bom(page)
        print(f"\n=== 页 {i} ===")
        if not r:
            print("   未识别到明细表；候选外框组如下（诊断用）：")
            H, _ = segments(page)
            W, Hh = page.rect.width, page.rect.height
            g = {}
            for y, x0, x1 in H:
                if y > Hh * 0.4 and x1 - x0 > W * 0.15:
                    g.setdefault((round(x0), round(x1)), []).append(round(y, 1))
            for k, v in sorted(g.items(), key=lambda t: -(t[0][1] - t[0][0]))[:8]:
                print(f"      x={k}  宽={k[1]-k[0]}  y={sorted(v)}")
            continue
        rect, ys, xs, rows, spans = r
        print(f"   外框 {[round(v,1) for v in rect]}")
        print(f"   行线 {ys}")
        print(f"   列界 {xs}")
        for ri, row in enumerate(rows):
            tag = "".join("|" if any(s[0]==c and s[1]<ri<=s[2] for s in spans) else " " for c in range(len(xs)-1))
            print(f"   [{tag}] | " + " | ".join(c if c else "·" for c in row))
    doc.close()


if __name__ == "__main__":
    main()
