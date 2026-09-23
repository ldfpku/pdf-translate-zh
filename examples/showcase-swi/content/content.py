# -*- coding: utf-8 -*-
"""内容层：SWI-650-SS《650 型钻井减震器装配作业指导书》中文版（虚构展示文档）。

R 级语义重排：前置页（法律声明/文档控制/法规符合性）按内容接排、不再一页一节；目录由引擎按标题自动生成
（点引线收敛、页码按译版页码、整行可点跳转），每个工序步骤另落 PDF 书签。插图全部走位图流水线
（figpipe：提取 → Real-ESRGAN 4 倍超分 → 图内英文回叠中文 → 件号气泡原位重绘），文件名 xNN = 源 PDF 的 xref。
"""
from reportlab.lib import colors
from reportlab.platypus import Flowable, Table, TableStyle

import render
from builder import A4
from zhlib import styles

S = styles(flow=True)
FW = A4.fw

MAST_TITLE = ""
FOOT = ("SWI-650-SS · 第 3 版 · 2026-03-12 · Tethys Downhole Tools", "", "虚构展示文档")
USED_FIGS = ("x23.png", "x25.jpg", "x27.jpg", "x28.jpg", "x29.jpg", "x31.jpg", "x33.jpg", "x34.jpg", "x36.jpg")


class WasteIcon(Flowable):
    """带叉垃圾桶（WEEE）符号：原版是矢量图形，按原样重画。"""
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


class Logo(Flowable):
    """封面徽标：三道波纹 + 字标（原版矢量，按原样重画；虚构品牌字标保留原文）。
    盒高留足：版心顶端的 Spacer 会被 ReportLab 丢弃，徽标要自带上方净空，否则顶到页眉色带。"""
    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = 180, 60

    def draw(self):
        c = self.canv
        teal = colors.HexColor("#138A8A")
        c.setStrokeColor(teal)
        c.setLineWidth(5)
        for k in range(3):
            y = 40 - k * 11
            p = c.beginPath()
            p.moveTo(0, y)
            p.curveTo(15, y + 10, 30, y - 10, 45, y)
            c.drawPath(p, stroke=1, fill=0)
        c.setFillColor(teal)
        c.setFont("Helvetica-Bold", 30)
        c.drawString(52, 16, "tethys")


def waste_row():
    """WEEE 符号 + 说明：图标与文字垂直居中并排。"""
    t = Table([[WasteIcon(), render.P("此标志表示该设备不得作为普通垃圾丢弃。设备及/或其零部件报废时，必须按照 "
                                      "Tethys 环境管理程序处置，并符合 Tethys QHSE 方针及适用的废弃物管理法律法规。",
                                      S["body"])]], colWidths=[56, FW - 56])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _grid(rows, w, align=None):
    return lambda: render.grid_table(rows, w, S, width=FW, align=align)


PARTS = [["件号", "零件号", "名称及规格", "数量"],
         ["01", "TDT-65001", "芯轴，6-1/2", "1"], ["02", "TDT-65002", "壳体，6-1/2", "1"],
         ["03", "TDT-65003", "碟形弹簧，外径 4.25", "6 ①"], ["04", "TDT-65004", "花键套", "1"],
         ["05", "TDT-65005", "防尘圈", "1"], ["06", "TDT-65006", "密封座", "1"],
         ["07", "TDT-65007", "O 形圈，2-348，HNBR 90", "2"], ["08", "TDT-65008", "挡圈，PEEK", "2"],
         ["09", "TDT-65009", "推力轴承", "1"], ["10", "TDT-65010", "锁紧螺母，4-1/2 UN", "1"],
         ["11", "TDT-65011", "紧定螺钉，3/8-16 × 1/2", "2"], ["12", "TDT-65012", "注脂嘴，1/8 NPT", "1"]]

TORQUE = [["代号", "连接部位", "扭矩（ft-lbf）", "工具"],
          ["TQ-A", "紧定螺钉（11）→ 锁紧螺母（10）", "35 ~ 40", "内六角批头，3/16"],
          ["TQ-B", "锁紧螺母（10）→ 芯轴（01）", "1,800 ~ 2,000", "650 型钩形扳手"]]

REVS = [["版本", "日期", "修订说明", "编制"],
        ["1", "2025-11-20", "初版", "A. Rivera"],
        ["2", "2026-01-15", "步骤 2.5 增加挡圈安装方向要求。", "A. Rivera"],
        ["3", "2026-03-12", "增补锁紧螺母与紧定螺钉的扭矩值（表 3-1）。", "A. Rivera"]]

PPE = ("fig", "x23.png", 150, None)


def ppe_required():
    return [("b", "所需个人防护装备（PPE）"), PPE]


def step(num, text, *extra):
    """工序步骤：书签（进 PDF 大纲、不进目录）+ 正文 + 本步的插图/说明，整体不跨页（图文不分离）。"""
    return [("keep", [("mark", "%s　%s" % (num, text), 1), ("step", "%s　%s" % (num, text))] + list(extra))]


