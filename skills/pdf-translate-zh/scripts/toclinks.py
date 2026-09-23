# -*- coding: utf-8 -*-
"""给成品 PDF 的目录加**内部跳转链接**与书签。

叠印路线保留原版版式，目录仍是「标题 …… 页码」的纯文字；
原版本来也没有链接。交付要求可点击跳转，故在成品上补一层链接注记：
按目录行末尾的页码定位目标物理页，给整行加一个 LINK_GOTO。

页码是**印刷页码**，与物理页号差一个前置页偏移（`offset`）；
偏移由调用方给出 —— 各册前置页数不同，猜不得。
"""
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

_ROW = re.compile(r"^(.*?)[.·\u2026\s]{2,}(\d{1,3})\s*$")
# 分节页码：`7-4-2`／`8-2-19`／`5-1`（手册 A 用这一套）——
# 「印刷页 + 偏移」算不出物理页，只能按页眉标签实扫后查表。
_ROW2 = re.compile(r"^(.*?)[.·\u2026\s]{2,}([A-Za-z]?\d+(?:-\d+){0,3})\s*$")
_LBL = re.compile(r"^([A-Za-z]?\d+(?:-\d+){0,3})\s*\|\s*P\s*a\s*g\s*e")
_NUMPFX = re.compile(r"^(\d+(?:\.\d+)*)(?=[\s　]|$)")
_FIGTBL = re.compile(r"^\s*[图表]\s*\d")


def _level(title, prev):
    """由条目编号推层级；无编号的图表条目至少比其所属章节深一级。

    `1.0` 是顶层（尾部的 `.0` 是排版习惯，不是一层），`6.3.1.3.3` 是第 5 层。
    图/表条目严禁与正文章节同级顶格（排版规范 §3.3），故取 prev+1。
    """
    m = _NUMPFX.match(title)
    if m:
        parts = m.group(1).split(".")
        while len(parts) > 1 and parts[-1] == "0":
            parts.pop()
        return len(parts)
    if _FIGTBL.match(title):
        return max(2, prev + 1)
    return 1


def page_labels(doc):
    """扫出每页的**印刷页码标签** → 物理页号（1 基）。

    分节页码（`7-4-2`）无法用「印刷页 + 偏移」算出物理页，只能实扫。
    判据用页眉的 `<标签> | P a g e` 形态（手册 A 全书如此）。
    """
    m = {}
    for i in range(doc.page_count):
        for ln in doc[i].get_text().splitlines():
            g = _LBL.match(" ".join(ln.split()))
            if g:
                m.setdefault(g.group(1), i + 1)
                break
    return m


_CODEROW = re.compile(r"^(.*?)[.·…]{2,}\s*"
                      r"([A-Za-z0-9][A-Za-z0-9 /\-]{2,})$")


def code_links(pdf, toc_pages, out=None, min_title=2, skip=None):
    """**文件编号索引**的跳转（手册 B 一族）。

    这四册的目录右列不是页码，是**文件编号**（`DM6754`／`675G2R PL`／
    `G2R w/ CLAW INSP`）—— 全册是若干分册装订而成，编号才是导航键。
    「印刷页 + 偏移」在这里无从谈起，但每个分册的每一页都印着自己的编号，
    于是「目录条目的编号 → 首个印有该编号的页」就是准确的落点。

    比按页码更稳：分册的页数一改，页码全变，编号不变。
    """
    d = fitz.open(pdf)
    last = max(toc_pages)
    skip = set(skip or ())
    # 编号 → 首个**页眉印着该编号**的物理页。
    #
    # 只认页眉带、且要求那一行**以编号开头** —— 拿整页文本做子串匹配会错两次：
    #   · 短码互相包含：`ASSY` 命中每一个 `DISASSY` 页；
    #   · 正文里的交叉引用（零件表提到 `IC7011`）会抢在真正的分册首页之前。
    # 实测这两条让 4 册各错 3~4 条落点，且六道关一处不报（链接不进文本层）。
    where = {}
    for i in range(last, d.page_count):
        if (i + 1) in skip:
            continue
        head = []
        for b in d[i].get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                if ln["bbox"][1] < 130.0:
                    head.append(" ".join("".join(
                        x["text"] for x in ln["spans"]).split()))
        where[i + 1] = [h for h in head if h]
    n_link, toc = 0, []
    for pno in toc_pages:
        pg = d[pno - 1]
        for _l in pg.get_links():
            if _l.get("kind") == fitz.LINK_GOTO:
                pg.delete_link(_l)
        for b in pg.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                r = fitz.Rect(ln["bbox"])
                t = " ".join("".join(x["text"] for x in ln["spans"]).split())
                m = _CODEROW.match(t)
                if not m:
                    continue
                title, code = m.group(1).strip(" .·…"), m.group(2).strip()
                if len(title) < min_title or len(code) < 3:
                    continue
                tgt = next((p for p in sorted(where)
                            if any(h.startswith(code) for h in where[p])), None)
                if not tgt:
                    continue
                # 链接矩形要含标题、点引线与编号 —— 右端延到编号之后，
                # 把独立成列的版次字母（x≈551）也罩进去。
                # 纵向要**内缩** 0.6pt：行框含升部降部，实测高 11.5 而行距
                # 只有 10.85，照抄行框相邻两条就压叠 0.7pt，点上一条可能
                # 跳到下一条。内缩后净高 10.3 < 行距，互不相犯。
                rr = fitz.Rect(r.x0, r.y0 + 0.6,
                               min(r.x1 + 16.0, pg.rect.x1), r.y1 - 0.6)
                pg.insert_link({"kind": fitz.LINK_GOTO, "from": rr,
                                "page": tgt - 1, "to": fitz.Point(0, 0)})
                n_link += 1
                toc.append([1, f"{title}（{code}）", tgt])
    if toc:
        toc.sort(key=lambda z: z[2])
        d.set_toc(toc)
    dst = out or pdf
    if dst == pdf:
        d.saveIncr()
    else:
        d.save(dst, garbage=3, deflate=True)
    d.close()
    return n_link, len(toc)


