# -*- coding: utf-8 -*-
"""附录 A《译校勘误说明》与附录 B《中英术语对照表》（SKILL §9）。

附录 A 分三部分
    甲、原文缺陷与勘正 —— 正文已按勘正后译出
    乙、存疑保留       —— 无法确证的数值分歧保留原值、仅加注
    丙、版式与插图修复 —— 自动化提取/排版中做的修复动作

附录 B 由 terms.GLOSSARY 自动生成，按类别排序，**双栏**排版
（条目短，单栏浪费近一半版面）。
"""
from reportlab.platypus import Table, TableStyle, Spacer, Paragraph, KeepTogether
from reportlab.lib import colors

import zhlib as _Z
from zhlib import zh, styles, TBL_GRID, TBL_HDR
from render import P, grid_table


A_TITLE = "附录 A 译校勘误说明"
B_TITLE = "附录 B 中英术语对照表"

_JIA_HDR = ["序号", "原文位置", "英文原文／问题描述", "问题类型", "勘正与译文",
            "依据与说明"]
_YI_HDR = ["序号", "原文位置", "存疑内容", "冲突对象", "本稿处理", "须确认事项"]
_BING_HDR = ["序号", "涉及部位", "原始问题", "修复处理"]


def _sect(t, S):
    return P(t, S["h2"])


def _numbered(rows, hdr):
    """行比表头少一格时，自动补上「序号」列。

    三张勘误表的表头第一列都是「序号」，但各册的内容层写的是不带序号的
    元组（序号本就该由程序生成，人手编号一改条目就得重排）。不补的话
    标题会顶到序号列里、最后一列空着 —— 成品上四列错位、末列全空。
    """
    out = []
    for i, r in enumerate(rows, 1):
        r = list(r)
        out.append(([str(i)] + r) if len(r) == len(hdr) - 1 else r)
    return out


def errata(jia=(), yi=(), bing=(), S=None, fw=468.0, intro=None):
    """附录 A。三类条目各自可为空；为空则该节写明「无」。"""
    S = S or styles()
    out = [P(A_TITLE, S["h1"])]
    out.append(P(intro or
                 "本附录逐条记录翻译与版式重建过程中发现的原文缺陷、存疑之处，"
                 "以及为忠实还原原版而做的插图与版式修复动作。凡正文按勘正后"
                 "译出者，均在「甲」中列明依据；凡无法确证者，一律保留原值并"
                 "在「乙」中标注，须经工程部门确认后方可据以施工。", S["body"]))

    out.append(_sect("甲、原文缺陷与勘正（正文已按勘正后译出）", S))
    if jia:
        w = [26, 62, 118, 50, 106, 106]
        out.append(grid_table([_JIA_HDR] + _numbered(jia, _JIA_HDR), w, S,
                              align=["C", "L", "L", "C", "L", "L"],
                              width=fw, size="tbl"))
    else:
        out.append(P("经逐句核对，本文件未发现须勘正的原文缺陷。", S["body"]))

    out.append(_sect("乙、存疑保留（保留原值，仅加注）", S))
    if yi:
        w = [26, 62, 112, 84, 92, 92]
        out.append(grid_table([_YI_HDR] + _numbered(yi, _YI_HDR), w, S,
                              align=["C", "L", "L", "L", "L", "L"],
                              width=fw, size="tbl"))
    else:
        out.append(P("无。本文件所载数值与单位均自洽，未发现相互冲突之处。",
                     S["body"]))

    out.append(_sect("丙、版式与插图修复", S))
    if bing:
        w = [26, 84, 174, 184]
        out.append(grid_table([_BING_HDR] + _numbered(bing, _BING_HDR), w, S,
                              align=["C", "L", "L", "L"], width=fw, size="tbl"))
    else:
        out.append(P("无。本文件版式简单，未做插图拼接或伪表剔除等修复。",
                     S["body"]))
    return out


