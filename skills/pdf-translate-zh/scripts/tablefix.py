# -*- coding: utf-8 -*-
"""**表格重建**：定位网格 → 逐格取文 → 译 → 按真表格统一重排渲染。

为什么不能沿用逐格叠印：叠印的「格」来自 MuPDF 的行聚组，而它对表格
并不可靠 —— 同一行的相邻两格常被并成一条（`零件号数量`、`制图BY`），
每格又各自缩号求生，于是同一张表里字号忽大忽小、内容跨列。
这些都是**分格错了**的下游症状，在叠印层面只能一处处打补丁。

本模块换一条路：
  1. **按行带定列** —— 行带取相邻两条水平线之间；该行带的列边界，
     只取**纵向真正穿过这条行带**的竖线。合并单元格因此天然成立
     （被合并的地方没有竖线穿过），不必另写合并检测。
  2. 逐格收词（`get_text("words")`，按词心归格），得到干净的格内文本。
  3. 逐格查词表；查不到就保留原文。
  4. 抹掉全表文字（`PDF_REDACT_LINE_ART_NONE`，线框不动），
     再用**全表统一的字号**重排写入 —— 这是「表内字号一致」的关键：
     字号由「所有格都放得下」反推，而不是每格各自缩。
  5. 对齐按内容定：表头居中加粗；纯数字／编号居中；其余左对齐留 2pt。
"""
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

_NUM = re.compile(r"^[\s\d.,;:/()\[\]+\-–—°'\"×xX#%&*]*$")
# 单字符也算代号：消耗品表的序号列就是 `A` `B` `D` `F`，
# 若要求 2 字符起，该列会被判成「有非代号内容」而整列左对齐，
# 与上方零件表的序号列（居中）不一致。
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9\-./\s]*$")



def regions(page, min_rows=3, min_w=60.0, tol=2.0):
    """页面上的**各张表**（不合并）。

    `hybrid_overlay.table_rects_grid` 会把相交的区域并成一大块 ——
    那对「哪些区域走行级」够用，但表格重建必须**一张表一张表**地做：
    列边界、统一字号都是按单张表算的。故这里按水平线的 x 跨度聚族后
    直接返回各族的 bbox，不做合并。
    """
    from dwg_bom import segments
    H, _V = segments(page, min_h=min_w, min_v=3.0)
    # 图框线（横贯 ≥ 93% 页宽）不是表格线：它会与零件轮廓线同族，再经「后合并」
    # 把明细表并进一个整页大「表」，fix_pages 随即按源页英文整片重写（避坑 118）。
    H = [h for h in H if h[2] - h[1] < 0.93 * page.rect.width]

    def bridged(g, y):
        """上一条行线与本条之间有竖线相连（同一张表的行带必有列线贯通）。

        只按 x 跨度聚族会把「页眉装饰线 + 正文表格」「明细表 + 下方标题栏」并成一张
        （实测）；竖线判据不怕行高 —— 步骤表一行排一段散文也照样连得上。"""
        last = max(g["ys"])
        vs = [(vx, vy0, vy1) for vx, vy0, vy1 in _V
              if g["x0"] - 3 <= vx <= g["x1"] + 3 and vy1 - vy0 >= 4]
        if not vs:
            # 三线表（只有横线、没有列线）：退回旧判据，只加一个行距上限
            return y - last <= 80
        return any(vy0 <= last + 3 and vy1 >= y - 3 for _vx, vy0, vy1 in vs)

    groups = []
    for y, x0, x1 in sorted(H):
        for g in groups:
            if not bridged(g, y):
                continue
            ov = min(g["x1"], x1) - max(g["x0"], x0)
            # **互覆盖**判据（除以较宽者）：页面边框线一根就横贯整页，
            # 用「除以较窄者」会把它并进任何一族，整族的 x 跨度被拉成整页宽，
            # 后面按跨度比例找行线时就一条都认不出来。
            if ov > 0.55 * max(g["x1"] - g["x0"], x1 - x0):
                g["x0"], g["x1"] = min(g["x0"], x0), max(g["x1"], x1)
                g["ys"].append(y)
                break
        else:
            groups.append(dict(x0=x0, x1=x1, ys=[y]))
    out = []
    for g in groups:
        ys = sorted(g["ys"])
        if len(ys) < min_rows:
            continue
        out.append(fitz.Rect(g["x0"] - tol, ys[0] - tol,
                             g["x1"] + tol, ys[-1] + tol))
    # ── 后合并 ──────────────────────────────────────────────────
    # 一张表里既有**全宽**行线（表框、表头）又有**半宽**行线（只跨部分列），
    # 第一趟的「互覆盖」判据会把它们分成两族，于是表区少了最左一列
    # （实测 手册 D 第 6 页零件表：竖线 349/370/515/566/590 本来齐全，
    #  表区却只到 368~578，ITEM 列被切在外面）。
    # 此时页面边框线已因**行数不足**被丢弃，可以安全地按「较窄者」再并一次。
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                ov = min(a.x1, b.x1) - max(a.x0, b.x0)
                vov = min(a.y1, b.y1) - max(a.y0, b.y0)
                if ov > 0.55 * min(a.width, b.width) and vov > -6.0:
                    out[i] = a | b
                    out.pop(j)
                    merged = True
                    break
            if merged:
                break
    # 真表格里必须有字：零件轮廓的「框中框」也会凑够三条水平线，但里面没有文字
    words = page.get_text("words")
    def inside(w, r):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        return r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1
    out = [r for r in out if sum(1 for w in words if inside(w, r)) >= 2]
    out.sort(key=lambda r: (round(r.y0), r.x0))
    return out


