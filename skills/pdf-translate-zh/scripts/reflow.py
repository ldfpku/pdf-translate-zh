# -*- coding: utf-8 -*-
"""**标准重排通道** —— 叠印路线的第四条通道（前三条见 `hybrid_overlay`）。

叠印把每条原文单元写回原坐标，同源感最好；但**原版自身版式不佳**时，
中文会照单全收：

  · 「Step 1:」的续行比首行还深（英文首行短、续行另起一个缩进级）；
  · 同一页示例 1 用 8pt、示例 2 用 11pt（原版就是这么排的）；
  · 分数式的分母是独立文本行，行距一变就掉到别处，横线穿字而过；
  · 无序列表的项目符号各行 x 不一，圆点大小随字号变。

这些**不是叠印的 bug，是原版版式本身**。当要求「按标准文本／标准列表／
标准表格重排，不必与原版缩进一致」时，就改用本通道：
**整块抹掉，按块 DSL 重新排版**。

块 DSL
------
    ("h",  文本[, opts])        小标题（默认粗体）
    ("p",  文本[, opts])        段落
    ("li", 文本[, 层级])         无序列表项，层级 1/2
    ("dt", 标签, 文本[, opts])   悬挂标签（「第 1 步：」「注意：」）
    ("kv", 标签, 数值)           左标签 + 右对齐数值（算式的数值列）
    ("rule",)                   合计横线，画在数值列上方
    ("gap", 倍数)               垂直空白 = base × 倍数
    ("tbl", spec)               真网格表格

opts（每块可选）：`b` 粗体、`a` 对齐(0左 1中 2右)、`i` 首行缩进倍数、
`s` 字号倍数、`x` 左边界绝对值。

区域 opts：`lead` 行距倍数、`ind` 悬挂缩进、`bullet` 项目符号、
`kvx` 数值列右边界、`lo`/`hi` 字号搜索区间。

**字号在整个区域内统一**：先按 `hi` 试排，放不下就 −0.2 再试，
直到装进 clip。这正是「同页字号忽大忽小」的解 —— 不是逐条取最大，
而是**全区域取同一个能装下的值**。
"""
try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

from dwg_overlay import ZH_FONT, ZH_FONT_B, _width

BULLET = "•"

# 目录行的矩形，由 `("toc", …)` 块填充：[(rect, 页码, 标题, 层级), …]
# 每次 `render()` 开头清空 —— 调用方在 render() 之后立刻取走用于加跳转链接。
LINKS = []
# `run()` 跨区域**累积**的同一份数据。目录分成多个区域时（双栏、跨页），
# `render()` 的逐次清空会让 `LINKS` 只剩最后一个区域的条目 ——
# 实测 手册 I 双栏目录 52 条只建出 13 条链接，且六道关一处不报
# （链接是注记，不进文本层）。`run()` 开头清空一次，之后只追加。
ALL_LINKS = []

_FB = None


def _widthb(t, s):
    """粗体度量 —— 与 msyhbd 同源；缺字体时按常规体 ×1.03 估。"""
    global _FB
    if _FB is None:
        try:
            _FB = fitz.Font(fontfile=ZH_FONT_B)
        except Exception:
            _FB = False
    return _FB.text_length(t, fontsize=s) if _FB else _width(t, s) * 1.03


def _w(t, s, bold=False):
    return _widthb(t, s) if bold else _width(t, s)


def _wrap(text, size, avail, bold=False):
    """按中文禁则折行；粗体用粗体度量，否则粗标题会溢出半个字。"""
    import hybrid_overlay as hy
    if not bold:
        return hy._cjkwrap(text, size, avail).split("\n")
    # 粗体略宽：按宽度比缩窄可用宽度后再折，避免用常规度量算「放得下」
    k = max(0.80, min(1.0, _width(text, size) / max(_widthb(text, size), 0.1)))
    return hy._cjkwrap(text, size, avail * k).split("\n")


