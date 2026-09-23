# -*- coding: utf-8 -*-
"""生成展示用的**虚构**工程图纸（英文源）：TDT-650-0100 6-1/2" 减震器总装图，3 张 B 号（11×17 in）。

品牌、图号、零件号、人名全部虚构；图形为程序绘制的示意剖视图，不代表任何真实产品。
复刻的是真实 CAD 导出图纸在翻译时的难点，而不是某一张具体图纸：

  - 矢量剖视图 + 剖面线 + 件号气泡 + 引线扭矩标注：**只换字、不动线**（叠印保位）；
  - 明细表：线条是路径 item，ITEM/QTY 两列用「缺行线」表示纵向合并（一个件号三种可选件）；
  - 明细表里 CAD 导出的**重影文字**（同一串在同一位置写了两遍）；
  - 标题栏「UNLESS OTHERWISE SPECIFIED」注记格：± / ° / 粗糙度符号是**矢量**，小数点列靠前导空格对齐；
  - 物理断行的长句（总注、专有声明、标题三行）；竖排（旋转 90°）尺寸文字；
  - 有意埋两处原文缺陷：可选件备注引错件号；碟簧备注片数与数量栏、剖视图不一致。

    python make_drawing.py [输出.pdf]
"""
import math
import os
import sys

from reportlab.lib.pagesizes import landscape, TABLOID
from reportlab.pdfgen import canvas

W, H = landscape(TABLOID)          # 1224 × 792 pt
FONT, BOLD = "Helvetica", "Helvetica-Bold"
DWG = "TDT-650-0100"


def Y(y):                          # 设计坐标取「左上原点」，换成 PDF 的左下原点
    return H - y


