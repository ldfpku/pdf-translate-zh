# -*- coding: utf-8 -*-
"""生成虚构的英文「装配作业指导书」（SWI）——展示用源文档。

Tethys Downhole Tools、SWI-650-SS、650 Drilling Shock Sub 及全部零件号均为虚构。
版式复刻系统导出式作业指导书的典型特征：页眉色带 + 章节名 + 页码、封面元信息、
法律/文档控制/法规页、带点引线的目录、PDF 书签、PPE 图标栏、警示/说明图标行、
多级步骤、零件表与扭矩表、约 85 dpi 的低清渲染插图（件号气泡与英文标注烧死在图里）。

    python make_source.py [输出目录]      → <输出目录>/SWI-650-SS_Assembly.pdf
"""
import os
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
                                TableStyle, Image, PageBreak, Flowable, KeepTogether, NextPageTemplate)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_figures  # noqa: E402

W, H = letter
BAND = colors.HexColor("#4A6FB5")
INK = colors.HexColor("#222222")
DOC = "SWI-650-SS"
FOOT1 = "SWI-650-SS  ·  Rev 3  ·  12-Mar-2026  ·  Tethys Downhole Tools"
FOOT2 = "Fictional demonstration document - not a real product."

body = ParagraphStyle("b", fontName="Helvetica", fontSize=8.6, leading=11.5, textColor=INK, spaceAfter=4)
bodyb = ParagraphStyle("bb", parent=body, fontName="Helvetica-Bold")
small = ParagraphStyle("s", parent=body, fontSize=7.6, leading=9.5)
h1 = ParagraphStyle("h1", fontName="Helvetica", fontSize=9.2, leading=12, textColor=INK, spaceBefore=6, spaceAfter=6)
cover_t = ParagraphStyle("ct", fontName="Helvetica-Bold", fontSize=16, leading=21, textColor=INK)
toc_title = ParagraphStyle("tt", fontName="Helvetica-Bold", fontSize=9, leading=12, spaceAfter=8)


# ---------------------------------------------------------------- 自定义 flowable
class Section(Paragraph):
    """一级章节：写进目录 + 书签，并更新页眉章节名。"""
    def __init__(self, num, title, toc=True):
        text = (f"{num}&nbsp;&nbsp;&nbsp;&nbsp;{title}" if num else title)
        super().__init__(text, h1)
        self.num, self.title, self.toc = num, title, toc
        self.key = "s_" + (num or title).replace(" ", "_")


class Step(Flowable):
    """步骤号悬挂 + 内容（段落/图/说明行）。书签标题 = 「2.2 - 步骤全文」。"""
    def __init__(self, num, parts, width=468):
        super().__init__()
        self.num, self.parts, self.width_ = num, parts, width
        self.key = "st_" + num
        self.outline = None
        self._t = Table([[Paragraph(num, bodyb), parts]], colWidths=[34, width - 34])
        self._t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 0),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))

    def wrap(self, aw, ah):
        return self._t.wrap(aw, ah)

    def split(self, aw, ah):
        return []

    def draw(self):
        self._t.drawOn(self.canv, 0, 0)


