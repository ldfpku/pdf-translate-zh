# -*- coding: utf-8 -*-
"""术语与附录数据。附录 A/B 由此自动生成，排在叠印正文之后、各自另起一页。"""

ERRATA_INTRO = (
    "行业判定：油气钻井装备——井下动力钻具（螺杆钻具定子壳体）。判据：①引用标准 API SPEC 7-2"
    "（旋转台肩螺纹）与 ASTM E709（磁粉检测）；②产品域词汇：stator housing、elastomer liner、"
    "lobe、REG pin/box；③英制尺寸与螺纹代号（6-3/4、6-5/8 REG）。版面定级为 P（保位叠印）："
    "工程图样的坐标即语义，译文原位叠印，尺寸、公差、件号、图号与螺纹代号照录原文。"
)

# 附录 B《中英术语对照表》：{类别: [(英文, 中文), ...]}
GLOSSARY = {
    "零件与结构": [
        ("stator housing", "定子壳体"),
        ("elastomer liner", "橡胶衬套"),
        ("elastomer lining", "橡胶衬层"),
        ("wear sleeve", "耐磨套"),
        ("O-ring", "O 形圈"),
        ("lobe", "头数"),
        ("pin / box", "公扣 / 母扣"),
    ],
    "图样与标题栏": [
        ("item", "序号"),
        ("part no.", "零件号"),
        ("description", "名称及规格"),
        ("qty", "数量"),
        ("notes", "技术要求"),
        ("unless otherwise specified", "除另有规定外"),
        ("detail", "局部详图"),
        ("drawing no.", "图号"),
        ("revision (rev)", "版次"),
        ("scale", "比例"),
        ("sheet", "张"),
        ("drawn / checked", "制图 / 校对"),
    ],
    "工艺与检验": [
        ("break sharp edges", "锐边倒钝"),
        ("phosphate coat", "磷化处理"),
        ("magnetic particle inspection", "磁粉检测"),
    ],
}

# 附录 A《译校勘误说明》——行首「序号」列自动补
JIA = []    # 甲 原文缺陷与勘正：(原文位置, 英文原文/问题, 问题类型, 勘正与译文, 依据)
YI = []     # 乙 存疑保留：(原文位置, 存疑内容, 冲突对象, 本稿处理, 须确认事项)
BING = [    # 丙 版式与插图修复：(涉及部位, 原始问题, 修复处理)
    ("标题栏", "公司名 NORTHSTAR DRILLING TOOLS", "商号保留原文，未译"),
    ("图面标注", "「Ø6.75 OD Ø5.10 ID」原版为单行", "译文按两行叠印，避免压住尺寸线"),
]
