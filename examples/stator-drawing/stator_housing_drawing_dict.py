# -*- coding: utf-8 -*-
"""stator_housing_drawing 叠印词表。键 = hybrid_overlay.units_of() 清理后的单元（见 pending.txt）。
值 = 中文；"" = 保留原文。尺寸、件号、螺纹代号、标准号原样写进译文。
行业：石油钻井井下工具（螺杆钻具 PDM 定子壳体），语体：工程图样技术要求体。"""
D = {
    # 明细栏
    "ITEM": "序号",
    "PART NO.": "零件号",
    "DESCRIPTION": "名称及规格",
    "QTY": "数量",
    "STATOR HOUSING, 6-3/4": "定子壳体，6-3/4",
    "ELASTOMER LINER, 7/8 LOBE": "橡胶衬套，7/8 头",
    "WEAR SLEEVE": "耐磨套",
    "O-RING, 2-352 NBR 90": "O 形圈，2-352 NBR 90",
    # 技术要求
    "NOTES:": "技术要求：",
    "UNLESS OTHERWISE SPECIFIED:": "除另有规定外：",
    "1. ALL DIMENSIONS ARE IN INCHES.": "1. 所有尺寸单位均为英寸。",
    "2. BREAK ALL SHARP EDGES 0.015 MAX.": "2. 所有锐边倒钝，最大 0.015。",
    "3. THREADS PER API SPEC 7-2.": "3. 螺纹按 API SPEC 7-2 加工。",
    "4. PHOSPHATE COAT ALL THREADS AFTER INSPECTION.": "4. 检验合格后，所有螺纹进行磷化处理。",
    "5. MAGNETIC PARTICLE INSPECT PER ASTM E709.": "5. 按 ASTM E709 进行磁粉检测。",
    # 图面标注
    "ELASTOMER LINING (NBR, 7/8 LOBE)": "橡胶衬层（NBR，7/8 头）",
    "SEE DETAIL A": "见局部详图 A",
    "Ø6.75 OD Ø5.10 ID": "Ø6.75 外径\nØ5.10 内径",
    "6-5/8 REG PIN": "6-5/8 REG 公扣",
    "6-5/8 REG BOX": "6-5/8 REG 母扣",
    # 标题栏
    "NORTHSTAR DRILLING TOOLS": "",          # 公司名保留原文
    "TITLE: STATOR HOUSING ASSY, 675 PDM": "图名：定子壳体总成，675 PDM",
    "DWG NO: 675-200-011": "图号：675-200-011",
    "REV: C": "版次：C",
    "SCALE: 1:4": "比例：1:4",
    "SHEET 1 OF 1": "共 1 张  第 1 张",
    "DRAWN: J. SMITH CHECKED: R. LEE": "制图：J. SMITH　校对：R. LEE",
}


def lookup(t):
    return D.get(t)