class Icon(Flowable):
    """说明行图标：warning（红圆 !）/ info（蓝方 i）。"""
    def __init__(self, kind, size=11):
        super().__init__()
        self.kind, self.size = kind, size
        self.width = self.height = size

    def draw(self):
        c, s = self.canv, self.size
        if self.kind == "warning":
            c.setFillColor(colors.HexColor("#D62B2B"))
            c.circle(s / 2, s / 2, s / 2, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", s * 0.8)
            c.drawCentredString(s / 2, s * 0.22, "!")
        else:
            c.setFillColor(colors.HexColor("#1E4E9C"))
            c.rect(0, 0, s, s, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", s * 0.8)
            c.drawCentredString(s / 2, s * 0.2, "i")


class WasteIcon(Flowable):
    """带叉的垃圾桶（WEEE）符号。"""
    def __init__(self):
        Flowable.__init__(self)          # 基类会把 width/height 置 0，必须在其后赋值
        self.width = self.height = 44

    def draw(self):
        c = self.canv
        c.translate(2, 4)
        c.setLineWidth(2)
        c.rect(10, 6, 20, 26)
        c.line(7, 32, 33, 32)
        c.line(16, 35, 24, 35)
        c.line(2, 2, 38, 38)
        c.line(2, 38, 38, 2)
        c.rect(6, -2, 28, 4, fill=1)


def note(kind, text, width=434):
    t = Table([[Icon(kind), Paragraph(text, bodyb)]], colWidths=[18, width - 18])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def fig(figdir, name, w=300):
    from PIL import Image as PI
    p = os.path.join(figdir, name + ".jpg")
    im = PI.open(p)
    return Image(p, width=w, height=w * im.height / im.width)


def grid(rows, widths, hdr=True):
    data = [[Paragraph(str(c), bodyb if (hdr and r == 0) else body) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if hdr else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    if hdr:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3E8F2")))
    t.setStyle(TableStyle(st))
    return t


def ppe_block(figdir, title="PPE required"):
    return [Paragraph(title, body), fig(figdir, "ppe", 110), Spacer(1, 6)]


# ---------------------------------------------------------------- 页面装饰
def _band(c, doc, page_label=True):
    c.saveState()
    c.setFillColor(BAND)
    c.rect(0, H - 14, W, 14, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(14, H - 10.5, "TDT-SWI")
    # 右上角徽章：菱形 + T
    c.setFillColor(colors.HexColor("#1F3E78"))
    p = c.beginPath()
    p.moveTo(W - 40, H - 2); p.lineTo(W - 28, H - 14); p.lineTo(W - 40, H - 26); p.lineTo(W - 52, H - 14); p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(W - 40, H - 17, "T")
    if page_label:
        c.setFillColor(INK)
        c.setFont("Helvetica", 8)
        sec = getattr(doc, "_section", "")
        if sec:
            c.drawCentredString(W / 2, H - 25, "/ " + sec)
        c.drawRightString(W - 60, H - 25, str(doc.page))
    c.setFillColor(colors.HexColor("#9A9A9A"))
    c.setFont("Helvetica", 6.4)
    c.drawCentredString(W / 2, 30, FOOT1)
    c.drawCentredString(W / 2, 21, FOOT2)
    c.restoreState()


def on_cover(c, doc):
    _band(c, doc, page_label=False)
    c.saveState()
    # 虚构徽标：三道波纹 + 字标
    c.setStrokeColor(colors.HexColor("#138A8A"))
    c.setLineWidth(5)
    for k in range(3):
        y = H - 110 - k * 11
        p = c.beginPath()
        p.moveTo(40, y)
        p.curveTo(55, y + 10, 70, y - 10, 85, y)
        c.drawPath(p, stroke=1, fill=0)
    c.setFillColor(colors.HexColor("#138A8A"))
    c.setFont("Helvetica-Bold", 30)
    c.drawString(92, H - 135, "tethys")
    c.restoreState()


class Doc(BaseDocTemplate):
    def __init__(self, path, **kw):
        super().__init__(path, pagesize=letter, leftMargin=72, rightMargin=72, topMargin=60,
                         bottomMargin=60, title="SWI-650-SS, Assembly SWI, 650 Drilling Shock Sub",
                         author="A. Rivera (fictional)", **kw)
        frame = Frame(72, 60, W - 144, H - 120, id="f")
        # 页眉章节名要等本页内容排完才知道 ⇒ 用 onPageEnd 画
        self.addPageTemplates([PageTemplate("cover", [Frame(40, 60, W - 80, H - 230)], onPageEnd=on_cover),
                               PageTemplate("body", [frame], onPageEnd=_band)])
        self._section = ""

    def afterFlowable(self, fl):
        if isinstance(fl, Section):
            self._section = fl.title
            if fl.toc:
                label = f"{fl.num}. {fl.title}" if fl.num else fl.title
                self.notify("TOCEntry", (0 if fl.num else 1, label, self.page, fl.key))
            self.canv.bookmarkPage(fl.key)
            self.canv.addOutlineEntry((f"{fl.num} - {fl.title}" if fl.num else fl.title), fl.key, 0)
        elif isinstance(fl, Step) and fl.outline:
            self.canv.bookmarkPage(fl.key)
            self.canv.addOutlineEntry(f"{fl.num} - {fl.outline}", fl.key, 0)


def step(num, text, *extra):
    parts = [Paragraph(text, body)] + list(extra)
    s = Step(num, parts)
    s.outline = text.replace("<b>", "").replace("</b>", "")
    return s


# ---------------------------------------------------------------- 正文
def story(figdir):
    S = [NextPageTemplate("body")]
    # 封面
    S += [Spacer(1, 10), Paragraph("SWI-650-SS, Assembly SWI, 650 Drilling Shock Sub", cover_t), Spacer(1, 14)]
    meta = [("Version:", "3"), ("DocumentID:", "7c1e9a40-58d2-4f6b-9e0a-3b2d61c4f8e7"),
            ("Published:", "March 12, 2026"), ("Owner:", "Tethys Assembly Engineering, Harbor Point Shop"),
            ("Author:", "A. Rivera"), ("Data Classification:", "Public (fictional demonstration)")]
    t = Table([[Paragraph(k, small), Paragraph(v, small)] for k, v in meta], colWidths=[130, 300])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    S += [t, PageBreak()]
    # 法律信息
    S += [Section("", "Legal Information", toc=True),
          Paragraph("Copyright © 2026 Tethys Downhole Tools. All rights reserved.", body),
          Paragraph("This document is a fictional demonstration created for the pdf-translate-zh project. "
                    "The company, the product, the part numbers and all people named in it are invented. "
                    "Any resemblance to real products or organizations is coincidental.", body),
          Paragraph("<b>Trademarks &amp; Service marks</b>", body),
          Paragraph("Tethys and the Tethys wave logo are fictional marks used for demonstration only.", body),
          PageBreak()]
    # 文档控制
    S += [Section("", "Document Control"),
          grid([["Owner:", "Tethys Assembly Engineering, Harbor Point Shop"], ["Author:", "A. Rivera"],
                ["Reviewer:", "M. Okafor"], ["Approver:", "A. Rivera"]], [120, 348], hdr=False),
          Spacer(1, 10), Paragraph("<b>Revision History</b>", body),
          grid([["Version", "Date", "Description", "Prepared by"],
                ["1", "11/20/2025", "Initial Version", "A. Rivera"],
                ["2", "1/15/2026", "Added back-up ring orientation to step 2.5.", "A. Rivera"],
                ["3", "3/12/2026", "Added torque values for the lock nut and set screws (Table 3-1).", "A. Rivera"]],
               [50, 70, 250, 98]),
          PageBreak()]
    # 法规符合性
    S += [Section("", "Regulatory Compliance"), Paragraph("<b>Waste Management</b>", body),
          Paragraph("IMPORTANT INFORMATION FOR CORRECT DISPOSAL OF THE EQUIPMENT", bodyb), Spacer(1, 8),
          Table([[WasteIcon(), Paragraph("This symbol means that the equipment cannot be discarded in a rubbish-bin. "
                                         "At its end of life, the equipment and/or its components must be treated "
                                         "following Tethys environmental procedures, in compliance with the Tethys "
                                         "QHSE Policy and applicable laws and regulations on waste management.", body)]],
                colWidths=[56, 412], style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
          PageBreak()]
    # 目录
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("t0", fontName="Helvetica", fontSize=8, leading=13, leftIndent=0),
                       ParagraphStyle("t1", fontName="Helvetica", fontSize=8, leading=13, leftIndent=16)]
    toc.dotsMinLevel = 0
    S += [Section("", "Table of Contents", toc=False), Spacer(1, 6), toc, PageBreak()]
    # 1 简介
    S += [Section("1", "Introduction")]
    S += [Table([[Paragraph("<b>PPE</b>", body)], [fig(figdir, "ppe", 120)]], colWidths=[468],
                style=[("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDDDDD")),
                       ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999"))]), Spacer(1, 8)]
    S += [Paragraph("The SWI-650-SS standard work instruction (SWI) gives the procedure for the assembly of the "
                    "650 drilling shock sub.", body),
          Paragraph("Obey all safety requirements as given in the Tethys Safety Standards. Important safety "
                    "requirements are:", body)]
    for b in ["Obey PPE requirements as per the Tools and Equipment PPE Appendix to Tethys QHSE Standard S-003.",
              "Use safe lifting methods when you move parts and tooling around the work area.",
              "Make sure that only necessary personnel are in the work area.",
              "Make sure that only approved and certified personnel use machinery during the procedure.",
              "Obey all safety requirements for electrical equipment."]:
        S.append(Paragraph("•&nbsp;&nbsp;" + b, ParagraphStyle("bl", parent=body, leftIndent=12, firstLineIndent=-8)))
    S += [Paragraph("Discard any equipment, component or consumables in accordance with the Tethys QHSE policy and "
                    "applicable laws and regulations on waste management.", body), Spacer(1, 8),
          Paragraph("<b>Parts List</b>", body),
          grid([["Item", "Part No.", "Description", "Qty"],
                ["01", "TDT-65001", "Mandrel, 6-1/2", "1"], ["02", "TDT-65002", "Housing, 6-1/2", "1"],
                ["03", "TDT-65003", "Disc spring, 4.25 OD", "6"], ["04", "TDT-65004", "Spline sleeve", "1"],
                ["05", "TDT-65005", "Wiper ring", "1"], ["06", "TDT-65006", "Seal carrier", "1"],
                ["07", "TDT-65007", "O-ring, 2-348, HNBR 90", "2"], ["08", "TDT-65008", "Back-up ring, PEEK", "2"],
                ["09", "TDT-65009", "Thrust bearing", "1"], ["10", "TDT-65010", "Lock nut, 4-1/2 UN", "1"],
                ["11", "TDT-65011", "Set screw, 3/8-16 x 1/2", "2"], ["12", "TDT-65012", "Grease fitting, 1/8 NPT", "1"]],
               [40, 80, 290, 58]),
          Spacer(1, 8), KeepTogether([fig(figdir, "fig_exploded", 430),
                                      Paragraph("Figure 1-1  Mandrel stack components", small)]),
          PageBreak()]
    # 2 装配芯轴组件
    S += [Section("2", "Assemble the Mandrel Stack")] + ppe_block(figdir)
    S += [note("warning", "Make sure that all components are clean before you start the assembly."),
          step("2.1", "Hold the mandrel (01) horizontally in a soft-jaw vise.",
               fig(figdir, "fig_clamp", 360),
               note("info", "Make sure that the vise jaws do not damage the chrome surface of the mandrel.")),
          step("2.2", "Install eight new disc springs (03) onto the mandrel (01).",
               fig(figdir, "fig_springs", 380),
               note("info", "Stack the disc springs in series with the convex face up. Springs installed in the "
                            "wrong direction will fail under load.")),
          step("2.3", "Install the spline sleeve (04) onto the mandrel (01). The spline keys must align with the "
                      "slots on the mandrel.", fig(figdir, "fig_sleeve", 380)),
          step("2.4", "Install the wiper ring (05) and the seal carrier (06) onto the mandrel (01)."),
          step("2.5", "Install the O-ring (07) and the back-up ring (08) into the groove of the seal carrier (06). "
                      "The back-up ring must be on the low-pressure side.", fig(figdir, "fig_seal", 380)),
          step("2.6", "Install the thrust bearing (09) against the seal carrier (06)."),
          PageBreak()]
    # 3 装入壳体
    S += [Section("3", "Install the Mandrel Stack into the Housing")] + ppe_block(figdir)
    S += [step("3.1", "Secure the housing (02) to prevent movement in any direction. Examine the inside of the "
                      "housing for debris. Clean if necessary.",
               note("warning", "Make sure that all components are clean before you start the assembly.")),
          step("3.2", "Use a sling and overhead crane to install the subassembly into the housing (02). Push it as "
                      "far forward as possible.", fig(figdir, "fig_housing", 380),
               note("info", "Use V-blocks, jack stands or other methods per local best practice.")),
          step("3.3", "Install the lock nut (10) and torque it to TQ-B (see Table 3-2).", fig(figdir, "fig_locknut", 380)),
          step("3.4", "Install two set screws (11) into the lock nut (10) and torque them to TQ-A."),
          Spacer(1, 6), Paragraph("<b>Table 3-1  Torque Values</b>", body),
          grid([["Code", "Connection", "Torque (ft-lbf)", "Tool"],
                ["TQ-A", "Set screw (11) to lock nut (10)", "35 - 40", "Hex bit, 3/16"],
                ["TQ-B", "Lock nut (10) to mandrel (01)", "1,800 - 2,000", "Spanner wrench, 650"]],
               [44, 196, 110, 118]),
          PageBreak()]
    # 4 注脂
    S += [Section("4", "Grease Fill")] + ppe_block(figdir)
    S += [step("4.1", "Remove the plugs from the side fill port and the top vent port of the housing (02).",
               fig(figdir, "fig_ports", 380)),
          step("4.2", "Pump grease through the side fill port until clean grease flows from the top vent port "
                      "without air bubbles.",
               note("warning", "Do not exceed 50 psi grease pressure. Excess pressure can push the seal carrier "
                               "(06) out of position.")),
          step("4.3", "Install the grease fitting (12) and the vent plug."),
          step("4.4", "Record the grease volume on the assembly checklist.")]
    return S


def main(out):
    os.makedirs(out, exist_ok=True)
    figdir = make_figures.main(out)
    path = os.path.join(out, "SWI-650-SS_Assembly.pdf")
    doc = Doc(path)
    doc.multiBuild(story(figdir))
    return path


if __name__ == "__main__":
    print(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build")))