class Sheet:
    def __init__(self, c):
        self.c = c

    # ---- 基本图元
    def line(self, x0, y0, x1, y1, w=0.6, dash=None):
        c = self.c
        c.setLineWidth(w)
        if dash:
            c.setDash(list(dash))
        c.line(x0, Y(y0), x1, Y(y1))
        c.setDash([])

    def rect(self, x0, y0, x1, y1, w=0.6):
        self.c.setLineWidth(w)
        self.c.rect(x0, Y(y1), x1 - x0, y1 - y0)

    def text(self, x, y, s, size=7.5, font=FONT, align="l", twice=False):
        """y = 基线（左上原点）。twice=True 复刻 CAD 导出的重影文字（同位写两遍）。"""
        c = self.c
        c.setFont(font, size)
        for _ in range(2 if twice else 1):
            if align == "c":
                c.drawCentredString(x, Y(y), s)
            elif align == "r":
                c.drawRightString(x, Y(y), s)
            else:
                c.drawString(x, Y(y), s)

    def vtext(self, x, y, s, size=7.5):
        """竖排（逆时针 90°）文字，以 (x, y) 为中心。"""
        c = self.c
        c.saveState()
        c.translate(x, Y(y))
        c.rotate(90)
        c.setFont(FONT, size)
        c.drawCentredString(0, 0, s)
        c.restoreState()

    def arrow(self, x, y, ang, L=6.0, w=2.0):
        """箭头尖在 (x, y)，指向 ang（度，左上原点坐标系）。"""
        a = math.radians(ang)
        bx, by = x - L * math.cos(a), y - L * math.sin(a)
        nx, ny = -math.sin(a) * w, math.cos(a) * w
        p = self.c.beginPath()
        p.moveTo(x, Y(y))
        p.lineTo(bx + nx, Y(by + ny))
        p.lineTo(bx - nx, Y(by - ny))
        p.close()
        self.c.drawPath(p, stroke=0, fill=1)

    def leader(self, x0, y0, x1, y1, w=0.5):
        """引线：从 (x0,y0) 到箭头尖 (x1,y1)。"""
        self.line(x0, y0, x1, y1, w)
        self.arrow(x1, y1, math.degrees(math.atan2(y1 - y0, x1 - x0)))

    def balloon(self, cx, cy, n, tx, ty, r=9.5):
        c = self.c
        c.setLineWidth(0.6)
        c.circle(cx, Y(cy), r)
        self.text(cx, cy + 2.8, str(n), 8, align="c")
        a = math.atan2(ty - cy, tx - cx)
        self.line(cx + r * math.cos(a), cy + r * math.sin(a), tx, ty, 0.5)
        c.circle(tx, Y(ty), 1.2, stroke=0, fill=1)

    # ---- 剖视图零件：分段外/内半径 → 上下两片壁，带剖面线
    def part(self, yc, segs, hatch=45, gap=4.2, phantom=False):
        """segs = [(x0, x1, ro, ri), …] 连续分段；画上下两片壁的轮廓与剖面线。"""
        c = self.c
        for sgn in (-1, 1):
            top = []
            for x0, x1, ro, ri in segs:
                top += [(x0, yc + sgn * ro), (x1, yc + sgn * ro)]
            bot = []
            for x0, x1, ro, ri in reversed(segs):
                bot += [(x1, yc + sgn * ri), (x0, yc + sgn * ri)]
            pts = top + bot
            p = c.beginPath()
            p.moveTo(pts[0][0], Y(pts[0][1]))
            for x, y in pts[1:]:
                p.lineTo(x, Y(y))
            p.close()
            c.setLineWidth(0.7)
            if phantom:
                c.setDash([8, 2, 2, 2])
                c.drawPath(p, stroke=1, fill=0)
                c.setDash([])
                continue
            c.drawPath(p, stroke=1, fill=0)
            c.saveState()
            c.clipPath(p, stroke=0, fill=0)
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            h = y1 - y0
            k = 1 if (hatch == 45) == (sgn > 0) else -1
            c.setLineWidth(0.3)
            hp = c.beginPath()
            x = x0 - h
            while x < x1 + h:
                hp.moveTo(x, Y(y0))
                hp.lineTo(x + k * h, Y(y1))
                x += gap
            c.drawPath(hp, stroke=1, fill=0)
            c.restoreState()

    def thread(self, yc, x0, x1, r, pitch=3.0, amp=1.4):
        c = self.c
        c.setLineWidth(0.35)
        for sgn in (-1, 1):
            p = c.beginPath()
            p.moveTo(x0, Y(yc + sgn * r))
            x, up = x0, True
            while x < x1:
                x = min(x + pitch / 2, x1)
                p.lineTo(x, Y(yc + sgn * (r + (amp if up else -amp) / 2)))
                up = not up
            c.drawPath(p, stroke=1, fill=0)

    def centerline(self, x0, x1, yc):
        self.line(x0, yc, x1, yc, 0.35, dash=(18, 3, 3, 3))

    def oring(self, x, y, r=2.2):
        self.c.circle(x, Y(y), r, stroke=1, fill=1)

    def disc_stack(self, yc, x0, n, pitch, ro, ri):
        """碟形弹簧串联叠装：剖面是一条折线，每一折是一片碟簧（相邻两片凸面相对）。"""
        c = self.c
        c.setLineWidth(1.3)
        for sgn in (-1, 1):
            p = c.beginPath()
            for k in range(n + 1):
                r = ri if k % 2 == 0 else ro
                (p.moveTo if k == 0 else p.lineTo)(x0 + k * pitch, Y(yc + sgn * r))
            c.drawPath(p, stroke=1, fill=0)

    def hdim(self, x0, x1, y, top, bottom=None, ext_to=None):
        """水平尺寸：两端箭头，数值在线上方、说明在线下方。"""
        self.line(x0, y, x1, y, 0.45)
        self.arrow(x0, y, 180)
        self.arrow(x1, y, 0)
        if ext_to is not None:
            self.line(x0, y - 4, x0, ext_to, 0.35)
            self.line(x1, y - 4, x1, ext_to, 0.35)
        xm = (x0 + x1) / 2
        self.text(xm, y - 3, top, 8, align="c")
        if bottom:
            self.text(xm, y + 9, bottom, 8, align="c")

    def vdim(self, x, y0, y1, label, ext_from=None):
        self.line(x, y0, x, y1, 0.45)
        self.arrow(x, y0, -90)
        self.arrow(x, y1, 90)
        if ext_from is not None:
            self.line(ext_from, y0, x + 4, y0, 0.35)
            self.line(ext_from, y1, x + 4, y1, 0.35)
        self.vtext(x - 4, (y0 + y1) / 2, label, 7.5)

    def callout(self, x, y, lines, tx, ty, align="l", size=7.5):
        """引线标注：多行文字块 + 从首行**左端**引出的折线箭头（CAD 的常见排法：文字在
        零件右侧时左对齐、引线接在行首）。align="r" 的块是右对齐的，引线同样接在首行左端 ——
        这类块的首行是扭矩值，原样保留，引线始终接得上。"""
        for i, s in enumerate(lines):
            self.text(x, y + i * 9.5, s, size, align=align)
        c = self.c
        c.setFont(FONT, size)
        w = c.stringWidth(lines[0], FONT, size)
        ex = x - 2 if align == "l" else x - w - 2
        self.line(ex, y - 2.5, ex - 6, y - 2.5, 0.5)
        self.leader(ex - 6, y - 2.5, tx, ty)

    # ---- 图框、修订栏、标题栏、明细表
    def frame(self, sheet):
        self.rect(18, 18, W - 18, H - 18, 1.2)
        self.rect(36, 36, W - 36, H - 36, 0.9)
        for i in range(8):
            x = 36 + (W - 72) * (i + 0.5) / 8
            for yy in (30, H - 24):
                self.text(x, yy, str(8 - i), 7, align="c")
            if i:
                xx = 36 + (W - 72) * i / 8
                self.line(xx, 18, xx, 36, 0.4)
                self.line(xx, H - 36, xx, H - 18, 0.4)
        for j, L in enumerate("DCBA"):
            y = 36 + (H - 72) * (j + 0.5) / 4
            for xx in (27, W - 27):
                self.text(xx, y + 2.5, L, 7, align="c")
            if j:
                yy = 36 + (H - 72) * j / 4
                self.line(18, yy, 36, yy, 0.4)
                self.line(W - 36, yy, W - 18, yy, 0.4)
        self.revisions()
        self.title_block(sheet)

    def revisions(self):
        x = [880, 910, 1080, 1128, 1156, 1188]
        ys = [36, 50, 62, 76, 90]
        self.rect(x[0], ys[0], x[-1], ys[-1], 0.8)
        for yy in ys[1:-1]:
            self.line(x[0], yy, x[-1], yy, 0.5)
        for xx in x[1:-1]:
            self.line(xx, ys[1], xx, ys[-1], 0.5)
        self.text((x[0] + x[-1]) / 2, 47, "REVISIONS", 9, BOLD, "c")
        for k, h in enumerate(("REV", "DESCRIPTION", "DATE", "BY", "APPR.")):
            self.text((x[k] + x[k + 1]) / 2, 59, h, 6.2, align="c")
        rows = [("A", "INITIAL RELEASE, ECO 1042", "11-20-25", "AR", "MO"),
                ("B", "ADDED ALT. HOUSINGS, ECO 1107", "03-12-26", "AR", "MO")]
        for r, row in enumerate(rows):
            yb = ys[2 + r] + 9.8
            for k, s in enumerate(row):
                if k == 0:
                    self.text((x[0] + x[1]) / 2, yb + 0.6, s, 10, BOLD, "c")
                elif k == 1:
                    self.text(x[1] + 3, yb, s, 6.2)
                else:
                    self.text((x[k] + x[k + 1]) / 2, yb, s, 6.2, align="c")

    def title_block(self, sheet):
        xa, xb, xc, xr = 712, 846, 972, 1188
        y0, yb = 606, 756
        self.rect(xa, y0, xr, yb, 0.9)
        self.line(xb, y0, xb, 742, 0.6)
        self.line(xc, y0, xc, yb, 0.9)
        # A 栏：热处理 / 制图 / 校核 / 批准 / 专有声明
        for yy in (620, 634, 648, 662, 676):
            self.line(xa, yy, xb, yy, 0.5)
        self.line(xb, 620, xc, 620, 0.5)
        self.line(xa, 742, xc, 742, 0.5)
        self.line(760, 620, 760, 662, 0.5)
        self.line(788, 620, 788, 662, 0.5)
        self.text(xa + 3, 615.5, "HEAT TREAT:", 6.2)
        self.text(800, 616.5, "N/A", 8, align="c")
        for yy, lab, who, dt in ((620, "DRAWN", "AR", "11-20-25"), (634, "CHECKED", "MO", "11-24-25"),
                                 (648, "ENG APPR.", "AR", "11-26-25")):
            self.text(736, yy + 9.5, lab, 6.2, align="c")
            self.text(774, yy + 10, who, 8, align="c")
            self.text(817, yy + 10, dt, 8, align="c")
        notice = ["PROPRIETARY NOTICE", "THIS FICTIONAL DRAWING WAS", "PREPARED FOR THE PDF-TRANSLATE-ZH",
                  "PROJECT AS A DEMONSTRATION. IT DOES",
                  "NOT DESCRIBE A REAL PRODUCT AND", "MUST NOT BE USED FOR MANUFACTURE."]
        for i, s in enumerate(notice):
            self.text(xa + 3, 686 + i * 7.2, s, 5.7, BOLD if i == 0 else FONT)
        self.text(xa + 3, 751, "INTERPRET DIMENSIONS AND TOLERANCES PER ASME Y14.5-2018.", 5.7)
        # B 栏：材料 + 「除另有规定外」注记（± / ° / 粗糙度为矢量）
        self.text(xb + 3, 615.5, "MATERIAL:", 6.2)
        self.text(930, 616.5, "SEE BOM", 8, align="c")
        self.note_cell(xb + 3, 628)
        # C 栏：商号、图名、零件号/图号、比例/重量/张次
        for yy in (660, 702, 732):
            self.line(xc, yy, xr, yy, 0.6)
        self.line(1080, 702, 1080, 732, 0.6)
        self.line(1036, 732, 1036, 756, 0.6)
        self.line(1128, 732, 1128, 756, 0.6)
        self.logo(xc + 10, 638)
        self.text(1070, 630, "TETHYS DOWNHOLE TOOLS", 6.4, BOLD)
        self.text(1070, 638, "HARBOR POINT ASSEMBLY SHOP", 5.6)
        self.text(1070, 645, "FICTIONAL DEMONSTRATION ONLY", 5.6)
        for i, s in enumerate(('6-1/2" SHOCK SUB ASSEMBLY,', "DUAL SPRING STACK")):
            self.text((xc + xr) / 2, 677 + i * 15, s, 12.5, align="c")
        self.text(xc + 3, 711, "PART NO.", 7)
        self.text(1083, 711, "DWG. NO.", 7)
        self.text(1026, 727, DWG, 12, align="c")
        self.text(1134, 727, DWG + "B", 12, align="c")
        self.text(xc + 3, 747, "SCALE: 1:4", 8)
        self.text(1039, 747, "WEIGHT: 640 LBS", 7.2)
        self.text(1131, 747, "SHEET %d OF 3" % sheet, 8)

    def note_cell(self, x, y):
        """「除另有规定外」注记：英文照 CAD 样板排；± / ° / ∨ 画成一条矢量路径（CAD 导出即如此）。"""
        L = 7.35
        s = 5.9
        self.text(x, y + 6, "UNLESS OTHERWISE SPECIFIED:", 6.6)
        self.line(x, y + 7.2, x + self.c.stringWidth("UNLESS OTHERWISE SPECIFIED:", FONT, 6.6), y + 7.2, 0.4)
        self.text(x, y + 6 + L, "DIMENSIONS ARE IN INCHES", s)
        fy = y + 6 + 2 * L
        self.text(x, fy, "FINISH:  ", s)
        self.text(x + 25, fy - 3.4, "125", 3.9)
        self.text(x + 36, fy, "MAX.; ", s)
        self.text(x + 56, fy - 3.4, "32", 3.9)
        self.text(x + 66, fy, "ON ALL ", s)
        rows = ["THREADS & RELIEF SURFACES.", "BREAK ALL SHARP CORNERS.", "REMOVE ALL BURRS.", "TOLERANCES:",
                "ANGULAR:                    1 - 0'",
                "DECIMAL:           .XXX   .005",
                "                            .XX     .010",
                "                            .X       .030",
                "FRACTIONAL:                1/32",
                "ALL UNSPECIFIED DIAMETERS TO ",
                "BE WITHIN .003 TIR."]
        for i, r in enumerate(rows):
            self.text(x, fy + (i + 1) * L, r, s)
        # 矢量符号：粗糙度 ∨ ×2、± ×5、° ×1 —— 一条路径
        c = self.c
        c.setLineWidth(0.35)
        p = c.beginPath()

        def vee(vx, vy):
            p.moveTo(vx, Y(vy - 3.2))
            p.lineTo(vx + 1.6, Y(vy))
            p.lineTo(vx + 4.2, Y(vy - 5.0))

        def pm(px, py):
            p.moveTo(px, Y(py - 2.4))
            p.lineTo(px + 2.3, Y(py - 2.4))
            p.moveTo(px + 1.15, Y(py - 3.6))
            p.lineTo(px + 1.15, Y(py - 1.2))
            p.moveTo(px, Y(py))
            p.lineTo(px + 2.3, Y(py))

        vee(x + 30, fy)
        vee(x + 60, fy)

        def at(prefix):
            return x + c.stringWidth(prefix, FONT, s)

        ay = fy + 5 * L
        a1 = at("ANGULAR:                    ")
        pm(a1 - 3.4, ay)
        p.circle(a1 + c.stringWidth("1", FONT, s) + 1.0, Y(ay - 4.0), 0.55)
        for k, pre in enumerate(("DECIMAL:           .XXX   ", "                            .XX     ",
                                 "                            .X       ", "FRACTIONAL:                ")):
            pm(at(pre) - 3.2, ay + (k + 1) * L)
        c.drawPath(p, stroke=1, fill=0)

    def logo(self, x, y):
        c = self.c
        c.setLineWidth(3.2)
        for k in range(3):
            yy = y - 12 + k * 7
            p = c.beginPath()
            p.moveTo(x, Y(yy))
            p.curveTo(x + 10, Y(yy - 6), x + 20, Y(yy + 6), x + 30, Y(yy))
            c.drawPath(p, stroke=1, fill=0)
        c.setFont(BOLD, 17)
        c.drawString(x + 36, Y(y), "tethys")

    def bom(self, rows):
        """rows = [(item, part, desc, qty, notes, merge_next), …] 自下而上逐行画；
        merge_next=True 表示与下一行在 ITEM/QTY 两列纵向合并（此处**不画**那两列的行线）。"""
        xs = [36, 80, 160, 430, 470, 700]
        rh = 14.4
        n = len(rows)
        yb = H - 50                   # 明细表底边不与图框线共线（共线会被当成图框线剔除）
        ytop = yb - (n + 1) * rh
        self.rect(xs[0], ytop, xs[-1], yb, 0.8)
        for xx in xs[1:-1]:
            self.line(xx, ytop, xx, yb, 0.5)
        for k, h in enumerate(("ITEM", "PART NO.", "DESCRIPTION", "QTY", "NOTES")):
            self.text((xs[k] + xs[k + 1]) / 2, ytop + 10.3, h, 7.8, BOLD, "c")
        self.line(xs[0], ytop + rh, xs[-1], ytop + rh, 0.8)
        span = []
        for i, (item, part, desc, qty, note, merge, twice) in enumerate(rows):
            y0 = ytop + (i + 1) * rh
            if i:
                prev_merge = rows[i - 1][5]
                if prev_merge:          # 合并：ITEM/QTY 两列不画行线
                    self.line(xs[1], y0, xs[3], y0, 0.5)
                    self.line(xs[4], y0, xs[5], y0, 0.5)
                else:
                    self.line(xs[0], y0, xs[-1], y0, 0.5)
            if not span:
                head = (item, qty)
            span.append(i)
            self.text((xs[1] + xs[2]) / 2, y0 + 10.2, part, 7.5, align="c")
            self.text((xs[2] + xs[3]) / 2, y0 + 10.2, desc, 7.5, align="c", twice=twice)
            self.text((xs[4] + xs[5]) / 2, y0 + 10.2, note, 7.5, align="c")
            if not merge:
                ya = ytop + (span[0] + 1) * rh
                yz = y0 + rh
                ym = (ya + yz) / 2 + 2.8
                self.text((xs[0] + xs[1]) / 2, ym, head[0], 7.5, align="c")
                self.text((xs[3] + xs[4]) / 2, ym, head[1], 7.5, align="c")
                span = []


