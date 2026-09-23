# -*- coding: utf-8 -*-
"""构建入口：python content/build.py —— 出稿并跑完全部闸门（FAIL 即返回非 0）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _engine  # noqa: F401,E402  —— 定位技能引擎
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from driver import Job, run            # noqa: E402
from builder import A4, LETTER         # noqa: E402,F401
import content as C                    # noqa: E402
import terms as T                      # noqa: E402
import zhlib                           # noqa: E402
from builder import Decor              # noqa: E402
from reportlab.platypus import Table, TableStyle, Paragraph   # noqa: E402
from reportlab.lib.styles import ParagraphStyle               # noqa: E402
from reportlab.lib import colors                              # noqa: E402

# 原版品牌色（页眉文字、标题、页眉线均为 #1F3B5A）
zhlib.set_brand(primary="#1F3B5A", dark="#1F3B5A", rule="#1F3B5A")
BRAND = colors.HexColor("#1F3B5A")


def _running_head(pno):
    """原版简式页眉：左品牌名（粗）| 右手册名，下方一道品牌色细线。"""
    l = ParagraphStyle("rh_l", fontName="ZH-B", fontSize=9, leading=11, textColor=BRAND)
    r = ParagraphStyle("rh_r", parent=l, fontName="ZH", alignment=2)
    t = Table([[Paragraph("NORTHSTAR DRILLING TOOLS", l),
                Paragraph("操作与维护手册", r)]], colWidths=[A4.fw / 2.0] * 2)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, BRAND),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t

WORK = os.path.dirname(HERE)                               # 工作区
SRC = os.path.normpath(os.path.join(WORK, '../../mud_motor_manual.pdf'))           # 原文（相对工作区）
OUT = os.path.normpath(os.path.join(WORK, '../mud_motor_manual_中文_v01.pdf'))           # 译稿（相对工作区）

job = Job(
    name='mud_motor_manual',
    src=SRC, work=WORK, out=OUT,
    pages=C.CHAPTERS,
    flow=True,                # R 级语义重排 = True；P/H 级 1:1 同源 = False
    geom=A4,                # 文本类文档用 A4；图纸/表单保持原幅面
    mast_title=getattr(C, "MAST_TITLE", ""),
    foot=getattr(C, "FOOT", ("", "", "")),
    used_figs=getattr(C, "USED_FIGS", ()),
    labels_zh=getattr(C, "LABELS_ZH", None),   # 图内矢量英文 → 中文（data/figures.json 的 labels）
    glossary=T.GLOSSARY, jia=T.JIA, yi=T.YI, bing=T.BING,
    whitelist_add=getattr(T, "WHITELIST_ADD", ()),
    token_ignore=getattr(T, "TOKEN_IGNORE", ()),
    errata_intro=getattr(T, "ERRATA_INTRO", None),
    decors=(Decor(_running_head, A4.fw, y_top=28.0, gap=14.0),),
)

if __name__ == "__main__":
    sys.exit(0 if run(job) else 1)
