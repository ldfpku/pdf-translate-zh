# -*- coding: utf-8 -*-
"""构建入口：python content/build.py —— 出稿并跑完全部闸门（FAIL 即返回非 0）。

插图须先跑位图流水线（见 examples/showcase-swi/README.md）：
    figpipe extract → sr.py → figpipe detect → figpipe apply content/labels_zh.py → figpipe sweep
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _engine  # noqa: F401,E402  —— 定位技能引擎
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from reportlab.lib import colors                              # noqa: E402
from reportlab.lib.styles import ParagraphStyle               # noqa: E402
from reportlab.platypus import Table, TableStyle, Paragraph   # noqa: E402

import content as C                    # noqa: E402
import terms as T                      # noqa: E402
import zhlib                           # noqa: E402
from builder import A4, Decor          # noqa: E402
from driver import Job, run            # noqa: E402

BAND = "#4A6FB5"
zhlib.set_brand(primary=BAND, dark="#1F3E78", rule=BAND)


def _band(pno):
    """原版页眉：品牌色带（左 TDT-SWI，右文件名）。"""
    st = ParagraphStyle("band", fontName="ZH-B", fontSize=8, leading=10, textColor=colors.white)
    t = Table([[Paragraph("TDT-SWI", st),
                Paragraph("SWI-650-SS　650 型钻井减震器装配作业指导书", ParagraphStyle("band_r", parent=st, alignment=2))]],
              colWidths=[A4.fw * 0.3, A4.fw * 0.7])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BAND)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


WORK = os.path.dirname(HERE)
SRC = os.path.normpath(os.path.join(WORK, "..", "..", "SWI-650-SS_Assembly.pdf"))
OUT = os.path.normpath(os.path.join(WORK, "..", "SWI-650-SS_Assembly_中文_v01.pdf"))

job = Job(
    name="SWI-650-SS_Assembly",
    src=SRC, work=WORK, out=OUT,
    pages=C.CHAPTERS,
    flow=True, chapter_break=True,
    geom=A4,
    mast_title=C.MAST_TITLE,
    foot=C.FOOT,
    used_figs=C.USED_FIGS,
    glossary=T.GLOSSARY, jia=T.JIA, yi=T.YI, bing=T.BING,
    errata_intro=T.ERRATA_INTRO,
    whitelist_add=T.WHITELIST_ADD,
    token_ignore=T.TOKEN_IGNORE,
    decors=(Decor(_band, A4.fw, y_top=24.0, gap=12.0),),
)

if __name__ == "__main__":
    sys.exit(0 if run(job) else 1)
