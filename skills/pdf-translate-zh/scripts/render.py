# -*- coding: utf-8 -*-
"""块 DSL → ReportLab flowable。

块是一个元组，首元素为种类字符串。所有文本一律过 zh() 全角规范化，
所有表格单元格一律包 Paragraph（SKILL 避坑 ⑨：裸串会用默认西文字体，
中文渲染成 ■■■）。

支持的块
    ("sec",  文本)                     章节大标题
    ("h1"|"h2"|"h3", 文本)             各级标题
    ("title", 文本)                    文档题名（居中）
    ("sub",  文本)                     副题（居中）
    ("p",    文本[, 样式名])            正文段
    ("b",    文本)                     加粗正文段
    ("bul",  [文本, ...][, 层级])       项目符号列表（层级 1/2）
    ("ol",   [文本, ...][, 模式])       有序列表，模式 num|alpha|ALPHA|roman|paren
    ("ol_from", 起始号, [文本, ...][, 模式])
    ("step", 文本) / ("step2", 文本)    工序步骤（悬挂缩进）
    ("kv",   [(键, 值), ...][, 键宽])   键值行（DATE: / LOCATION:）
    ("fig",  文件名, 宽pt[, 图题])       插图
    ("figrow", [(文件名, 宽pt), ...][, 图题])   一行多图
    ("tbl",  表格flowable或工厂[, 表题][, 表题位置])
    ("sbs",  左块列表, 右块列表, 左宽pt) 并排（图左表右，SKILL §5）
    ("box",  文本或块列表[, 类型[, 标题]]) 警示框。按原版信号词选类型：
                                        NOTE→note「说明」 CAUTION→caution「注意」
                                        WARNING→warning「警告」 DANGER→("box",t,"danger","危险")
                                        第 4 项换标题，"" = 不加（正文里别再写一遍）
    ("sp",   高度pt)                    垂直间距
    ("hr", [粗细])                      分隔线
    ("keep", [块, ...])                 KeepTogether
    ("pb",)                             强制分页（流式重排时另起一页）
    ("cpb", 高度pt)                     剩余高度不足即分页（防标题落在页底）
    ("raw",  flowable)                  直接插入

坑（SKILL ⑧）：("ol", items, mode) 与 ("ol_from", start, items, mode) 的 mode
下标不同，绝不可写成统一的 b[3] —— 否则所有 alpha 会静默退化成数字序号。
本模块按块种类分别取值，并由 checks.test_dsl 抽查。
"""
import zhlib as _Z
from reportlab.platypus import (Paragraph, Spacer, Table, TableStyle, Image,
                                KeepTogether, HRFlowable, Flowable)
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle

from zhlib import (zh, styles, TBL_GRID, TBL_HDR, WARN_BG, WARN_ED,
                   DANGER_BG, DANGER_ED, NOTE_BG, NOTE_ED,
                   atom_width, fix_scripts, lead_bump)

_ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
          "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx"]


class RotText(Flowable):
    """竖排（旋转 90°）文字，用于图表纵轴题。

    ReportLab 没有现成的旋转 flowable；纵轴题若横排会把版面撑宽，
    与原版不同源。此处按 canvas.rotate 自绘，占位宽度取字号 × 1.5。
    """

    def __init__(self, text, height, font="ZH-B", size=8.4, color=None):
        Flowable.__init__(self)
        self.text, self.font, self.size = text, font, size
        self.color = color or colors.black
        self.width, self.height = size * 1.5, height

    def wrap(self, aw, ah):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont(self.font, self.size)
        c.setFillColor(self.color)
        c.translate(self.width - self.size * 0.25, 0)
        c.rotate(90)
        w = c.stringWidth(self.text, self.font, self.size)
        c.drawString((self.height - w) / 2.0, 0, self.text)
        c.restoreState()


def marker(i, mode):
    """i 从 1 起。"""
    if mode == "alpha":
        return chr(ord("a") + i - 1) + "."
    if mode == "ALPHA":
        return chr(ord("A") + i - 1) + "."
    if mode == "roman":
        return _ROMAN[i - 1] + "."
    if mode == "paren":
        return f"（{i}）"
    return f"{i}."