CHAPTERS = [
    # ---- 封面
    [("raw", Logo()), ("sp", 26),
     ("title", "SWI-650-SS，650 型钻井减震器装配作业指导书（Assembly SWI）", 18),
     ("sp", 10),
     ("kv", [("版本：", "3"), ("文件标识：", "7c1e9a40-58d2-4f6b-9e0a-3b2d61c4f8e7"), ("发布日期：", "2026 年 3 月 12 日"),
             ("所有者：", "Tethys 装配工程部，Harbor Point 车间"), ("作者：", "A. Rivera"),
             ("数据密级：", "公开（虚构展示文档）")], 90),
     ("pb",),
     # ---- 前置页：按内容接排
     ("h1", "法律声明"),
     ("p", "版权所有 © 2026 Tethys Downhole Tools。保留所有权利。"),
     ("p", "本文件是为 pdf-translate-zh 项目制作的虚构展示文档。文中的公司、产品、零件号及人名均为虚构，"
           "如与真实产品或机构雷同，纯属巧合。"),
     ("b", "商标与服务标志"),
     ("p", "Tethys 及 Tethys 波纹徽标为虚构标志，仅用于演示。"),
     ("h1", "文档控制"),
     ("kv", [("所有者：", "Tethys 装配工程部，Harbor Point 车间"), ("作者：", "A. Rivera"),
             ("审核：", "M. Okafor"), ("批准：", "A. Rivera")], 70),
     ("tbl", _grid(REVS, [1, 1.6, 5, 1.6], ["C", "C", "L", "C"]), "修订记录"),
     ("h1", "法规符合性"),
     ("b", "废弃物管理"),
     ("b", "设备正确处置的重要信息"),
     ("sp", 6),
     ("raw", waste_row()),
     ("pb",),
     # ---- 目录（引擎自动生成）；其后各章由 chapter_break 另起一页
     ("toc", "目录", 0),
     ],
    # ---- 1 简介
    [("h1", "1　简介"),
     ("box", [PPE], "note", "个人防护装备（PPE）"),
     ("p", "本标准作业指导书（SWI）SWI-650-SS 规定了 650 型钻井减震器的装配程序。"),
     ("p", "遵守 Tethys 安全标准中的全部安全要求。重要安全要求如下："),
     ("bul", ["按 Tethys QHSE 标准 S-003《工具与设备 PPE 附录》的要求穿戴个人防护装备。",
              "在工作区内搬运零件与工装时，采用安全的起吊方法。",
              "确保工作区内只有必要的人员。",
              "确保作业中只有经批准并取得资质的人员操作机械设备。",
              "遵守电气设备的全部安全要求。"]),
     ("p", "任何设备、零部件或耗材的废弃，均须符合 Tethys QHSE 方针及适用的废弃物管理法律法规。"),
     ("tbl", _grid(PARTS, [1, 2, 5, 1], ["C", "C", "L", "C"]), "表 1-1  零件明细"),
     ("p", "注①：原版零件表数量为 6，步骤 2.2 为八片，两处不一致，本稿保留原值，见附录 A 乙。", "tnote"),
     ("fig", "x25.jpg", 400, "图 1-1  芯轴组件零件（件号气泡已按零件表核对后重绘，见附录 A 乙）"),
     ],
    # ---- 2 装配芯轴组件
    [("h1", "2　装配芯轴组件")] + ppe_required() + [
        ("box", "开始装配前，确认全部零件清洁。", "warning", ""),
    ]
    + step("2.1", "用软钳口台虎钳水平夹持芯轴（01）。",
           ("fig", "x27.jpg", 380, None), ("box", "确认钳口不会损伤芯轴的镀铬表面。", "note", ""))
    + step("2.2", "将八片新的碟形弹簧（03）装到芯轴（01）上。",
           ("fig", "x28.jpg", 380, None),
           ("box", "碟形弹簧须凸面朝上、串联叠装。方向装反的弹簧在承载时会失效。", "note", ""))
    + step("2.3", "将花键套（04）装到芯轴（01）上，花键须与芯轴上的键槽对齐。", ("fig", "x29.jpg", 380, None))
    + step("2.4", "将防尘圈（05）和密封座（06）装到芯轴（01）上。")
    + step("2.5", "将 O 形圈（07）和挡圈（08）装入密封座（06）的密封槽，挡圈必须位于低压侧。",
           ("fig", "x31.jpg", 380, None))
    + step("2.6", "将推力轴承（09）靠紧密封座（06）安装。"),
    # ---- 3 装入壳体
    [("h1", "3　将芯轴组件装入壳体")] + ppe_required()
    + step("3.1", "固定壳体（02），防止其向任何方向移动。检查壳体内部有无杂物，必要时清理。",
           ("box", "开始装配前，确认全部零件清洁。", "warning", ""))
    + step("3.2", "用吊带和行车将子总成装入壳体（02），尽量向前推到底。",
           ("fig", "x33.jpg", 380, None), ("box", "按当地最佳做法使用 V 形块、千斤顶支架或其他支承方式。", "note", ""))
    + step("3.3", "安装锁紧螺母（10），按 TQ-B 拧紧（见表 3-1）。", ("fig", "x34.jpg", 380, None))
    + step("3.4", "将两个紧定螺钉（11）装入锁紧螺母（10），按 TQ-A 拧紧。")
    + [("tbl", _grid(TORQUE, [1, 4.2, 2.2, 2.6], ["C", "L", "C", "L"]), "表 3-1  扭矩值")],
    # ---- 4 注脂
    [("h1", "4　注脂")] + ppe_required()
    + step("4.1", "拆下壳体（02）侧注脂孔和顶部排气孔的堵头。", ("fig", "x36.jpg", 380, None))
    + step("4.2", "从侧注脂孔泵入润滑脂，直到顶部排气孔流出无气泡的洁净润滑脂。",
           ("box", "注脂压力不得超过 50 psi。压力过高会把密封座（06）顶离安装位置。", "warning", ""))
    + step("4.3", "安装注脂嘴（12）和排气堵头。") + step("4.4", "在装配检查表上记录注脂量。"),
]