def R(item, part, desc, qty="1", note="", merge=False, twice=False):
    return (item, part, desc, qty, note, merge, twice)


# ---------------------------------------------------------------- 第 1 张：总览 + 下端剖视
def sheet1(s):
    s.frame(1)
    s.text(50, 62, "NOTES:", 8.5, BOLD)
    notes = ["1.  CLEAN ALL THREADS AND SEAL BORES BEFORE ASSEMBLY.",
             "2.  APPLY ANTI-SEIZE COMPOUND TO ALL TOOL JOINT CONNECTIONS UNLESS",
             "     OTHERWISE NOTED.",
             "3.  PRESSURE TEST SEAL SECTION TO 1,500 PSI FOR 10 MINUTES WITH NO VISIBLE",
             "     LEAKAGE. RECORD THE RESULT ON THE ASSEMBLY TRAVELER.",
             "4.  STAMP ASSEMBLY SERIAL NUMBER ON ITEM 20 WITHIN 2.0\" OF THE SHOULDER."]
    for i, n in enumerate(notes):
        s.text(50, 75 + i * 10, n, 7.2)
    # 总览
    yc = 232
    segs = [(150, 250, 12, 7), (250, 1020, 13, 8), (1020, 1100, 11, 6)]
    s.centerline(135, 1115, yc)
    for x0, x1, ro, ri in segs:
        s.rect(x0, yc - ro, x1, yc + ro, 0.7)
    s.line(430, yc - 13, 430, yc + 13, 0.5)
    s.line(700, yc - 13, 700, yc + 13, 0.5)
    for x in range(470, 690, 14):                      # 碟簧示意
        s.line(x, yc - 8, x + 6, yc + 8, 0.35)
    s.hdim(150, 1100, 164, '68.4"', "OAL", ext_to=yc - 14)
    s.hdim(150, 470, 196, '22.5"', "BOX TO SPRING STACK", ext_to=yc - 14)
    s.text(150, 262, "BOX END (UPHOLE)", 7.5)
    s.text(1100, 262, "PIN END (DOWNHOLE)", 7.5, align="r")
    s.text(625, 285, "ASSEMBLY OVERVIEW", 9, BOLD, "c")
    s.text(625, 296, "SCALE 1:12", 7.5, align="c")
    # 剖视 A-A：下端
    yc = 420
    s.centerline(180, 1060, yc)
    s.part(yc, [(200, 520, 42, 30)], 45)                                   # 2 壳体（下端）
    s.part(yc, [(440, 520, 29.5, 22), (520, 920, 42, 22), (920, 1010, 35, 20)], 135)   # 20 下接头
    s.thread(yc, 446, 516, 30)
    s.thread(yc, 925, 1005, 36.5, pitch=4, amp=2)
    s.part(yc, [(200, 600, 20, 12)], 45, gap=3.4)                           # 3 芯轴
    s.part(yc, [(200, 236, 30, 20)], 135, gap=3.0)                         # 19 下密封座
    s.part(yc, [(240, 380, 30, 20)], 135, gap=4.6)                          # 17 花键套
    s.part(yc, [(384, 432, 30, 20)], 135, gap=2.6)                         # 18 锁紧螺母
    s.thread(yc, 388, 430, 20)
    for x in (212, 224):
        for sg in (-1, 1):
            s.oring(x, yc + sg * 30)
            s.oring(x, yc + sg * 20)
    s.rect(326, yc - 47, 338, yc - 42, 0.6)                                # 21 注脂嘴
    s.rect(470, yc - 45, 480, yc - 42, 0.6)                                # 22 堵头
    for n, bx, tx, ty in ((19, 214, 218, yc - 25), (17, 300, 300, yc - 25), (21, 350, 332, yc - 46),
                          (18, 408, 408, yc - 25), (22, 490, 475, yc - 44), (20, 700, 700, yc - 32)):
        s.balloon(bx, 344, n, tx, ty)
    s.callout(410, 496, ["2,000 ± 100 FT-LBS", "LEFT HAND", "THREAD LOCKER, MEDIUM STRENGTH"],
              408, yc + 24, align="r")
    s.callout(560, 496, ["18,000 ± 1,000 FT-LBS", "ANTI-SEIZE COMPOUND"], 500, yc + 32)
    s.callout(560, 350, ["25 ± 5 FT-LBS", "PIPE SEALANT"], 478, yc - 45)
    s.text(960, 486, "API 4-1/2 IF PIN", 7.5, align="c")
    s.line(960, 478, 960, yc + 36, 0.4)
    s.vdim(1050, yc - 42, yc + 42, "Ø6.50 OD", ext_from=925)
    s.text(625, 552, "SECTION A-A", 9, BOLD, "c")
    s.text(625, 563, "SCALE 1:4", 7.5, align="c")
    s.bom([R("17", "TDT-650-1701", "SPLINE SLEEVE, 6-1/2"),
           R("18", "TDT-650-1801", "LOCK NUT, 4-1/2 UN, LEFT HAND"),
           R("19", "TDT-650-1901", "SEAL CARRIER, LOWER"),
           R("20", "TDT-650-2001", "BOTTOM SUB, 6-1/2", note="API 4-1/2 IF PIN"),
           R("21", "TDT-00-0121", "GREASE FITTING, 1/8 NPT", "2"),
           R("22", "TDT-00-0122", "PIPE PLUG, 1/8 NPT, SOCKET HEAD", "2")])


