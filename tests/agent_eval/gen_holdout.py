# -*- coding: utf-8 -*-
"""留出集（holdout）：与仓库示例内容完全不同的虚构文档，没有任何现成参考译文。
Borealis Downhole Systems 为虚构品牌。

    python gen_holdout.py <输出目录>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                "skills", "pdf-translate-zh", "scripts"))
import bootstrap  # noqa: E402  —— 依赖装在技能私有目录（Homebrew Python 等禁止系统 pip）
bootstrap.ensure(quiet=True)

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, Flowable)

ss = getSampleStyleSheet()
body = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=10.5,
                      leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=15,
                    textColor=colors.HexColor("#5A2A1F"))
h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12)
cap = ParagraphStyle("cap", parent=body, fontName="Helvetica-Bold", fontSize=9.5, alignment=1)
warn = ParagraphStyle("w", parent=body, fontSize=10, backColor=colors.HexColor("#FDE2E1"),
                      borderColor=colors.HexColor("#B42318"), borderWidth=1, borderPadding=6,
                      spaceBefore=6, spaceAfter=10)
note = ParagraphStyle("n", parent=warn, backColor=colors.HexColor("#E8F1FB"),
                      borderColor=colors.HexColor("#2E6DA4"))


class JarFig(Flowable):
    def __init__(self, w=460, h=140):
        super().__init__()
        self.width, self.height = w, h

    def draw(self):
        c = self.canv
        secs = [("Top Sub", 45, "#A0A0A0"), ("Detent Section", 120, "#D98C5F"),
                ("Splined Mandrel", 130, "#7FA7C9"), ("Wash Pipe", 90, "#B7C9A8"),
                ("Bottom Sub", 45, "#A0A0A0")]
        x, y = 12, 55
        for name, w, col in secs:
            c.setFillColor(colors.HexColor(col))
            c.setStrokeColor(colors.black)
            c.rect(x, y, w, 28, fill=1)
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 8)
            c.line(x + w / 2, y + 28, x + w / 2, y + 52)
            c.drawCentredString(x + w / 2, y + 57, name)
            x += w
        c.setFont("Helvetica", 7.5)
        c.drawString(12, 32, "Up-jar stroke 8 in")
        c.drawString(300, 32, "Tool OD 6.50 in")


def tbl(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                           ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EADBD5")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return t


def hf(c, d):
    c.saveState()
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#5A2A1F"))
    c.drawString(54, 760, "BOREALIS DOWNHOLE SYSTEMS")
    c.setFont("Helvetica", 9)
    c.drawRightString(558, 760, "Field Operation Guide")
    c.line(54, 754, 558, 754)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawString(54, 30, "BDS-FG-650J Rev A")
    c.drawRightString(558, 30, "Page %d" % d.page)
    c.restoreState()


def make_jar_guide(path):
    S = [Paragraph("650 Hydraulic Drilling Jar", h1),
         Paragraph("Field Operation Guide", h2),
         Paragraph("1  General", h1),
         Paragraph("The 650 hydraulic drilling jar is a double-acting jar that delivers an upward "
                   "or downward impact to free stuck pipe. It is run in the bottom hole assembly "
                   "above the drill collars and below the heavy-weight drill pipe. The jar must be "
                   "placed in tension or compression according to the jar placement analysis; it "
                   "shall not be run at the neutral point.", body),
         Paragraph("The detent section meters hydraulic oil through a restricted orifice. While "
                   "the oil is metered, the jar stays latched and the driller can load the string "
                   "with overpull or slack-off weight. When the mandrel reaches the free-stroke "
                   "position, the jar fires and the hammer strikes the anvil.", body),
         Paragraph("2  Specifications", h1),
         Paragraph("Table 2-1  Jar Specifications", cap),
         tbl([["Parameter", "Value", "Unit"],
              ["Tool OD", "6.50", "in"],
              ["Tool ID", "2.75", "in"],
              ["Overall length (cocked)", "31.2", "ft"],
              ["Max. overpull while jarring", "175,000", "lbf"],
              ["Max. slack-off while jarring", "70,000", "lbf"],
              ["Up-jar stroke", "8", "in"],
              ["Down-jar stroke", "6", "in"],
              ["Max. operating temperature", "400", "°F"],
              ["Connections", "4-1/2 IF", "pin x box"]], [220, 120, 80]),
         Spacer(1, 8),
         Paragraph("3  Operation", h1),
         Paragraph("<b>DANGER:</b> Never stand on the rig floor within the swing radius of the "
                   "elevators while jarring. A jar that fires unexpectedly can release the stored "
                   "energy of the drill string into the derrick.", warn),
         Paragraph("3.1  Jarring Up", h2),
         Paragraph("1. Pick up to the free-point weight plus the desired overpull.", body),
         Paragraph("2. Set the brake and wait. The delay is typically 30 to 90 seconds and "
                   "decreases as the overpull increases.", body),
         Paragraph("3. After the jar fires, slack off to re-cock the jar before the next blow.", body),
         Paragraph("3.2  Jarring Down", h2),
         Paragraph("Slack off below the neutral weight by the desired load. Do not exceed the "
                   "maximum slack-off in Table 2-1, or the drill pipe above the jar may buckle.", body),
         Paragraph("<b>NOTE:</b> Jarring efficiency drops at temperatures above 350 °F because "
                   "the viscosity of the hydraulic oil decreases. Allow longer delays.", note),
         PageBreak(),
         Paragraph("Figure 3-1 identifies the main sections of the jar.", body),
         JarFig(),
         Paragraph("Figure 3-1  Jar Sections", cap),
         Paragraph("4  Redress and Inspection", h1),
         Paragraph("Redress the jar after 300 circulating hours or 1,000 jarring blows, whichever "
                   "comes first. Inspect the splined mandrel for fretting and the wash pipe for "
                   "erosion. Replace all seals and the metering orifice at every redress.", body),
         Paragraph("Table 4-1  Make-up Torque", cap),
         tbl([["Connection", "Size", "Min. torque (ft-lbf)", "Max. torque (ft-lbf)"],
              ["Top sub to detent housing", "5-1/2 FH", "22,000", "24,500"],
              ["Mandrel body to wash pipe", "4-1/2 IF", "19,000", "21,000"]], [170, 90, 110, 110]),
         ]
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=54, rightMargin=54,
                            topMargin=72, bottomMargin=54, title="650 Jar Field Guide")
    doc.build(S, onFirstPage=hf, onLaterPages=hf)


def make_mandrel_drawing(path):
    W, H = landscape(letter)
    c = canvas.Canvas(path, pagesize=(W, H))
    c.setLineWidth(1.2)
    c.rect(18, 18, W - 36, H - 36)
    x0, y0, L, D = 90, 310, 400, 70
    c.setLineWidth(0.8)
    c.rect(x0, y0, L, D)
    c.rect(x0 + 25, y0 + 18, L - 50, D - 36)
    c.setLineWidth(0.25)
    for i in range(1600):          # hatch
        xx = x0 + (i % 400)
        if (i // 400) % 2 == 0:
            if xx + 5 < x0 + L:
                c.line(xx, y0, xx + 5, y0 + 18)
        elif xx + 5 < x0 + L:
            c.line(xx, y0 + D - 18, xx + 5, y0 + D)
    for i in range(1500):          # spline marks
        c.line(x0 + 120 + (i % 30), y0 + 20 + (i % 30), x0 + 122 + (i % 30), y0 + 22 + (i % 30))
    c.setFont("Helvetica", 8)
    c.line(x0, y0 - 25, x0 + L, y0 - 25)
    c.drawCentredString(x0 + L / 2, y0 - 35, "48.50 ±0.02")
    c.drawString(x0 + L + 10, y0 + D / 2, "Ø5.25 OD")
    c.drawString(x0 + L + 10, y0 + D / 2 - 12, "Ø2.75 BORE")
    c.drawString(x0 + 100, y0 + D + 12, "SPLINE, 6 KEYS, SEE VIEW B")
    c.drawString(x0 + 280, y0 + D + 12, "CHROME PLATE THIS AREA")
    c.drawString(x0 - 40, y0 - 60, "4-1/2 IF PIN")
    c.drawString(x0 + L - 50, y0 - 60, "SEAL BORE 3.500 +0.002/-0.000")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(520, 520, "NOTES:")
    c.setFont("Helvetica", 8)
    notes = ["UNLESS OTHERWISE SPECIFIED:", "1. MATERIAL: AISI 4145H MOD, 285-341 HB.",
             "2. HEAT TREAT TO 30-36 HRC BEFORE FINAL MACHINING.",
             "3. SURFACE FINISH 63 RA MAX ON SEAL BORE.",
             "4. HARD CHROME 0.003-0.005 THICK WHERE SHOWN.",
             "5. MAGNETIC PARTICLE INSPECT PER ASTM E1444."]
    for i, n in enumerate(notes):
        c.drawString(520, 505 - 12 * i, n)
    bx, by = 500, 300
    rows = [("ITEM", "PART NO.", "DESCRIPTION", "QTY"),
            ("1", "BDS-65011", "MANDREL, SPLINED, 6-1/2", "1"),
            ("2", "BDS-65012", "WIPER RING", "2"),
            ("3", "BDS-65013", "BACK-UP RING, PEEK", "2")]
    cw = [30, 60, 125, 25]
    for r, row in enumerate(rows):
        xx = bx
        for k, cell in enumerate(row):
            c.rect(xx, by - r * 14, cw[k], 14)
            c.setFont("Helvetica-Bold" if r == 0 else "Helvetica", 7)
            c.drawString(xx + 2, by - r * 14 + 4, cell)
            xx += cw[k]
    tx, ty = 560, 30
    c.rect(tx, ty, 210, 90)
    for yy in (60, 75, 90):
        c.line(tx, ty + yy - 30, tx + 210, ty + yy - 30)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(tx + 5, ty + 75, "BOREALIS DOWNHOLE SYSTEMS")
    c.setFont("Helvetica", 8)
    c.drawString(tx + 5, ty + 50, "TITLE: SPLINED MANDREL, 650 JAR")
    c.drawString(tx + 5, ty + 35, "DWG NO: 650-310-004    REV: B")
    c.drawString(tx + 5, ty + 20, "SCALE: 1:5    SHEET 1 OF 1")
    c.drawString(tx + 5, ty + 5, "DRAWN: K. ORTEGA   APPROVED: M. HALE")
    c.save()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    make_jar_guide(os.path.join(out, "jar_field_guide.pdf"))
    make_mandrel_drawing(os.path.join(out, "mandrel_drawing.pdf"))
    print("ok", out)
