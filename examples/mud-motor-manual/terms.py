# -*- coding: utf-8 -*-
"""术语与附录数据。附录 A/B 由此自动生成。"""

ERRATA_INTRO = (
    "行业判定：油气钻井装备——井下动力钻具（螺杆钻具，PDM）。判据：①引用标准 API RP 7G"
    "（钻柱设计与操作极限）；②产品域词汇成簇出现：motor、rotor、stator、power section、"
    "bearing assembly、bit box、dump valve；③工况词：stall、weight on bit、standpipe pressure、"
    "make-up torque；④英制单位（in、ft、psi、gpm、ft-lbf）与 API 旋转台肩螺纹代号"
    "（4-1/2 REG、4-1/2 IF、6-5/8 REG、5-1/2 FH）。据此锁定钻井行业术语（stall=憋停、"
    "make up=上扣、bit box=钻头母扣、lobe=头数、play=游隙、dump valve=旁通阀），"
    "语体取操作指令体：工序用祈使句，shall、must、should 分别译为「应」「必须」「宜」。"
    "单位与螺纹代号照录原文、不作换算。版面定级为 R（语义重排）：原版 3 页均为散文、"
    "工序与普通表格，版面坐标无语义。本附录逐条记录译校中发现的原文问题与版式处理；"
    "「乙」中各项须经工程部门确认后方可据以施工。"
)

# 附录 B《中英术语对照表》：{类别: [(英文, 中文), ...]}
GLOSSARY = {
    "钻具结构": [
        ("positive displacement motor (PDM)", "螺杆钻具（容积式马达）"),
        ("power section", "动力段"),
        ("rotor", "转子"),
        ("stator", "定子"),
        ("elastomer", "橡胶（定子衬层）"),
        ("lobe", "头数"),
        ("stage", "级"),
        ("fit", "配合（转子与定子）"),
        ("transmission", "万向轴总成"),
        ("transmission housing", "万向轴壳体"),
        ("drive shaft", "驱动轴"),
        ("bearing assembly", "轴承总成"),
        ("bearing housing", "轴承壳体"),
        ("top sub", "上接头"),
        ("bit box", "钻头母扣"),
        ("dump valve", "旁通阀"),
        ("OD / ID", "外径 / 内径"),
    ],
    "连接与螺纹": [
        ("make up", "上扣"),
        ("make-up torque", "上扣扭矩"),
        ("box", "母扣"),
        ("REG", "正规扣"),
        ("IF", "内平扣"),
        ("FH", "贯眼扣"),
        ("torque gauge", "扭矩表"),
        ("elastomer bond", "橡胶粘接层"),
        ("over-torquing", "上扣扭矩过大"),
    ],
    "钻井作业": [
        ("kelly", "方钻杆"),
        ("top drive", "顶驱"),
        ("drill string", "钻柱"),
        ("drill stem", "钻柱"),
        ("drilling fluid", "钻井液"),
        ("flow rate", "排量"),
        ("surface test", "地面试验"),
        ("run in the hole", "下钻"),
        ("casing", "套管"),
        ("tag bottom", "探井底"),
        ("pick up", "上提"),
        ("establish circulation", "建立循环"),
        ("weight on bit", "钻压"),
        ("standpipe pressure", "立管压力"),
        ("off-bottom pressure", "离底压力"),
        ("differential pressure", "压差"),
        ("stall", "憋停"),
        ("on-bottom / off-bottom load", "钻进 / 离底载荷"),
        ("run", "趟钻"),
    ],
    "检查与维护": [
        ("axial play", "轴向游隙"),
        ("bearing wear", "轴承磨损"),
        ("chunking", "掉块（定子橡胶）"),
        ("sour service", "酸性环境（抗硫）"),
        ("service center", "维修中心"),
        ("service manual", "维修手册"),
    ],
}

# 附录 A《译校勘误说明》——行首「序号」列自动补
JIA = []    # 经逐句核对，未发现可确证须勘正的原文缺陷

YI = [      # (原文位置, 存疑内容, 冲突对象, 本稿处理, 须确认事项)
    ("第 3 章 警告框（原版第 1 页）",
     "WARNING: Do not exceed the maximum differential pressure of 1,200 psi.",
     "表 2-1「Max. differential pressure」为 1,000 psi",
     "两处原值照录；警告框内加译注指向本条",
     "最大压差以哪一值为准。确认前宜按较低值 1,000 psi 控制"),
    ("3.1 工序 1（原版第 1 页）",
     "Make up the motor to the kelly or top drive using the torque values in Table 4-1.",
     "表 4-1 仅列钻具内部三处连接（6-5/8 REG、5-1/2 FH），未含顶部连接 4-1/2 IF（表 2-1）",
     "照原文译出，未补数值",
     "钻具顶部 4-1/2 IF 连接的上扣扭矩取值"),
    ("第 4 章（原版第 3 页）",
     "Measure the stator ID and the rotor OD as described in ASTM A370 …",
     "ASTM A370 为钢制品力学性能试验方法标准，不涉及定子内径、转子外径的尺寸测量",
     "标准号照录，未改动",
     "引用标准是否有误，或应以维修手册 NDT-SM-675 为准"),
]

BING = [    # (涉及部位, 原始问题, 修复处理)
    ("全文版式",
     "原版为 Letter 幅面，按英文行数断行、两端对齐",
     "按 R 级语义重排为 A4，正文按中文版式流式排版；原版第 1→2 页跨页的工序 1~4 合并为一个连续有序列表"),
    ("3.2 列表",
     "原版三条列表为「小写起头、分号结尾」的句子残段，承接上句冒号",
     "译为三条完整中文分句，保留原有的列举关系"),
    ("图 3-1",
     "图内 7 条矢量英文标注（部件名、液流方向、最大外径）",
     "提取时抹除英文、按源版坐标同源回叠中文；数值 6.75 与单位 in 保留原样；图中无位图烧死文字"),
    ("警告框",
     "原文化学式写作「H2S」",
     "按化学式规范排为真下标 H<sub>2</sub>S"),
    ("页眉页脚",
     "原版页眉为品牌名 | 手册名，页脚为文件号 | 页码",
     "品牌名 NORTHSTAR DRILLING TOOLS 与文件号 NDT-OM-675 Rev B 保留原文；手册名译出；页码按译版重排"),
]

WHITELIST_ADD = ("NORTHSTAR DRILLING TOOLS", "NDT-OM-675 Rev B", "NDT-SM-675",
                 "ASTM A370", "API RP 7G", "rev/gal", "ft-lbf", "gpm", "psi")
TOKEN_IGNORE = ()    # 内容对账允许消失的记号：原版页眉页脚的页码、修订号等