# ---------------------------------------------------------------- 第 2 张：弹簧组剖视
def sheet2(s):
    s.frame(2)
    yc = 300
    s.centerline(130, 1110, yc)
    s.part(yc, [(150, 1050, 42, 32)], 45)                                  # 2 壳体
    s.part(yc, [(150, 1090, 20, 12)], 135, gap=3.4)                        # 3 芯轴
    s.part(yc, [(250, 296, 32, 20)], 135, gap=3.0)                         # 10 上导向
    s.disc_stack(yc, 300, 8, 24.5, 31, 21)                                   # 9 碟簧 ×8
    s.part(yc, [(496, 540, 32, 20)], 45, gap=2.6)                          # 16 垫圈
    s.disc_stack(yc, 542, 8, 24.5, 31, 21)                                   # 9 碟簧 ×8
    s.part(yc, [(740, 790, 32, 20)], 135, gap=3.0)                         # 11 下导向
    s.part(yc, [(800, 818, 32, 20)], 45, gap=2.2)                          # 14 轴承座圈
    s.part(yc, [(818, 882, 32, 20)], 135, gap=6.0)                         # 13 推力轴承
    s.part(yc, [(882, 900, 32, 20)], 45, gap=2.2)                          # 14 轴承座圈
    for sg in (-1, 1):
        for x in (758, 772):
            s.oring(x, yc + sg * 20)
        for k in range(4):
            s.c.circle(830 + k * 14, Y(yc + sg * 26), 4.2, stroke=1, fill=0)
    s.part(yc, [(600, 800, 46, 42)], phantom=True)                         # 15 耐磨套（光壳体选用）
    for n, bx, tx, ty in ((10, 272, 272, yc - 26), (9, 380, 372, yc - 26), (16, 518, 518, yc - 26),
                          (15, 640, 640, yc - 44), (11, 766, 764, yc - 26), (14, 809, 809, yc - 26),
                          (13, 850, 850, yc - 26), (12, 910, 772, yc - 20)):
        s.balloon(bx, 220, n, tx, ty)
    s.callout(350, 385, ["DISC SPRINGS STACKED IN SERIES,", "CONVEX FACES OPPOSED"], 330, yc + 28)
    s.callout(560, 395, ["SHIM ITEM 16 TO OBTAIN 0.020 - 0.040", "STACK PRELOAD GAP"], 518, yc + 30)
    s.callout(900, 380, ["LUBRICATE O-RINGS WITH", "SEAL GREASE BEFORE INSTALLING"], 772, yc + 21, align="l")
    s.callout(730, 244, ["SLICK HOUSING ONLY"], 700, yc - 46)
    s.vdim(1112, yc - 32, yc + 32, "Ø4.25 SPRING BORE", ext_from=1000)
    s.text(625, 470, "SECTION B-B", 9, BOLD, "c")
    s.text(625, 481, "SCALE 1:4", 7.5, align="c")
    s.bom([R("9", "TDT-650-0901", "DISC SPRING, 4.25 OD X 2.25 ID", "16", "10 PER STACK, 2 STACKS"),
           R("10", "TDT-650-1001", "SPRING GUIDE, UPPER"),
           R("11", "TDT-650-1101", "SPRING GUIDE, LOWER"),
           R("12", "TDT-00-0112", "O-RING, 2-342, HNBR 90", "2", twice=True),
           R("13", "TDT-650-1301", "THRUST BEARING, 4-3/4"),
           R("14", "TDT-650-1401", "BEARING RACE, THRUST", "2"),
           R("15", "TDT-650-1501", "WEAR SLEEVE, SLICK HOUSING", note="SLICK HOUSING ONLY"),
           R("16", "TDT-650-1601", "SPACER, SPRING STACK", note="SELECT FIT AT ASSEMBLY")])