# ── 版面测算与绘制 ────────────────────────────────────────────────
def _runs(blocks, kind):
    """把连续同类块切成「运行段」，返回 {块下标: 运行段下标}。

    `dt` 的悬挂宽度、`kv` 的横线长度都要**在同一运行段内取齐** ——
    逐条各算各的，就又回到「每行缩进都不一样」的老样子。
    """
    out, cur = {}, []
    runs = []
    for i, b in enumerate(blocks):
        if b[0] == kind:
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    for ri, r in enumerate(runs):
        for i in r:
            out[i] = ri
    return out, runs


def _cellsize(cell):
    return cell if isinstance(cell, dict) else {"t": str(cell)}


def _atom_floor(spec, ncol, size, pad):
    """每列的**不可断记号下限**（见 zhlib.ATOM_RE）。

    日期、零件号、标准号、尺寸这类工程标识断开即改变含义。叠印路线的
    `_cjkwrap` 不会从记号中间断（拉丁词只在空格处断），但列给窄了它会
    **溢出**到邻列 —— 症状不同，根因一样：分列时没把记号宽度算进去。
    """
    try:
        from zhlib import atoms
    except Exception:
        return [0.0] * ncol
    fl = [0.0] * ncol
    for row in spec.get("rows") or []:
        cells = list(row[1:]) if (isinstance(row, (list, tuple)) and row
                                  and row[0] in ("span", "hdr")) else list(row)
        ci = 0
        for cell in cells:
            if ci >= ncol:
                break
            c = _cellsize(cell)
            n = max(1, int(c.get("cs", 1)))
            if n == 1:                       # 跨列单元不参与，摊不到具体某列
                for a in atoms(c.get("t", "")):
                    fl[ci] = max(fl[ci], _width(a, size) + 2 * pad + 0.6)
            ci += n
    return fl


def _tbl_layout(spec, x0, x1, size, lead):
    """表格测算：返回 (列边界 xs, 行高 hs, 行内绘制数据)。"""
    cols = spec.get("cols") or [1.0]
    pad = spec.get("pad", 3.0)
    tot = float(sum(cols))
    W = x1 - x0
    w = [W * c / tot for c in cols]
    # 先保下限，富余再按原比例还回去
    fl = _atom_floor(spec, len(w), size, pad)
    if any(fl) and sum(fl) <= W:
        free = W - sum(fl)
        base = [max(w[i] - fl[i], 0.0) for i in range(len(w))]
        bt = sum(base) or 1.0
        w = [fl[i] + free * base[i] / bt for i in range(len(w))]
    xs = [x0]
    for c in w:
        xs.append(xs[-1] + c)
    xs[-1] = x1

    hs, data = [], []
    for row in spec["rows"]:
        kind = "row"
        if isinstance(row, (list, tuple)) and row and row[0] in ("span", "hdr"):
            kind, cells = row[0], list(row[1:])
        else:
            cells = list(row)
        ncol = len(xs) - 1
        if kind == "span":
            bnd, cells = [(xs[0], xs[-1])], cells[:1] or [""]
            cidx = [0]
        else:
            # 跨列（`{"cs": 2}`）：表头「示例」要横跨「算式」与「结果」两列，
            # 不支持跨列就只能把表头塞进其中一列，另一列空着 —— 一眼假。
            bnd, cidx, ci = [], [], 0
            for cell in cells:
                if ci >= ncol:
                    break
                n = max(1, int(_cellsize(cell).get("cs", 1)))
                j = min(ci + n, ncol)
                bnd.append((xs[ci], xs[j]))
                cidx.append(ci)
                ci = j
            cells = cells[:len(bnd)]
            while ci < ncol:                      # 行内单元少于列数：补空格
                bnd.append((xs[ci], xs[ci + 1]))
                cidx.append(ci)
                cells.append("")
                ci += 1
        rd, h = [], 0.0
        for (cx0, cx1), cell, col in zip(bnd, cells, cidx):
            c = _cellsize(cell)
            avail = cx1 - cx0 - 2 * pad
            bold = bool(c.get("b")) or kind in ("span", "hdr")
            if "num" in c:
                pre = c.get("pre", "")
                prew = _widthb(pre, size) + (size * 0.3 if pre else 0)
                fa = max(avail - prew, size * 3)
                nl = _wrap(c["num"], size * 0.94, fa)
                dl = _wrap(c["den"], size * 0.78, fa)
                h = max(h, (len(nl) + len(dl)) * size * lead + size * 0.5)
                rd.append(("frac", cx0, cx1, pre, nl, dl, prew))
            else:
                pre = c.get("pre", "")
                prew = _widthb(pre, size) + (size * 0.3 if pre else 0)
                lines = _wrap(c.get("t", ""), size, max(avail - prew, size * 2),
                              bold)
                h = max(h, len(lines) * size * lead)
                a = c.get("a", 1 if kind in ("span", "hdr") else
                          (spec.get("align") or [1] * 12)[col])
                rd.append(("txt", cx0, cx1, pre, lines, bold, a, prew))
        h += 2 * pad
        hs.append(max(h, size * lead + 2 * pad))
        data.append((kind, rd))
    return xs, hs, data