def P(text, style):
    """单元格/段落统一入口：过 zh()、修上下标、包 Paragraph。

    上下标要在**这里**处理，不能留给内容层：内容层写 `<sub>0.3 kgf</sub>`
    时并不知道最终字号，而 ReportLab 的 rise 增量是 pt 值、必须按字号算。
    行距也在这里补 —— 只压浅下沉量仍会蹭到次行，两件事缺一不可。
    """
    if isinstance(text, str):
        text = zh(text)
        bump = lead_bump(text, style.fontSize)
        if bump > 0:
            text = fix_scripts(text, style.fontSize)
            style = ParagraphStyle("_s", parent=style,
                                   leading=style.leading + bump)
    return Paragraph(text, style)


# ---------------------------------------------------------------- 表格工具
def fit_cols(data, colw, S, size="tbl", hdr_rows=1, pad=3.2, grow=0.0):
    """给每列一个**不可断记号下限**，再把富余宽度按原比例还回去。

    为什么必须有这一步：`wordWrap="CJK"` 是中英混排的刚需（不开，中文长串
    被当成一个词，首行只排三分之一），但代价是 ReportLab 认为**任意两字符
    之间都可断** —— `2020-08-17` 于是被劈成 `2020-08-1` / `7`，断行处还
    顶穿了行高（实测「修订历史」表的日期列）。而那张表右侧连同版心两侧
    都空着一大片：**不是没地方，是列宽求解时压根没考虑记号断不得**。

    做法：
      ① 逐列量出最宽的原子记号（日期／零件号／标准号／尺寸／数值+单位），
         加上左右内边距，作为该列**硬下限**；
      ② 总下限 ≤ 总宽 → 富余按原比例分配，每列不低于其下限；
      ③ 总下限 > 总宽 → 先向 `grow` 允许的两侧留白借宽；仍不够就按下限
         等比压缩（此时确实排不下，让它断，但至少是「真的没地方」）。
    """
    ncol = max(len(r) for r in data)
    colw = list(colw) + [0.0] * (ncol - len(colw))
    tot = float(sum(colw)) or 1.0
    floor = [0.0] * ncol
    for ri, row in enumerate(data):
        for ci, cell in enumerate(row[:ncol]):
            if not isinstance(cell, str) or not cell:
                continue
            st = S[size + "H"] if ri < hdr_rows else S[size]
            w = atom_width(zh(cell), st.fontName, st.fontSize)
            if w:
                floor[ci] = max(floor[ci], w + 2 * pad + 0.6)
    if not any(floor):
        return colw

    need = sum(floor)
    if need > tot and grow:
        tot = min(need, tot + float(grow))
    if need <= tot:
        # 富余按原比例分，但每列不得低于下限
        free = tot - need
        base = [max(c - floor[i], 0.0) for i, c in enumerate(colw)]
        bt = sum(base) or 1.0
        return [floor[i] + free * base[i] / bt for i in range(ncol)]
    return [f * tot / need for f in floor]