# ---------------------------------------------------------------- 第 3 张：上端剖视 + 局部详图
def sheet3(s):
    s.frame(3)
    yc = 360
    s.centerline(100, 1110, yc)
    s.part(yc, [(120, 190, 42, 31), (190, 420, 42, 18), (420, 500, 31.5, 18)], 135)   # 1 上接头
    s.thread(yc, 124, 186, 31, pitch=4, amp=2)
    s.thread(yc, 426, 496, 32)
    s.part(yc, [(420, 1060, 42, 32)], 45)                                  # 2 壳体
    s.part(yc, [(520, 1100, 20, 12)], 135, gap=3.4)                        # 3 芯轴
    s.part(yc, [(520, 590, 32, 20)], 45, gap=2.6)                          # 4 上密封座
    s.part(yc, [(594, 604, 32, 20)], 135, gap=1.8)                         # 7 防尘圈
    for sg in (-1, 1):
        for x in (536, 566):
            s.oring(x, yc + sg * 20)
            s.c.rect(x + 3, Y(yc + sg * 20) - 2, 3, 4, stroke=1, fill=1)
    s.rect(452, yc - 42, 460, yc - 32, 0.6)                                # 8 紧定螺钉
    s.c.setLineWidth(0.5)
    s.c.circle(552, Y(yc - 20), 20)                                        # 局部详图 D 的范围
    s.text(578, yc - 42, "D", 9, BOLD)
    for n, bx, tx, ty in ((1, 300, 300, yc - 30), (8, 456, 456, yc - 38), (2, 700, 700, yc - 37),
                          (4, 556, 552, yc - 26), (5, 520, 536, yc - 21), (6, 588, 570, yc - 21),
                          (7, 622, 599, yc - 26), (3, 820, 820, yc - 16)):
        s.balloon(bx, 270, n, tx, ty)
    s.callout(490, 452, ["15,000 ± 1,000 FT-LBS", "ANTI-SEIZE COMPOUND"], 460, yc + 34)
    s.callout(505, 215, ["35 ± 5 FT-LBS", "THREAD LOCKER, MEDIUM STRENGTH"], 454, yc - 40)
    s.text(150, 432, "API 4-1/2 IF BOX", 7.5, align="c")
    s.line(150, 424, 150, yc + 32, 0.4)
    s.vdim(1125, yc - 42, yc + 42, "Ø6.50 OD", ext_from=1065)
    s.text(625, 512, "SECTION C-C", 9, BOLD, "c")
    s.text(625, 523, "SCALE 1:4", 7.5, align="c")
    # 局部详图 D：密封槽放大
    cx, cy = 900, 180
    s.c.setLineWidth(0.6)
    s.c.circle(cx, Y(cy), 62)
    s.line(850, cy + 10, 950, cy + 10, 0.9)                                # 芯轴外圆
    s.line(850, cy - 30, 950, cy - 30, 0.9)                                # 壳体内孔
    s.rect(880, cy - 4, 916, cy + 10, 0.8)                                 # 槽
    s.c.circle(893, Y(cy + 3), 6.5, stroke=1, fill=0)                      # O 形圈
    s.c.rect(903, Y(cy + 10), 9, 13, stroke=1, fill=1)                     # 挡圈
    s.text(806, cy - 68, "HIGH PRESSURE", 7)
    s.leader(804, cy - 65, 878, cy + 2)
    s.text(962, cy - 68, "LOW PRESSURE", 7)
    s.leader(960, cy - 65, 918, cy + 2)
    s.text(904, cy + 34, "BACK-UP RING ON LOW PRESSURE SIDE", 7)
    s.line(907, cy + 26, 907, cy + 12, 0.4)
    s.text(cx, cy + 80, "DETAIL D", 9, BOLD, "c")
    s.text(cx, cy + 91, "SCALE 2:1", 7.5, align="c")
    s.bom([R("1", "TDT-650-0101", "TOP SUB, 6-1/2", note="API 4-1/2 IF BOX"),
           R("2", "TDT-650-0201", "HOUSING, SPRING, 6-1/2, INTEGRAL STABILIZER, 4 BLADE", merge=True),
           R("", "TDT-650-0202", "HOUSING, SPRING, 6-1/2, INTEGRAL STABILIZER, 3 BLADE", merge=True),
           R("", "TDT-650-0203", "HOUSING, SPRING, 6-1/2, SLICK", note="USES ITEM #16"),
           R("3", "TDT-650-0301", "MANDREL, SPLINED, 6-1/2"),
           R("4", "TDT-650-0401", "SEAL CARRIER, UPPER"),
           R("5", "TDT-00-0105", "O-RING, 2-348, HNBR 90", "4"),
           R("6", "TDT-00-0106", "BACK-UP RING, 2-348, PEEK", "4"),
           R("7", "TDT-650-0701", "WIPER RING", twice=True),
           R("8", "TDT-00-0108", "SET SCREW, 3/8-16 X 1/2, CUP POINT", "2")])


def main(out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    c = canvas.Canvas(out, pagesize=(W, H), invariant=1)   # 可复现：不写时间戳
    c.setTitle(DWG + ' 6-1/2" SHOCK SUB ASSEMBLY (FICTIONAL)')
    c.setAuthor("Tethys Downhole Tools (fictional)")
    c.setCreator("pdf-translate-zh showcase")
    s = Sheet(c)
    for f in (sheet1, sheet2, sheet3):
        f(s)
        c.showPage()
    c.save()
    print("源图纸已写入", out)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "build", DWG + "_Assembly.pdf"))