def _lay(blocks, clip, base, o):
    """一次测算 + 生成绘制指令。返回 (ops, 总高)。

    ops: ("t", x, ybase, text, bold, size, color) / ("ln", x0, y, x1, w)
         / ("rect", x0,y0,x1,y1, width)
    """
    lead = o.get("lead", 1.55)
    ind = o.get("ind", base * 1.5)
    bul = o.get("bullet", BULLET)
    kvx = o.get("kvx", clip.x1)
    x0, x1 = clip.x0, clip.x1
    ops = []
    y = clip.y0

    dtmap, dtruns = _runs(blocks, "dt")
    dtw = []
    for r in dtruns:
        dtw.append(max(_widthb(blocks[i][1], base) for i in r) + base * 0.55)
    kvmap, kvruns = _runs(blocks, "kv")
    kvw = []
    for r in kvruns:
        kvw.append(max(_width(str(blocks[i][2]), base) for i in r))

    def put(txt, bx, size, bold, color=(0, 0, 0)):
        nonlocal y
        y += size * lead
        ops.append(("t", bx, y - size * 0.30, txt, bold, size, color))

    last_kv_run = [-1]
    for bi, b in enumerate(blocks):
        k = b[0]
        if k == "gap":
            y += base * float(b[1])
            continue
        if k == "rule":
            ri = last_kv_run[0]
            w = (kvw[ri] if 0 <= ri < len(kvw) else base * 5) * 1.18
            y += base * 0.30
            ops.append(("ln", kvx - w, y, kvx, 0.7))
            y += base * 0.22
            continue
        if k == "tbl":
            spec = b[1]
            tx0 = spec.get("x0", x0)
            tx1 = spec.get("x1", x1)
            ts = base * spec.get("s", 0.92)
            tl = spec.get("lead", 1.30)
            y += base * spec.get("before", 0.35)
            xs, hs, data = _tbl_layout(spec, tx0, tx1, ts, tl)
            pad = spec.get("pad", 3.0)
            ty = y
            for (kind, rd), h in zip(data, hs):
                for item in rd:
                    if item[0] == "frac":
                        _, cx0, cx1, pre, nl, dl, prew = item
                        inner0, inner1 = cx0 + pad + prew, cx1 - pad
                        cy = ty + (h - (len(nl) + len(dl)) * ts * tl
                                   - ts * 0.5) / 2.0
                        if pre:
                            ops.append(("t", cx0 + pad,
                                        ty + h / 2.0 + ts * 0.32, pre,
                                        True, ts, (0, 0, 0)))
                        nw = max(_width(t, ts * 0.94) for t in nl)
                        dw = max(_width(t, ts * 0.78) for t in dl)
                        mid = (inner0 + inner1) / 2.0
                        for t in nl:
                            cy += ts * tl
                            ops.append(("t", mid - _width(t, ts * 0.94) / 2.0,
                                        cy - ts * 0.30, t, False, ts * 0.94,
                                        (0, 0, 0)))
                        rw = max(nw, dw) * 1.10
                        cy += ts * 0.25
                        ops.append(("ln", mid - rw / 2.0, cy,
                                    mid + rw / 2.0, 0.6))
                        cy += ts * 0.25
                        for t in dl:
                            cy += ts * tl
                            ops.append(("t", mid - _width(t, ts * 0.78) / 2.0,
                                        cy - ts * 0.26, t, False, ts * 0.78,
                                        (0, 0, 0)))
                    else:
                        _, cx0, cx1, pre, lines, bold, a, prew = item
                        inner0, inner1 = cx0 + pad + prew, cx1 - pad
                        cy = ty + (h - len(lines) * ts * tl) / 2.0
                        if pre:
                            ops.append(("t", cx0 + pad,
                                        ty + h / 2.0 + ts * 0.32, pre,
                                        True, ts, (0, 0, 0)))
                        for t in lines:
                            cy += ts * tl
                            tw = _w(t, ts, bold)
                            tx = (inner0 if a == 0 else
                                  inner1 - tw if a == 2 else
                                  (inner0 + inner1) / 2.0 - tw / 2.0)
                            ops.append(("t", tx, cy - ts * 0.30, t, bold, ts,
                                        (0, 0, 0)))
                # 网格按**实际单元边界**画（跨列单元只有一个框），
                # 不能按列边界一律画满 —— 否则跨列的表头中间会多一条竖线
                for item in rd:
                    ops.append(("rect", item[1], ty, item[2], ty + h, 0.6))
                ty += h
            y = ty + base * spec.get("after", 0.35)
            continue

        opt = b[-1] if isinstance(b[-1], dict) else {}
        size = base * float(opt.get("s", 1.06 if k == "h" else 1.0))
        bold = bool(opt.get("b", k == "h"))
        # 抹除框要盖住原版最左的一列文字，正文却常从更靠右处起排 ——
        # 二者必须分开：`clip.x0` 只管抹，`bx` 管写。写窄抹宽不会留残影，
        # 反过来（把 clip 收到写入位）原版左侧那一列就抹不掉，会露出英文。
        bx = float(opt.get("x", o.get("bx", x0)))

        if k == "h":
            y += base * float(opt.get("before", 0.70))
            for t in _wrap(b[1], size, x1 - bx, bold):
                put(t, bx, size, bold)
            y += base * float(opt.get("after", 0.18))
        elif k == "p":
            y += base * float(opt.get("before", 0.42))
            first = bx + base * float(opt.get("i", 0))
            a = int(opt.get("a", 0))
            avail = x1 - first
            lines = _wrap(b[1], size, avail, bold)
            for j, t in enumerate(lines):
                lx = first if j == 0 else bx
                if a:
                    tw = _w(t, size, bold)
                    lx = (x1 - tw) if a == 2 else (bx + x1 - tw) / 2.0
                put(t, lx, size, bold)
        elif k == "li":
            lvl = int(b[2]) if len(b) > 2 and not isinstance(b[2], dict) else 1
            bx2 = bx + (lvl - 1) * ind
            hang = bx2 + ind
            y += base * float(opt.get("before", 0.30))
            lines = _wrap(b[1], size, x1 - hang, bold)
            for j, t in enumerate(lines):
                put(t, hang, size, bold)
                if j == 0:
                    ops.append(("t", bx2, y - size * 0.30, bul, False,
                                size, (0, 0, 0)))
        elif k == "toc":
            # ("toc", 层级, 标题, 页码)：悬挂缩进 + 点引线 + 右对齐页码。
            # 每行的矩形记进 LINKS，调用方据此加 GOTO 跳转（长文档必备）。
            lvl, title, pno = int(b[1]), b[2], b[3]
            tsz = base * (1.0 if lvl <= 2 else 0.94)
            tb = bool(opt.get("b", lvl <= 2))
            # 缩进按**步长制**：第 n 级左界 = 写入左界 + (n−1) × 步长，
            # 步长 = k × 基准字号（k≈1.6，约 1.5 个汉字宽）。跟着字号缩放，
            # 不写死 16/32pt —— 目录条目多时字号会降，缩进必须同比降。
            tx = bx + (lvl - 1) * o.get("tocind", base * 1.60)
            num = str(pno)
            nw = _width(num, tsz)
            y += base * float(opt.get("before", 0.34 if lvl <= 2 else 0.12))
            gap = base * float(o.get("tocgap", 0.30))
            avail = x1 - tx - nw - base * 0.9
            lines = _wrap(title, tsz, avail, tb)
            for j, t in enumerate(lines):
                put(t, tx, tsz, tb)
                if j == len(lines) - 1:
                    # 点数是整数，取整余量最大一个点宽。若从标题末尾**向右**
                    # 铺点，余量就落在引线右端与页码之间 —— 各行参差正好暴露
                    # 在最显眼的位置。故**右端锚定、向左延伸**，余量留在标题
                    # 一侧（那里本就是空白，看不出来）。
                    dot = _width(".", tsz) or 1.0
                    rend = x1 - nw - gap              # 引线右端锚点
                    used = tx + _w(t, tsz, tb) + gap  # 引线左端下限
                    n = max(2, int((rend - used) / dot))
                    ops.append(("t", rend - n * dot, y - tsz * 0.30, "." * n,
                                False, tsz, (0.35, 0.35, 0.35)))
                    ops.append(("t", x1 - nw, y - tsz * 0.30, num, tb, tsz,
                                (0, 0, 0)))
            LINKS.append((fitz.Rect(tx, y - tsz * 1.05, x1,
                                    y + tsz * 0.28), pno, title, lvl))
        elif k == "licol":
            # 并排短条目（原版把「钻进　测试」这类两两排在一行以省版面）。
            # 拆成一列会让页面拉成又长又窄的一条，反而不像技术手册的做法；
            # 这里按**真正的多列列表**排：列宽等分、项目符号与悬挂缩进列列对齐。
            items = list(b[1])
            nc = int(b[2]) if len(b) > 2 and not isinstance(b[2], dict) else 2
            cw = (x1 - bx) / nc
            y += base * float(opt.get("before", 0.30))
            for r0 in range(0, len(items), nc):
                row = items[r0:r0 + nc]
                wrapped = [_wrap(t, size, cw - ind - base * 0.4, bold)
                           for t in row]
                nl = max(len(t) for t in wrapped)
                ytop = y
                for ci, lines in enumerate(wrapped):
                    y = ytop
                    cx = bx + ci * cw
                    for j, t in enumerate(lines):
                        put(t, cx + ind, size, bold)
                        if j == 0:
                            ops.append(("t", cx, y - size * 0.30, bul, False,
                                        size, (0, 0, 0)))
                y = ytop + nl * size * lead
        elif k == "cols":
            # ("cols", [(列偏移em, 文本[, 对齐]), …])：**一行、多列、定位对齐**。
            # 工程图的公差块靠列对齐表达含义（`.XXX/.XX/.X` 的小数点要成列、
            # `±` 要成列），原版是拿**前导空格**排出来的 —— 空格一归一，
            # 对齐全丢。这里按列偏移写死，且偏移以 em 计，随字号一起缩放。
            items = list(b[1])
            y += base * float(opt.get("before", 0.10))
            y += size * lead
            for it in items:
                dx, t = float(it[0]), str(it[1])
                a = int(it[2]) if len(it) > 2 else 0
                tb2 = bool(it[3]) if len(it) > 3 else bold
                w = _w(t, size, tb2)
                x = bx + dx * base
                if a == 2:
                    x -= w
                elif a == 1:
                    x -= w / 2.0
                ops.append(("t", x, y - size * 0.30, t, tb2, size, (0, 0, 0)))
        elif k == "dt":
            w = dtw[dtmap[bi]]
            hang = bx + w
            y += base * float(opt.get("before", 0.36))
            lines = _wrap(b[2], size, x1 - hang, bold)
            for j, t in enumerate(lines or [""]):
                put(t, hang, size, bold)
                if j == 0:
                    ops.append(("t", bx, y - size * 0.30, b[1], True,
                                size, (0, 0, 0)))
        elif k == "kv":
            last_kv_run[0] = kvmap[bi]
            y += base * float(opt.get("before", 0.16))
            val = str(b[2])
            lines = _wrap(b[1], size, kvx - kvw[kvmap[bi]] * 1.25 - bx)
            for j, t in enumerate(lines):
                put(t, bx, size, False)
                if j == len(lines) - 1:
                    ops.append(("t", kvx - _width(val, size),
                                y - size * 0.30, val, False, size, (0, 0, 0)))
        else:
            raise ValueError("unknown block: %r" % (b[0],))
    return ops, y - clip.y0