def grid_table(data, colw, S, hdr_rows=1, align=None, hdr_bg=TBL_HDR,
               grid=TBL_GRID, size="tbl", pad=3.2, width=None, row_h=None,
               spans=None, extra=(), grow=0.0):
    """把二维文本表变成带线框的 Table。

    data  行列表；单元格可以是 str（自动包 Paragraph）或已构造的 flowable。
    colw  列宽列表；给出 width 时按比例缩放到该总宽（SKILL §5 并排版式用）。
    align 每列对齐 "L"/"C"/"R"，缺省首列左其余居中。
    grow  允许向表格两侧留白借的最大宽度（pt）。原子记号排不下时才动用。
    """
    st_c = S[size]
    st_l = S[size + "L"]
    st_r = S.get(size + "R", st_l)
    st_h = S[size + "H"]
    st_hl = S[size + "HL"]
    ncol = max(len(r) for r in data)
    if align is None:
        align = ["L"] + ["C"] * (ncol - 1)
    align = list(align) + ["C"] * (ncol - len(align))

    if width is not None and colw:
        k = width / float(sum(colw))
        colw = [c * k for c in colw]
    if colw:
        colw = fit_cols(data, colw, S, size, hdr_rows, pad, grow)

    body = []
    for ri, row in enumerate(data):
        out = []
        for ci, cell in enumerate(row):
            if isinstance(cell, Flowable) or isinstance(cell, list):
                out.append(cell)
                continue
            cell = "" if cell is None else str(cell)
            if ri < hdr_rows:
                s = st_hl if align[ci] == "L" else st_h
            else:
                s = {"L": st_l, "C": st_c, "R": st_r}[align[ci]]
            out.append(P(cell, s))
        out += [""] * (ncol - len(out))
        body.append(out)

    cmds = [("GRID", (0, 0), (-1, -1), 0.5, grid),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), pad),
            ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), pad * 0.75),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad * 0.75)]
    if hdr_rows:
        cmds.append(("BACKGROUND", (0, 0), (-1, hdr_rows - 1), hdr_bg))
        cmds.append(("LINEBELOW", (0, hdr_rows - 1), (-1, hdr_rows - 1), 0.9, grid))
    for sp in (spans or ()):
        cmds.append(("SPAN",) + tuple(sp))
    cmds += list(extra)
    t = Table(body, colWidths=colw, rowHeights=row_h, repeatRows=hdr_rows)
    t.setStyle(TableStyle(cmds))
    return t


def _img(path, w, geom=None):
    """按目标宽度等比缩放。图片实际像素比决定高度，避免变形。"""
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        iw, ih = im.size
    return Image(path, width=w, height=w * ih / float(iw))