def grid(page, clip, min_hfrac=0.45, min_rows=3, grow=36.0,
         main_frac=0.6):
    """返回 [(行带 y0, y1, [列边界 x…])]，按行带自上而下。

    `grow` —— 竖线的**向外扩张搜索量**。`clip` 若来自 `regions()`（按水平线
    x 跨度求的粗框），必须放大着搜；若已经过 `bounds()` 校正，就要收紧到
    ~2pt，否则会把表外的竖线（相邻插图的引出框）当成列边界补进来 ——
    实测 手册 D 第 6 页把 x=321.1 补进第 27 行带，该行带的列元组因此与众不同，
    被 `_headers()` 误判成新子表的表头，整行渲染成加粗居中。
    """
    from dwg_bom import segments
    R = fitz.Rect(clip)
    H, V = segments(page, min_h=8.0, min_v=3.0)
    hs = sorted({round(y, 1) for y, x0, x1 in H
                 if R.y0 - 1 <= y <= R.y1 + 1
                 and min(x1, R.x1) - max(x0, R.x0) >= min_hfrac * R.width})
    ys = []
    for y in hs:
        if not ys or y - ys[-1] > 2.0:
            ys.append(y)
    if len(ys) < min_rows:
        return []
    # 竖线要**向外扩张搜**：表区 bbox 来自水平线的 x 跨度，而一张表里
    # 常有「只跨部分列」的半宽行线；若全宽行线不足 min_rows 条，
    # 表区就会缩到半宽那一段，最外侧的列被切在外面
    # （实测 手册 D 第 6 页：竖线 349/370/515/566/590 齐全，
    #  表区却只到 368~578，ITEM 列丢失）。
    # 竖线还必须**被行线横跨**才算列边界：表旁插图的引出框线纵向很长、
    # 位置又贴着表，只按 x 范围收会被当成列（实测 手册 C 第 6 页 x=321.1
    # 混进 11 个行带，那些行带的列签名因此与众不同，被 `_headers()`
    # 判成表头，整行加粗居中）。行线一条都不跨过它 —— 判据就在这里。
    hl = [(x0, x1) for y, x0, x1 in H
          if R.y0 - 1 <= y <= R.y1 + 1
          and min(x1, R.x1) - max(x0, R.x0) >= min_hfrac * R.width]
    need_c = max(2.0, 0.05 * len(hl))
    G = grow
    vv = [(round(x, 1), y0, y1) for x, y0, y1 in V
          if R.x0 - G <= x <= R.x1 + G and y1 > R.y0 + 2 and y0 < R.y1 - 2
          and sum(1 for a, b in hl if a - 2.0 <= x <= b + 2.0) >= need_c]
    out = []
    for a, b in zip(ys, ys[1:]):
        if b - a < 4.0:
            continue
        xs = sorted({x for x, y0, y1 in vv
                     if y0 <= a + 1.5 and y1 >= b - 1.5})
        cols = []
        for x in xs:
            if not cols or x - cols[-1] > 2.0:
                cols.append(x)
        if len(cols) >= 2:
            out.append((a, b, cols))

    # ── 主列线回补 ──────────────────────────────────────────────
    # 列分隔线常是分段绘出的，某几个行带上恰好断开，那几行的两列就被并成
    # 一格（实测 手册 E 第 6 页：`O-RING` 与 `00100039` 同格，渲染成
    # 「O 形圈00100039」，全表 10 行如此）。
    # **不能**照搬邻近行带的全部列边界 —— 早先试过，DESCRIPTION 列里
    # 有只存在于个别行带的内部竖线，补进来会把 `STATOR, SS100` 从中间切开。
    # 判据收紧为「**贯穿多数行带**的才是主列线」：出现率 < `main_frac`
    # 的竖线是格内装饰，不回补。
    # 回补必须**分子表统计**：一个 region 里常叠着两张表（零件表 + 消耗品表），
    # 混在一起统计会把零件表的列线补进消耗品表，`WRENCH … CATCH RING`
    # 被从 x=515.5 处切成两格。子表按**外边界**（最左/最右列线）归组。
    grp = {}
    for i, (_a, _b, cols) in enumerate(out):
        for k in grp:
            if abs(k[0] - cols[0]) <= 3.0 and abs(k[1] - cols[-1]) <= 3.0:
                grp[k].append(i)
                break
        else:
            grp[(cols[0], cols[-1])] = [i]
    for idx in grp.values():
        cnt = {}
        for i in idx:
            for x in out[i][2]:
                for k in cnt:
                    if abs(k - x) <= 2.0:
                        cnt[k] += 1
                        break
                else:
                    cnt[x] = 1
        main = sorted(k for k, c in cnt.items() if c >= main_frac * len(idx))
        for i in idx:
            a, b, cols = out[i]
            add = [x for x in main if cols[0] + 2.0 < x < cols[-1] - 2.0
                   and all(abs(x - c) > 2.0 for c in cols)]
            if add:
                out[i] = (a, b, sorted(cols + add))
    return out