def add(pdf, toc_pages, offset, out=None, min_title=2, use_labels=False,
        fix=None):
    """`fix` = {条目编号: 正确页码}，勘正**原版目录里写错的页码**。

    原版目录常是未刷新的 Word 域。实测 手册 A 的 `7.3.2 Flexshaft` 在目录
    里写作 `7-3-1`，正文实际在 `7-3-2`；照抄就把链接落到前一页。
    键取条目编号（`7.3.2`）而非标题 —— 标题是译文，会随词表改动。
    凡用到本参数，都要在附录 A 甲里逐条记明。
    """
    return _add(pdf, toc_pages, offset, out, min_title, use_labels, fix or {})


def _add(pdf, toc_pages, offset, out=None, min_title=2, use_labels=False,
         fix=None):
    """给目录页加跳转链接与书签。`toc_pages` 为目录所在**物理页号**（1 基）。

    两种页码体系：
      · 连续页码 → 物理页 = 印刷页 + `offset`；
      · 分节页码（`7-4-2`，手册 A）→ `use_labels=True`，按页眉标签实扫查表。

    另外，页码**未必与标题在同一个文本块**里 —— 右对齐成独立一列时
    （手册 A 即如此），要按基线把标题行与右侧页码行配对，
    否则一条链接都建不出来。
    """
    d = fitz.open(pdf)
    labels = page_labels(d) if use_labels else {}
    n_link = 0
    toc = []
    for pno in toc_pages:
        if pno > d.page_count:
            continue
        pg = d[pno - 1]
        # **幂等**：先清掉本页已有的 GOTO 链接。装配流程用 saveIncr 增量写，
        # 重跑一次就再叠一层 —— 实测 手册 A 134 条链接实为 67 条各两份，
        # 且**六道关一处不报**（链接是注记，不进文本层）。
        for _l in pg.get_links():
            if _l.get("kind") == fitz.LINK_GOTO:
                pg.delete_link(_l)
        rows = []
        for b in pg.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                t = " ".join("".join(x["text"] for x in ln["spans"]).split())
                if t:
                    rows.append((fitz.Rect(ln["bbox"]), t))
        for r0, t in rows:
            r = fitz.Rect(r0)
            m = (_ROW2 if use_labels else _ROW).match(t)
            if m:
                title, num = m.group(1), m.group(2)
            else:
                if not re.search(r"[.·…]{3,}$", t):
                    continue
                title, num = t, None
                cand = [(q, u) for q, u in rows
                        if q is not r0 and q.x0 > r0.x1 - 2
                        and abs((q.y0 + q.y1) / 2 - (r0.y0 + r0.y1) / 2)
                        < 0.6 * max(r0.height, 1)]
                for q, u in sorted(cand, key=lambda z: z[0].x0):
                    g = re.match(r"^([A-Za-z]?\d+(?:-\d+){0,3})$", u)
                    if g:
                        num = g.group(1)
                        r = r | q
                        break
                if num is None:
                    continue
            title = title.strip(" .·…")
            if len(title) < min_title:
                continue
            if fix:
                _k = title.split()[0] if title.split() else ""
                num = fix.get(_k, num)
            if use_labels:
                tgt = labels.get(num)
                if not tgt:
                    continue
            else:
                try:
                    tgt = int(num) + offset
                except ValueError:
                    continue
            if not (1 <= tgt <= d.page_count):
                continue
            pg.insert_link({"kind": fitz.LINK_GOTO, "from": r,
                            "page": tgt - 1, "to": fitz.Point(0, 0)})
            n_link += 1
            toc.append([_level(title, toc[-1][0] if toc else 0), title, tgt])
    # 书签层级：PDF 大纲**一次不能跳两级**（PyMuPDF 直接抛错），而目录的
    # 视觉缩进完全可以跳。故条目与顺序 100% 照搬，层级归一到「至多深一级」。
    prev = 0
    for row in toc:
        row[0] = min(row[0], prev + 1)
        prev = row[0]
    if toc:
        d.set_toc(toc)
    dst = out or pdf
    if dst == pdf:
        d.saveIncr()
    else:
        d.save(dst, garbage=3, deflate=True)
    d.close()
    return n_link, len(toc)
