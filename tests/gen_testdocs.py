# -*- coding: utf-8 -*-
"""生成虚构的英文工业技术 PDF（Northstar Drilling Tools 为虚构品牌），供示例与冒烟测试用。

    python3 tests/gen_testdocs.py [输出目录]
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..",
                                  "skills", "pdf-translate-zh", "scripts"))
import bootstrap  # noqa: E402  —— 单独运行时也能找到技能私有目录里的依赖
bootstrap.ensure(quiet=True)

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether, Flowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfgen import canvas
import math, random

ss = getSampleStyleSheet()
body = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=10.5,
                      leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=15,
                    textColor=colors.HexColor("#1F3B5A"))
h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12)
cap = ParagraphStyle("cap", parent=body, fontName="Helvetica-Bold", fontSize=9.5,
                     alignment=1)
warn = ParagraphStyle("w", parent=body, fontSize=10, backColor=colors.HexColor("#FFF3CD"),
                      borderColor=colors.HexColor("#C69200"), borderWidth=1, borderPadding=6,
                      spaceBefore=6, spaceAfter=10)

class MotorFig(Flowable):
    """Vector figure with text labels + leader lines."""
    def __init__(self, w=460, h=150):
        super().__init__(); self.width, self.height = w, h
    def draw(self):
        c = self.canv
        secs = [("Top Sub", 50, "#999999"), ("Power Section", 150, "#6C8EBF"),
                ("Transmission", 80, "#B5B5B5"), ("Bearing Assembly", 110, "#82B366"),
                ("Bit Box", 40, "#999999")]
        x = 10; y = 60
        for name, w, col in secs:
            c.setFillColor(colors.HexColor(col)); c.setStrokeColor(colors.black)
            c.rect(x, y, w, 30, fill=1)
            c.setFillColor(colors.black); c.setFont("Helvetica", 8)
            c.line(x + w / 2, y + 30, x + w / 2, y + 55)
            c.drawCentredString(x + w / 2, y + 60, name)
            x += w
        c.setFont("Helvetica", 7.5)
        c.drawString(10, 35, "Flow direction  →")
        c.drawString(330, 35, "Max. OD 6.75 in")

def hf(title, docno):
    def _f(c, d):
        c.saveState()
        c.setFont("Helvetica-Bold", 9); c.setFillColor(colors.HexColor("#1F3B5A"))
        c.drawString(54, 760, "NORTHSTAR DRILLING TOOLS"); c.setFont("Helvetica", 9)
        c.drawRightString(558, 760, title)
        c.setStrokeColor(colors.HexColor("#1F3B5A")); c.line(54, 754, 558, 754)
        c.setFont("Helvetica", 8); c.setFillColor(colors.black)
        c.drawString(54, 30, docno)
        c.drawRightString(558, 30, "Page %d" % d.page)
        c.restoreState()
    return _f

def tbl(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                           ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE3EA")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return t

def manual_story(repeat=1):
    S = []
    S += [Paragraph("675 Series Positive Displacement Motor", h1),
          Paragraph("Operation and Maintenance Manual", h2),
          Paragraph("1  Introduction", h1),
          Paragraph("This manual covers the operation, inspection and field maintenance of the "
                    "675 Series positive displacement motor (PDM). The motor converts the hydraulic "
                    "energy of the drilling fluid into mechanical rotation at the bit. It shall be "
                    "operated only by personnel who have been trained in downhole motor handling "
                    "and who are familiar with API RP 7G drill stem design practices.", body),
          Paragraph("The power section consists of a rotor and a stator. The rotor is a helical "
                    "steel shaft with one lobe fewer than the elastomer-lined stator. When fluid is "
                    "pumped through the power section, the rotor turns eccentrically inside the "
                    "stator, and the transmission converts this eccentric motion into concentric "
                    "rotation of the drive shaft. Bearings in the bearing assembly carry the "
                    "on-bottom and off-bottom axial loads as well as the radial loads.", body),
          Paragraph("2  Specifications", h1),
          Paragraph("Table 2-1 lists the nominal specifications. Values are for a 7/8 lobe, "
                    "5.0 stage power section with a standard fit.", body),
          Paragraph("Table 2-1  Motor Specifications", cap),
          tbl([["Parameter", "Value", "Unit"],
               ["Tool OD", "6.75", "in"],
               ["Overall length", "25.4", "ft"],
               ["Flow rate range", "300 - 600", "gpm"],
               ["Max. differential pressure", "1,000", "psi"],
               ["Output speed", "0.26", "rev/gal"],
               ["Max. operating torque", "8,950", "ft-lbf"],
               ["Bit connection", "4-1/2 REG", "box"],
               ["Top connection", "4-1/2 IF", "box"],
               ["Assembly part number", "80020610", "-"]], [220, 120, 80]),
          Spacer(1, 8),
          Paragraph("3  Operation", h1),
          Paragraph("<b>WARNING:</b> Do not exceed the maximum differential pressure of 1,200 psi. "
                    "Stalling the motor can cause chunking of the stator elastomer and loss of "
                    "the power section. If H2S is expected, use stators rated for sour service.", warn),
          Paragraph("3.1  Surface Test", h2),
          Paragraph("1. Make up the motor to the kelly or top drive using the torque values in Table 4-1.", body),
          Paragraph("2. Start the pumps slowly and increase the flow rate to 300 gpm. The bit box should rotate freely.", body),
          Paragraph("3. Record the off-bottom pressure. This value is required to calculate the "
                    "differential pressure while drilling.", body),
          Paragraph("4. Stop the pumps and check that the drill string drains through the dump valve.", body),
          Paragraph("3.2  Drilling", h2),
          Paragraph("Run in the hole at a controlled speed of no more than 90 ft/min through casing. "
                    "Tag bottom gently, then pick up 1-2 ft and establish circulation. Apply weight on "
                    "bit gradually while monitoring the standpipe pressure:", body),
          Paragraph("• increase in pressure indicates increased torque at the bit;", body),
          Paragraph("• a sudden pressure spike followed by no rotation indicates a stall;", body),
          Paragraph("• when stalled, pick up off bottom immediately before restarting.", body),
          PageBreak(),
          Paragraph("Figure 3-1 shows the main sub-assemblies of the motor.", body),
          MotorFig(),
          Paragraph("Figure 3-1  Motor Assembly", cap),
          Paragraph("4  Maintenance", h1),
          Paragraph("After each run, flush the motor with fresh water and inspect the bearing play. "
                    "Axial play greater than 0.25 in. indicates bearing wear; the motor must be "
                    "returned to the service center. Measure the stator ID and the rotor OD as described in "
                    "ASTM A370 and the service manual NDT-SM-675.", body),
          Paragraph("Table 4-1  Make-up Torque", cap),
          tbl([["Connection", "Size", "Min. torque (ft-lbf)", "Max. torque (ft-lbf)"],
               ["Top sub to stator", "6-5/8 REG", "12,500", "14,000"],
               ["Stator to transmission housing", "6-5/8 REG", "12,500", "14,000"],
               ["Bearing housing to bit box", "5-1/2 FH", "10,200", "11,500"]], [170, 90, 110, 110]),
          Spacer(1, 8),
          Paragraph("<b>CAUTION:</b> Always use a calibrated torque gauge. Over-torquing the "
                    "connections will damage the threads and the elastomer bond.", warn),
          ]
    if repeat > 1:
        extra = []
        for i in range(repeat - 1):
            extra.append(PageBreak())
            extra.append(Paragraph("%d  Field Troubleshooting Case %d" % (5 + i, i + 1), h1))
            for j in range(9):
                extra.append(Paragraph(
                    "Case %d.%d: The standpipe pressure rose by %d psi while the rate of penetration "
                    "dropped by %d ft/hr. The crew picked up off bottom, reduced the weight on bit to "
                    "%d klbs and resumed drilling. The root cause was bit balling in the reactive "
                    "shale section; a higher flow rate of %d gpm was recommended." %
                    (i + 1, j + 1, 150 + 10 * j, 5 + j, 20 + j, 450 + 10 * j), body))
        S += extra
    return S

def make_manual(path, repeat=1, title="Operation & Maintenance Manual", docno="NDT-OM-675 Rev B"):
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=54, rightMargin=54,
                            topMargin=72, bottomMargin=54, title="675 PDM O&M Manual")
    f = hf(title, docno)
    doc.build(manual_story(repeat), onFirstPage=f, onLaterPages=f)

def make_drawing(path):
    W, H = landscape(letter)
    c = canvas.Canvas(path, pagesize=(W, H))
    c.setLineWidth(1.2); c.rect(18, 18, W - 36, H - 36)
    # part outline (stator housing section) with hatch -> many paths
    c.setLineWidth(0.8)
    x0, y0, L, D = 80, 300, 420, 90
    c.rect(x0, y0, L, D); c.rect(x0 + 20, y0 + 15, L - 40, D - 30)
    random.seed(1)
    c.setLineWidth(0.25)
    for i in range(0, 1700):
        xx = x0 + (i % 420)
        if (i // 420) % 2 == 0:
            c.line(xx, y0, xx + 6, y0 + 15) if xx + 6 < x0 + L else None
        else:
            c.line(xx, y0 + D - 15, xx + 6, y0 + D) if xx + 6 < x0 + L else None
    for i in range(1500):   # knurl / thread marks
        a = i * 0.05
        c.line(x0 - 30 + (i % 25), y0 + 20 + (i % 50), x0 - 28 + (i % 25), y0 + 22 + (i % 50))
    # dimensions
    c.setFont("Helvetica", 8)
    c.line(x0, y0 - 25, x0 + L, y0 - 25); c.drawCentredString(x0 + L / 2, y0 - 35, "54.00 ±0.03")
    c.drawString(x0 + L + 10, y0 + D / 2, "Ø6.75 OD")
    c.drawString(x0 + L + 10, y0 + D / 2 - 12, "Ø5.10 ID")
    c.drawString(x0 + 30, y0 + D + 12, "ELASTOMER LINING (NBR, 7/8 LOBE)")
    c.drawString(x0 + 260, y0 + D + 12, "SEE DETAIL A")
    c.drawString(x0 - 40, y0 - 60, "6-5/8 REG PIN")
    c.drawString(x0 + L - 40, y0 - 60, "6-5/8 REG BOX")
    # notes
    c.setFont("Helvetica-Bold", 9); c.drawString(520, 520, "NOTES:")
    c.setFont("Helvetica", 8)
    notes = ["UNLESS OTHERWISE SPECIFIED:", "1. ALL DIMENSIONS ARE IN INCHES.",
             "2. BREAK ALL SHARP EDGES 0.015 MAX.", "3. THREADS PER API SPEC 7-2.",
             "4. PHOSPHATE COAT ALL THREADS AFTER INSPECTION.",
             "5. MAGNETIC PARTICLE INSPECT PER ASTM E709."]
    for i, n in enumerate(notes):
        c.drawString(520, 505 - 12 * i, n)
    # BOM
    bx, by = 500, 300
    rows = [("ITEM", "PART NO.", "DESCRIPTION", "QTY"),
            ("1", "80020611", "STATOR HOUSING, 6-3/4", "1"),
            ("2", "80020612", "ELASTOMER LINER, 7/8 LOBE", "1"),
            ("3", "80020613", "WEAR SLEEVE", "2"),
            ("4", "10030045", "O-RING, 2-352 NBR 90", "4")]
    cw = [30, 60, 120, 25]
    for r, row in enumerate(rows):
        xx = bx
        for k, cell in enumerate(row):
            c.rect(xx, by - r * 14, cw[k], 14)
            c.setFont("Helvetica-Bold" if r == 0 else "Helvetica", 7)
            c.drawString(xx + 2, by - r * 14 + 4, cell)
            xx += cw[k]
    # title block
    tx, ty = 560, 30
    c.rect(tx, ty, 210, 90)
    for yy in (60, 75, 90):
        c.line(tx, ty + yy - 30, tx + 210, ty + yy - 30)
    c.setFont("Helvetica-Bold", 10); c.drawString(tx + 5, ty + 75, "NORTHSTAR DRILLING TOOLS")
    c.setFont("Helvetica", 8)
    c.drawString(tx + 5, ty + 50, "TITLE: STATOR HOUSING ASSY, 675 PDM")
    c.drawString(tx + 5, ty + 35, "DWG NO: 675-200-011    REV: C")
    c.drawString(tx + 5, ty + 20, "SCALE: 1:4    SHEET 1 OF 1")
    c.drawString(tx + 5, ty + 5, "DRAWN: J. SMITH   CHECKED: R. LEE")
    c.save()

def main(out="."):
    import os
    os.makedirs(out, exist_ok=True)
    make_manual(os.path.join(out, "mud_motor_manual.pdf"))
    make_manual(os.path.join(out, "mud_motor_manual_long.pdf"), repeat=22)
    make_drawing(os.path.join(out, "stator_housing_drawing.pdf"))
    return out


if __name__ == "__main__":
    import sys
    print("生成于", main(sys.argv[1] if len(sys.argv) > 1 else "."))
