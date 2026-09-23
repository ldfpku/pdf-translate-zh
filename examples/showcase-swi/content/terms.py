# -*- coding: utf-8 -*-
"""术语与附录数据。附录 A/B 由此自动生成，排在译文之后、各自另起一页。"""

ERRATA_INTRO = (
    "行业判定：油气钻井装备——井下钻具（钻井减震器）装配作业。判据：①产品域词汇成簇出现：mandrel、housing、"
    "disc spring、spline sleeve、seal carrier、back-up ring、thrust bearing、lock nut；②工序语体为标准作业指导书"
    "（SWI）：编号步骤 + 个人防护装备（PPE）栏 + 警示/说明图标行；③英制规格与扭矩单位（in、ft-lbf、psi、NPT、UN）。"
    "据此锁定钻具装配术语（mandrel=芯轴、housing=壳体、back-up ring=挡圈、seal carrier=密封座），语体取操作指令体。"
    "版面定级为 R（语义重排）：原版 11 页为步骤、表格与插图，版面坐标无语义；前置页按内容接排，目录由译版自动生成。"
    "本文件为虚构展示文档；原文中有意保留一处表号误引与一处数量不一致，用于演示勘误与存疑的处置。"
)

# 附录 B《中英术语对照表》：{类别: [(英文, 中文), ...]}
GLOSSARY = {
    "零件": [
        ("shock sub", "减震器"),
        ("mandrel", "芯轴"),
        ("housing", "壳体"),
        ("disc spring", "碟形弹簧"),
        ("spline sleeve", "花键套"),
        ("wiper ring", "防尘圈"),
        ("seal carrier", "密封座"),
        ("O-ring", "O 形圈"),
        ("back-up ring", "挡圈"),
        ("thrust bearing", "推力轴承"),
        ("lock nut", "锁紧螺母"),
        ("set screw", "紧定螺钉"),
        ("grease fitting", "注脂嘴"),
        ("vent plug", "排气堵头"),
        ("subassembly", "子总成"),
    ],
    "工装与设备": [
        ("soft-jaw vise", "软钳口台虎钳"),
        ("sling", "吊带"),
        ("overhead crane", "行车"),
        ("V-block", "V 形块"),
        ("jack stand", "千斤顶支架"),
        ("spanner wrench", "钩形扳手"),
        ("hex bit", "内六角批头"),
    ],
    "工艺与部位": [
        ("stack in series", "串联叠装"),
        ("convex face", "凸面"),
        ("low-pressure side", "低压侧"),
        ("spline key", "花键"),
        ("side fill port", "侧注脂孔"),
        ("top vent port", "顶部排气孔"),
        ("torque", "扭矩（拧紧力矩）"),
        ("exploded view", "爆炸图"),
        ("section A-A", "剖视图 A-A"),
        ("detail B", "局部详图 B"),
    ],
    "文件与安全": [
        ("standard work instruction (SWI)", "标准作业指导书"),
        ("personal protective equipment (PPE)", "个人防护装备"),
        ("QHSE", "质量、健康、安全与环境"),
        ("revision history", "修订记录"),
        ("data classification", "数据密级"),
    ],
}

# 附录 A《译校勘误说明》——行首「序号」列自动补
JIA = [
    ("步骤 3.3", "torque it to TQ-B (see Table 3-2)", "引用表号错误",
     "译为「按 TQ-B 拧紧（见表 3-1）」", "全文只有表 3-1《扭矩值》，TQ-B 即其中锁紧螺母一行；插图 3.3 的标注亦写 Table 3-1"),
]
YI = [
    ("表 1-1 零件明细 · 件号 03", "碟形弹簧数量 6", "步骤 2.2：Install eight new disc springs",
     "表中保留原值 6 并加注，步骤按原文译「八片」", "以哪一个为准须经装配工程部确认；插图 2.2 可数出 8 片"),
    ("全部插图", "件号气泡判读：原图有效分辨率 85~97 dpi，超分前 08/06、03/05 形近",
     "零件表 01~12、步骤正文、零件颜色编码", "逐个核对后在原环心位置统一重绘（26 个）",
     "若与 CAD 原图不符，以 CAD 为准"),
]
BING = [
    ("全部插图（9 幅）", "系统导出位图有效分辨率仅 85~132 dpi，放大即糊，气泡数字发虚",
     "Real-ESRGAN x4plus 超分 4 倍（2040 px ≈ 340 dpi 嵌入）；几何与色彩未作改动"),
    ("插图内英文标注（11 处）", "SECTION A-A、DETAIL B、Subassembly、Side Fill Port 等烧死在位图中，文本层没有",
     "按检测框铺底色后原位写中文，同图字号按原文行高统一；件号气泡保留编号、原位重绘"),
    ("前置页", "原版法律声明、文档控制、法规符合性各占一页，内容仅数行",
     "按内容接排，目录由译版标题自动生成，页码与跳转链接按译版"),
    ("工序步骤书签", "原版每个步骤均有 PDF 书签", "译版保留：每个步骤一条书签（二级），目录只收章节"),
]

WHITELIST_ADD = ("Tethys", "Harbor Point", "A. Rivera", "M. Okafor", "tethys", "TDT-SWI", "Assembly SWI")
# 内容对账允许消失的记号：日期改为中文格式（11/20/2025 → 2025-11-20）；原版页脚的发布路径串
TOKEN_IGNORE = ("11/20/2025", "1/15/2026", "3/12/2026", "12-Mar-2026", "2026", "12",
                "3-2")   # 3-2：原文误引「Table 3-2」，按勘误译为表 3-1（附录 A 甲）