# ---------------------------------------------------------------- 主渲染
def flow(blocks, S=None, figdir=None, ctx=None):
    """块列表 → flowable 列表。"""
    S = S or styles()
    out = []
    for b in blocks:
        k = b[0]

        if k == "pb":
            from reportlab.platypus import PageBreak
            out.append(PageBreak())
        elif k == "cpb":
            from reportlab.platypus import CondPageBreak
            out.append(CondPageBreak(b[1]))
        elif k == "sec":
            out.append(P(b[1], S["section"]))
        elif k in ("h1", "h2", "h3"):
            out.append(P(b[1], S[k]))
        elif k == "title":
            # 可选字号：中文比英文紧凑，原版 22pt 题名需上调才有同等版面占比
            st = S["title"]
            if len(b) > 2 and b[2]:
                st = ParagraphStyle("title_" + str(b[2]), parent=st,
                                    fontSize=b[2], leading=b[2] * 1.36)
            out.append(P(b[1], st))
        elif k == "sub":
            out.append(P(b[1], S["subtitle"]))
        elif k == "p":
            out.append(P(b[1], S[b[2]] if len(b) > 2 else S["body"]))
        elif k == "b":
            out.append(P(b[1], S["bodyb"]))

        elif k == "bul":
            lvl = b[2] if len(b) > 2 else 1
            st = S["bullet"] if lvl == 1 else S["bullet2"]
            dot = _Z.pick_glyph("•●·") if lvl == 1 else _Z.pick_glyph("◦○·")
            for it in b[1]:
                out.append(P(f"{dot} {it}", st))

        elif k == "ol":
            mode = b[2] if len(b) > 2 else "num"          # 注意：下标 2
            for i, it in enumerate(b[1], 1):
                out.append(P(f"{marker(i, mode)} {it}", S["step"]))

        elif k == "ol_from":
            start = b[1]
            mode = b[3] if len(b) > 3 else "num"          # 注意：下标 3
            for i, it in enumerate(b[2], start):
                out.append(P(f"{marker(i, mode)} {it}", S["step"]))

        elif k == "step":
            out.append(P(b[1], S["step"]))
        elif k == "step2":
            out.append(P(b[1], S["step2"]))

        elif k == "kv":
            kw = b[2] if len(b) > 2 else 78
            bold = b[3] if len(b) > 3 else True     # 原版键有加粗与不加粗两种
            rows = [[P(f"<b>{a}</b>" if bold else a, S["body"]),
                     P(c, S["body"])]
                    for a, c in b[1]]
            t = Table(rows, colWidths=[kw, None])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
            out.append(t)

        elif k == "fig":
            path = b[1] if figdir is None else f"{figdir}/{b[1]}"
            im = _img(path, b[2])
            cap = b[3] if len(b) > 3 else None
            t = Table([[im]], colWidths=[b[2]], hAlign="CENTER")
            t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                                   ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
            if cap:
                # 图题**不入图宽列**：列宽跟随图宽时，窄图的图题必然被
                # 无谓折行（实测 90pt 图宽把 13 字图题折成两行）。图题的
                # 可用宽度应是版心宽——放到表外由段落样式居中，能一行
                # 排下就一行。KeepTogether 保证图与图题永不分页。
                # 固定留 5pt：间距 < 3pt 时图题会压掉图的下沿线条（SKILL ⑰）
                out.append(KeepTogether([t, Spacer(1, 5), P(cap, S["cap"])]))
            else:
                out.append(t)

        elif k == "figrow":
            cells, ws = [], []
            for f, w in b[1]:
                path = f if figdir is None else f"{figdir}/{f}"
                cells.append(_img(path, w))
                ws.append(w)
            t = Table([cells], colWidths=ws, hAlign="CENTER")
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                   ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 2),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            out.append(t)
            if len(b) > 2 and b[2]:
                out += [Spacer(1, 5), P(b[2], S["cap"])]

        elif k == "tbl":
            tb = b[1]() if callable(b[1]) else b[1]
            cap = b[2] if len(b) > 2 else None
            pos = b[3] if len(b) > 3 else "above"
            if cap and pos == "above":
                out.append(P(cap, S["tcap"]))
            out.append(tb)
            if cap and pos == "below":
                out += [Spacer(1, 3), P(cap, S["tcap"])]

        elif k == "sbs":
            # 图左表右／双栏并排：原版 bbox 只占半幅时必须照抄，否则该页溢出
            # （SKILL §5）。gap 为两栏净间距，按原版实测栏间距给出。
            lw = b[3]
            gap = b[4] if len(b) > 4 else 8.0
            left = flow(b[1], S, figdir, ctx)
            right = flow(b[2], S, figdir, ctx)
            t = Table([[left, "", right]], colWidths=[lw, gap, None])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            out.append(t)

        elif k == "box":
            kind = b[2] if len(b) > 2 else "note"
            # 原版信号词 → 类型：NOTE→note(说明)  CAUTION→caution(注意)
            # WARNING→warning(警告)  DANGER→danger 并给标题「危险」。
            # warn / danger 是旧名（标题分别为「注意」「警告」），保留兼容。
            bg, ed = {"note": (NOTE_BG, NOTE_ED), "warn": (WARN_BG, WARN_ED),
                      "caution": (WARN_BG, WARN_ED), "warning": (WARN_BG, DANGER_ED),
                      "danger": (DANGER_BG, DANGER_ED)}[kind]
            hdr = {"note": "说明", "warn": "注意", "caution": "注意",
                   "warning": "警告", "danger": "警告"}[kind]
            if len(b) > 3 and b[3] is not None:
                hdr = b[3]
            inner = (flow(b[1], S, figdir, ctx) if isinstance(b[1], list)
                     else [P(b[1], S["warn"])])
            cell = ([P(hdr, S["warnh"])] if hdr else []) + inner
            t = Table([[cell]])
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg),
                                   ("BOX", (0, 0), (-1, -1), 0.9, ed),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            out += [t, Spacer(1, 5)]

        elif k == "sp":
            out.append(Spacer(1, b[1]))
        elif k == "hr":
            out.append(HRFlowable(width="100%", thickness=b[1] if len(b) > 1 else 0.6,
                                  color=_Z.BRAND_RULE, spaceBefore=3, spaceAfter=5))
        elif k == "keep":
            out.append(KeepTogether(flow(b[1], S, figdir, ctx)))
        elif k == "raw":
            # 允许传工厂函数：两趟构建会把同一 story 排两遍，而 ReportLab 的
            # flowable 是有状态的（Table 会记住拆分状态），复用同一实例第二趟
            # 会抛 LayoutError。内容层一律传 lambda，使每趟都拿到新对象。
            out.append(b[1]() if callable(b[1]) else b[1])
        else:
            raise ValueError(f"未知块种类: {k!r}")
    return out