def glossary(GLOSSARY, S=None, fw=468.0, order=None, note=None):
    """附录 B。GLOSSARY: {类别: [(英文, 中文[, 备注]), ...]}，双栏排版。"""
    S = install_gloss_styles(S or styles())
    out = [P(B_TITLE, S["h1"])]
    out.append(P(note or
                 "下表汇总全文术语的英中对照，供与原版交叉查阅。同一术语全文"
                 "统一译名；首次出现处在正文中附注英文。数值、单位、型号、"
                 "标准号与零件号一律保持原样。", S["body"]))

    cats = order or list(GLOSSARY.keys())
    hdr = ["英文", "中文", "英文", "中文"]
    w = [117, 117, 117, 117]
    rows = [hdr]
    spans = []
    for cat in cats:
        items = GLOSSARY.get(cat) or []
        if not items:
            continue
        spans.append(((0, len(rows)), (3, len(rows))))
        rows.append([f"— {cat} —", "", "", ""])
        # 行主序双栏：跨页自然续排，不会像列主序那样被切断
        for k in range(0, len(items), 2):
            a = items[k]
            b = items[k + 1] if k + 1 < len(items) else ("", "")
            rows.append([a[0], a[1], b[0], b[1]])

    cat_rows = [s[0][1] for s in spans]
    extra = [("SPAN", s[0], s[1]) for s in spans]
    extra += [("BACKGROUND", (0, r), (-1, r), TBL_HDR) for r in cat_rows]
    extra += [("ALIGN", (0, r), (-1, r), "CENTER") for r in cat_rows]
    extra += [("FONTNAME", (0, r), (-1, r), "ZH-B") for r in cat_rows]
    t = grid_table(rows, w, S, align=["L", "L", "L", "L"], width=fw,
                   size="gloss_", extra=extra)
    out.append(no_widow(t))
    return out


# grid_table 用 S[size] / S[size+"L"] / … 取样式；为术语表补一组别名
def install_gloss_styles(S):
    S["gloss_"] = S["gloss"]
    S["gloss_L"] = S["gloss"]
    S["gloss_R"] = S["gloss"]
    S["gloss_H"] = S["glossH"]
    S["gloss_HL"] = S["glossH"]
    return S


class NoWidowRows:
    """给长表装上「不留寡行」的分页：尾页不足若干行就从上一页多挪几行下来。

    ⚠ 术语表是几百行的长表，ReportLab 只按「装得下就装」切分，于是尾页可能
      只剩**一两行**（实测 规范 L 附录 B 尾页只有 1 条词条，整页留白）。
      关 7「空白页」看不见（页上有字），关 13「孤页」也看不见
      —— 那一页上有表格线框，被「有图或绘图对象多」的豁免放过了。
      ⇒ 判据管不住的，改由排版本身管住。

    用法：`t.__class__ = type("T", (NoWidowRows, t.__class__), {})`。
    """
    _MIN_TAIL = 6

    def split(self, aw, ah):
        parts = super().split(aw, ah)
        if len(parts) != 2:
            return parts
        rep = getattr(self, "repeatRows", 0) or 0
        nt = len(getattr(parts[1], "_cellvalues", []) or []) - rep
        nh = len(getattr(parts[0], "_cellvalues", []) or [])
        if not (0 < nt < self._MIN_TAIL) or nh <= self._MIN_TAIL + rep:
            return parts
        rh = getattr(self, "_rowHeights", None) or []
        k = self._MIN_TAIL - nt
        cut = sum(rh[max(rep, nh - k):nh]) if rh else 0
        if cut <= 0 or ah - cut <= 0:
            return parts
        p2 = super().split(aw, ah - cut)
        return p2 if len(p2) == 2 else parts


def no_widow(t, min_tail=6):
    t.__class__ = type("NoWidow" + t.__class__.__name__,
                       (NoWidowRows, t.__class__), {"_MIN_TAIL": min_tail})
    return t