def bounds(gd):
    """按实际列边界校正表区（`regions()` 的 bbox 可能缺最外侧的列）。

    左右界取**各行带外边界的中位数**，不取全局 min/max ——
    表旁插图的引出框线会被 `grow` 搜进来落到个别行带上（实测 手册 E
    第 6 页 x=321.1 只出现在 2 个行带），按 min 会把表区左界拉到那里，
    该行带的列元组从此与众不同，被 `_headers()` 误判成表头（整行加粗居中）。
    """
    if not gd:
        return None

    def pick(vals, far):
        need = max(2.0, 0.06 * len(gd))
        cnt = {}
        for v in vals:
            for k in cnt:
                if abs(k - v) <= 2.0:
                    cnt[k] += 1
                    break
            else:
                cnt[v] = 1
        ok = [k for k, c in cnt.items() if c >= need] or list(cnt)
        return far(ok)

    lo = pick([cols[0] for _a, _b, cols in gd], min)
    hi = pick([cols[-1] for _a, _b, cols in gd], max)
    return fitz.Rect(lo, gd[0][0], hi, gd[-1][1])


def cells(page, gd, pad=1.0, drop_font=None):
    """把词按格归位，返回 [(rect, 文本, 行号, 列号)]。

    `drop_font` —— 水印字体的正则。格内文本取自**源页**，而源页上的水印
    （手册 B 的 `ACME DRILLING TOOLS`）还在，其字符会按位置落进各格，
    渲染出「66057100 DRILLING」「O 形圈 ACME」这类混入（实测第 47 页 3 处）。
    """
    # 判据要**两条同时成立**：词形属水印词表、且词框有一半以上压在水印
    # 字符框上。只用 span 包围盒不行 —— 水印是斜排的，其轴对齐包围盒是
    # 近 300pt 的大方块，按它删会连带删掉 7 条正常零件名。
    # 只按词形也不行 —— 版权栏里的 `ACME DRILLING TOOLS` 是正文。
    drop, wtok = [], set()
    if drop_font:
        from dwg_overlay import font_char_rects
        pat = re.compile(drop_font, re.I)
        drop = [fitz.Rect(r) for r in font_char_rects(page, drop_font)]
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln["spans"]:
                    if pat.search(sp.get("font", "")):
                        wtok |= set(sp["text"].split())
    # 原版常把同一串**叠印两份**（SKILL 避坑 ⑳）。英文完全重合、肉眼无异常，
    # 到这里却变成 `CATCH CATCH`，键里没有这种重复串，整格必然未命中。
    seen, words = set(), []
    for w in page.get_text("words"):
        k = (round(w[0], 1), round(w[1], 1), w[4])
        if k in seen:
            continue
        seen.add(k)
        if w[4] in wtok:
            wr = fitz.Rect(w[:4])
            cov = sum((wr & d).get_area() for d in drop if wr.intersects(d))
            if cov >= 0.5 * max(wr.get_area(), 0.01):
                continue
        words.append(w)
    out = []
    for ri, (a, b, cols) in enumerate(gd):
        for ci, (x0, x1) in enumerate(zip(cols, cols[1:])):
            r = fitz.Rect(x0 + pad, a + pad, x1 - pad, b - pad)
            ws = [w for w in words
                  if x0 < (w[0] + w[2]) / 2 < x1 and a < (w[1] + w[3]) / 2 < b]
            if not ws:
                continue
            # 分行按**词心纵坐标**聚类，不按基线：同一视觉行里
            # `ROTOR, P100`（有下伸部，底 192.4）与 `(used w/ …)`
            # （无下伸部，底 192.1）底边差得极小，而**换行**处
            # `stator)*` 的底边只比下一行高 2.4pt —— 按基线 ±2.5pt 分行
            # 会把上一行的尾巴并到下一行，且排序后跑到行首，
            # 得到 `(used w/ SS300 stator)* ROTOR, P300 XL` 这种倒序串。
            hgt = sorted(w[3] - w[1] for w in ws)[len(ws) // 2] or 8.0
            ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
            lines, cur = [], [ws[0]]
            for w in ws[1:]:
                mid = sum((x[1] + x[3]) / 2 for x in cur) / len(cur)
                if abs((w[1] + w[3]) / 2 - mid) <= 0.6 * hgt:
                    cur.append(w)
                else:
                    lines.append(cur)
                    cur = [w]
            lines.append(cur)
            lines = [sorted(ln, key=lambda w: w[0]) for ln in lines]
            # **保留行结构**：合并单元格里常一格列着好几条（4 种定子型号），
            # 压成一行后既查不到词表，渲染出来也和原版对不上。
            txt = "\n".join(" ".join(" ".join(w[4] for w in ln).split())
                            for ln in lines)
            out.append((r, txt, ri, ci))
    return out


def _nlines(text, size, avail, font="zh"):
    from dwg_overlay import _width
    n = 0
    for seg in str(text).split("\n"):
        n += max(1, int(_width(seg, size) / max(avail, 1.0)) + 1) \
            if _width(seg, size) > avail else 1
    return max(n, 1)


def _fit(text, box, font, base, floor=5.0, lead=1.30):
    """该格放得下的最大字号。"""
    s = base
    while s > floor:
        if _nlines(text, s, box.width - 2.0, font) * s * lead <= box.height - 0.5:
            return s
        s -= 0.25
    return floor


def _headers(gd, cs):
    """哪几个行带是**表头**。

    这些零件表没有粗体、没有底纹，唯一可靠的信号是结构：
      · 每张（子）表的**第一个行带**是表头 —— 列边界元组一变即换了子表；
      · 子表中途**重复出现**的同一条表头（`ITEM` 再来一次）也是表头。
    不能用「格内无数字」判 —— `A | GREASE | N/A` 一样没有数字。
    """
    first = {}
    for ri, (_a, _b, cols) in enumerate(gd):
        first[ri] = next((t for r, t, i, ci in cs if i == ri and ci == 0), "")
    # 只用**成规模出现**的竖线构成子表签名。表旁插图的引出框线会被搜进
    # 个别行带（实测 手册 E 第 6 页 x=321.1 只在 2 个行带上），签名一变
    # 那行就被当成新子表的表头，整行渲染成加粗居中。
    cnt = {}
    for _a, _b, cols in gd:
        for x in cols:
            for k in cnt:
                if abs(k - x) <= 2.0:
                    cnt[k] += 1
                    break
            else:
                cnt[x] = 1
    need = max(2.0, 0.15 * len(gd))

    def _solid(x):
        return any(abs(k - x) <= 2.0 and c >= need for k, c in cnt.items())

    hdr, prev, cur = set(), None, ""
    for ri, (_a, _b, cols) in enumerate(gd):
        # 列边界按 **1pt 容差** 归一：同一条竖线在不同行带上取到的 x
        # 常差 0.2pt（576.2／576.4），照原值比对会把每一处抖动都当成新子表。
        key = tuple(round(x) for x in cols if _solid(x))
        if key != prev:
            hdr.add(ri)
            cur = first[ri]
        elif cur and first[ri] == cur:
            hdr.add(ri)
        prev = key
    return hdr


def _colalign(gd, items, hdr_rows):
    """**按列**定对齐，不按格。

    同一列里 `润滑脂` 靠左、`LOCTITE 290` 居中（后者被当成代号）——
    一列之内两种对齐，正是用户点名的「对齐不统一」。
    判据：该（子表）列的非表头格**全部**是数字／代号才居中，否则整列左对齐。
    """
    sub, prev = {}, None
    for ri, (_a, _b, cols) in enumerate(gd):
        key = tuple(round(x) for x in cols)
        if key != prev:
            cur = key
        prev = key
        sub[ri] = cur
    ok = {}
    for _r, zh, ri, ci in items:
        if ri in hdr_rows:
            continue
        k = (sub[ri], ci)
        v = bool(_NUM.match(zh)) or bool(_CODE.match(zh))
        ok[k] = ok.get(k, True) and v
    return {ri: sub[ri] for ri in sub}, ok


def _call(fn, text, ctx):
    if fn is None:
        return None
    try:
        return fn(text, ctx)
    except TypeError:
        return fn(text)


def rebuild(page, clip, lookup, base=8.0, floor=5.0, header_rows=None,
            font="zh", fontfile=None, keep=None, src_page=None, page_no=None,
            drop_font=None):
    """重建一张表。返回 (格数, 未命中清单)。

    `src_page` —— **格内文本从源 PDF 取**。成品页上的文字是叠印层写的，
    而叠印层的「行」来自 MuPDF 聚组，同一行相邻两格常已被并成一条并写进
    其中一格（实测 手册 D 第 6 页 `CONSUMABLES`+`PN` → 「零件号 消耗品」
    整条落在最右一格）。从源页取词，分格才是原版的分格。
    线框与网格两边完全一致（叠印不动 line art），坐标可直接通用。
    """
    from dwg_overlay import ZH_FONT, ZH_FONT_B
    gd = grid(page, clip, grow=2.0)
    if not gd:
        return 0, []
    cs = cells(src_page if src_page is not None else page, gd,
               drop_font=drop_font)
    if not cs:
        return 0, []
    hdr_rows = set(range(header_rows)) if header_rows is not None \
        else _headers(gd, cs)
    def _tr(t, ctx, rec=True):
        if keep is not None and _call(keep, t, ctx):
            return t
        zh = _call(lookup, t, ctx)
        if zh is None:
            if rec:
                miss.append(t)
            return None
        return t if not zh.strip() else zh

    miss, items = [], []
    for r, t, ri, ci in cs:
        ctx = (page_no, r)
        zh = _tr(t, ctx, rec="\n" not in t)
        if zh is None and "\n" in t:
            # 先试**整格拼成一句**：格内文字折了行，但语义上是一条
            # （`WRENCH for TOP SUB ROTOR CATCH` / `RING`）。
            zh = _tr(t.replace("\n", " "), ctx, rec=False)
        if zh is None and "\n" in t:
            # 合并单元格：整格查不到就**逐行查**（一格里列着 4 种定子型号，
            # 词表里只有单条，没有把四条粘在一起的键）。
            ln = [_tr(x, ctx, rec=False) for x in t.split("\n")]
            zh = "\n".join(a if a is not None else b
                           for a, b in zip(ln, t.split("\n")))
            if any(a is None for a in ln):
                miss.append(t.replace("\n", " ⏎ "))
        items.append((r, t if zh is None else zh, ri, ci))

    # **全表统一字号**：取「所有格都放得下」的最大值
    size = min(_fit(z, r, font, base, floor) for r, z, _a, _b in items)

    # 抹除按**行带整条**，不按格：叠印层可能把文字写在错误的格里，
    # 甚至略微越出格边；按格抹会留下碎片。行带之间的空当（插图区）
    # 不在抹除范围内，插图安全。
    for a, b, cols in gd:
        page.add_redact_annot(fitz.Rect(cols[0], a, cols[-1], b))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    page.insert_font(fontname=font, fontfile=fontfile or ZH_FONT)
    page.insert_font(fontname=font + "b", fontfile=ZH_FONT_B)

    sub, colnum = _colalign(gd, items, hdr_rows)
    for r, zh, ri, ci in items:
        hdr = ri in hdr_rows
        al = 1 if (hdr or colnum.get((sub[ri], ci), True)) else 0
        fn = font + ("b" if hdr else "")
        s2, rc = size, -1
        while s2 > 3.6:
            # **纵向居中**：单行内容落在行带正中，才像一张排好的表；
            # insert_textbox 从顶部起排，须先把写入框整体下移。
            dy = max(0.0, (r.height - _nlines(zh, s2, r.width - 2.0, font)
                           * s2 * 1.30) / 2.0)
            box = fitz.Rect(r.x0 + (0 if al else 2.0), r.y0 + dy,
                            r.x1, r.y1 + 1.0)
            rc = page.insert_textbox(box, zh, fontname=fn, fontsize=s2,
                                     align=al, lineheight=1.30, color=(0, 0, 0))
            if rc >= 0:
                break
            s2 -= 0.3
    return len(items), miss


def fix_pages(dst, src, pages, lookup, keep=None, base=8.0, drop_font=None):
    """对成品 `dst` 的指定页（0 基）重建表格；格内文本取自源 `src`。

    次序很关键：**必须在叠印之后跑** —— 叠印负责翻译，本模块只重新分格
    与统一字号。逐页开启（不要全局开）：步骤表这类「表里排散文」的页面，
    全表统一字号会把长段落压得过小，须逐页目检后再加。
    """
    d = fitz.open(dst)
    s = fitz.open(src)
    n, miss = 0, []
    for pi in pages:
        if pi >= d.page_count or pi >= s.page_count:
            continue
        pg = d[pi]
        for t in regions(pg):
            gd = grid(pg, t)
            bb = bounds(gd)
            if not bb:
                continue
            c, m = rebuild(pg, bb, lookup, base=base, keep=keep,
                           src_page=s[pi], page_no=pi + 1, drop_font=drop_font)
            n += c
            miss += m
    s.close()
    d.saveIncr()
    d.close()
    return n, miss
