# -*- coding: utf-8 -*-
"""可填写表单的译文重建工具（SKILL §5：扫描件/表单表格一律逐格转录重建）。

服务报告类文件是密集的可填写表单：右对齐粗体标签 + 填写栏 + 勾选框 +
浅蓝底的自动计算格。本模块把这些元素做成一组短函数，
使各页只需按「带」（band）拼装，而不必逐条写 TableStyle。

约定
  · 勾选框用 □（SKILL ⑩/③：不要用（  ），全角括号太宽必然撞线）；
  · 填写下划线用带下划线的全角空格，渲染为连续实线，不用 ＿ 或 _；
  · 浅蓝底 #B8CCE3 与深蓝底 #8EB4E1 取自原版实测填充色，用于自动计算格；
  · 所有单元格一律过 Paragraph（避坑 ⑨：裸串会渲染成 ■■■）。
"""
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER

from zhlib import zh

CALC_BG = colors.HexColor("#B8CCE3")      # 自动计算格底色（实测）
CALC_BG2 = colors.HexColor("#8EB4E1")     # 主键格底色（实测，仅 1 处）
LINE = colors.black
BOX = "□"


def styles(S, base=8.6):
    """表单专用样式档。原版标签 8~9pt，中文取 8.6pt 密度相当。"""
    if "fm_l" in S:
        return S
    S["fm_l"] = ParagraphStyle("fm_l", fontName="ZH-B", fontSize=base,
                               leading=base * 1.32, alignment=TA_RIGHT,
                               wordWrap="CJK")
    S["fm_lL"] = ParagraphStyle("fm_lL", parent=S["fm_l"], alignment=TA_LEFT)
    S["fm_lC"] = ParagraphStyle("fm_lC", parent=S["fm_l"], alignment=TA_CENTER)
    S["fm_v"] = ParagraphStyle("fm_v", fontName="ZH", fontSize=base,
                               leading=base * 1.32, alignment=TA_LEFT,
                               wordWrap="CJK")
    S["fm_vC"] = ParagraphStyle("fm_vC", parent=S["fm_v"], alignment=TA_CENTER)
    S["fm_calc"] = ParagraphStyle("fm_calc", fontName="ZH", fontSize=base + 2.4,
                                  leading=(base + 2.4) * 1.3,
                                  alignment=TA_CENTER,
                                  textColor=colors.white)
    S["fm_t"] = ParagraphStyle("fm_t", fontName="ZH-B", fontSize=11.5,
                               leading=15.5, alignment=TA_CENTER,
                               wordWrap="CJK")
    S["fm_sub"] = ParagraphStyle("fm_sub", fontName="ZH-B", fontSize=9.6,
                                 leading=13, alignment=TA_CENTER,
                                 wordWrap="CJK")
    return S


def L(t, S):
    """右对齐粗体标签（原版标签一律右靠贴着填写栏）。"""
    return Paragraph(zh(t), S["fm_l"])


def LL(t, S):
    return Paragraph(zh(t), S["fm_lL"])


def LC(t, S):
    return Paragraph(zh(t), S["fm_lC"])


def V(t, S):
    return Paragraph(zh(t) if t else "", S["fm_v"])


def VC(t, S):
    return Paragraph(zh(t) if t else "", S["fm_vC"])


def CALC(t, S):
    """自动计算格：原版以浅蓝底 + 白字显示 0.000 之类的计算结果。"""
    return Paragraph(str(t), S["fm_calc"])


def cbx(t, S, n=1):
    """勾选框 + 说明文字。n>1 时并列多个同文本框（少用）。"""
    return Paragraph((BOX + " " + zh(t)) if t else BOX, S["fm_v"])


def rule(n=14):
    """填写栏：带下划线的全角空格，渲染为连续实线（避坑 ⑩）。"""
    return "<u>" + "　" * n + "</u>"


def ruled(t, S, n=14):
    """标签后紧跟填写实线，整体作一格（原版「Date:______」即此形）。"""
    return Paragraph(zh(t) + rule(n), S["fm_v"])


BASE_STYLE = [
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
    ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
    ("TOPPADDING", (0, 0), (-1, -1), 1.6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
]


def band(rows, colw, extra=(), box=True, row_h=None, grid=None):
    """一「带」= 一个 Table。只画原版确有的线，不擅自补全网格。

    box   外框；grid 传 True 时画满格线（仅用于确有满格线的量测小表）。
    """
    cmds = list(BASE_STYLE)
    if box:
        cmds.append(("BOX", (0, 0), (-1, -1), 0.9, LINE))
    if grid:
        cmds.append(("GRID", (0, 0), (-1, -1), 0.6, LINE))
    cmds += list(extra)
    t = Table(rows, colWidths=colw, rowHeights=row_h)
    t.setStyle(TableStyle(cmds))
    return t


def stack(tables, fw, gaps=None):
    """把多条带纵向拼成一页。带间距缺省 0（原版各带边框相接）。"""
    rows = [[t] for t in tables]
    cmds = [("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    for i, g in enumerate(gaps or []):
        if g:
            cmds.append(("BOTTOMPADDING", (0, i), (0, i), g))
    t = Table(rows, colWidths=[fw])
    t.setStyle(TableStyle(cmds))
    return t


def calc_bg(cells, color=CALC_BG):
    """给若干 (col,row) 单元格加自动计算格底色。"""
    return [("BACKGROUND", c, c, color) for c in cells]


def ul(cells, w=0.6):
    """给若干 (col,row) 单元格加下划实线 —— 原版「标签＋横线」填写栏之形。"""
    return [("LINEBELOW", c, c, w, LINE) for c in cells]


def grid_of(c0, c1, w=0.6):
    """局部满格线：((col,row),(col,row)) 区间内画网格。"""
    return [("GRID", c0, c1, w, LINE)]