# ── 对外接口 ──────────────────────────────────────────────────────
def render(page, clip, blocks, opts=None, erase=True, lineart=False,
           images=False, verbose=False):
    """把 blocks 排进 clip。返回 (采用字号, 实际高, 是否溢出)。"""
    o = dict(opts or {})
    clip = fitz.Rect(clip)
    lo, hi, step = o.get("lo", 6.4), o.get("hi", 11.0), o.get("step", 0.2)

    best, bops, bh = lo, None, None
    s = hi
    while s >= lo - 1e-6:
        del LINKS[:]                       # 每次试排都会重填，只留最后一次
        ops, h = _lay(blocks, clip, s, o)
        if h <= clip.height:
            best, bops, bh = s, ops, h
            break
        s = round(s - step, 2)
    over = bops is None
    if over:                                   # 最小号仍装不下：照最小号排
        del LINKS[:]
        bops, bh = _lay(blocks, clip, lo, o)
        best = lo

    if erase:
        page.add_redact_annot(clip)
        page.apply_redactions(
            images=(fitz.PDF_REDACT_IMAGE_NONE if not images
                    else fitz.PDF_REDACT_IMAGE_REMOVE),
            graphics=(fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED if lineart
                      else fitz.PDF_REDACT_LINE_ART_NONE),
            text=fitz.PDF_REDACT_TEXT_REMOVE)

    page.insert_font(fontname="zh", fontfile=ZH_FONT)
    page.insert_font(fontname="zhb", fontfile=ZH_FONT_B)
    for op in bops:
        if op[0] == "t":
            _, x, yb, t, bold, size, col = op
            if not t:
                continue
            page.insert_text((x, yb), t, fontname="zhb" if bold else "zh",
                             fontsize=size, color=col)
        elif op[0] == "ln":
            _, a, yy, bb, wd = op
            page.draw_line((a, yy), (bb, yy), color=(0, 0, 0), width=wd)
        elif op[0] == "rect":
            _, a, b_, c, d, wd = op
            page.draw_rect(fitz.Rect(a, b_, c, d), color=(0, 0, 0), width=wd)
    if verbose:
        print("    reflow p%d  %.1fpt  h=%.0f/%.0f%s"
              % (page.number + 1, best, bh, clip.height, "  溢出!" if over else ""))
    return best, bh, over


def run(pdf, regions, out=None, verbose=True):
    """`regions` = {1 基页号: [(clip, blocks, opts), …]}；就地增量保存。"""
    doc = pdf if isinstance(pdf, fitz.Document) else fitz.open(pdf)
    bad = []
    del ALL_LINKS[:]
    for pno in sorted(regions):
        pg = doc[pno - 1]
        for reg in regions[pno]:
            clip, blocks = reg[0], reg[1]
            o = reg[2] if len(reg) > 2 else {}
            size, h, over = render(pg, clip, blocks, o,
                                   erase=o.get("erase", True),
                                   lineart=o.get("lineart", False),
                                   verbose=verbose)
            ALL_LINKS.extend(LINKS)
            if over:
                bad.append((pno, size, h, fitz.Rect(clip).height))
    if not isinstance(pdf, fitz.Document):
        if out and out != pdf:
            doc.save(out)
        else:
            doc.saveIncr()
        doc.close()
    return bad
