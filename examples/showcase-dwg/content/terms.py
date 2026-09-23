# -*- coding: utf-8 -*-
"""术语与附录数据。附录 A/B 追加在叠印图纸之后，各自另起一页（A4 竖排）。"""

ERRATA_INTRO = (
    "行业判定：油气钻井装备——井下钻具（钻井减震器）总装图。判据：①明细表零件成簇：mandrel、housing、disc spring、"
    "spline sleeve、seal carrier、back-up ring、thrust bearing、top/bottom sub；②API 旋转台肩螺纹代号（4-1/2 IF PIN/BOX）"
    "与英制扭矩（FT-LBS）；③CAD 工程图版式：图框分区、修订栏、标题栏「除另有规定外」注记、剖视图与件号气泡。"
    "版面定级为 P（保位叠印）：坐标即语义，只换字、不动线；剖面线、尺寸线、气泡与引线全部保持原始矢量。"
    "本文件为虚构展示图纸；原文中有意保留一处件号误引与一处数量不一致，用于演示勘误与存疑的处置。"
)

# 附录 B《中英术语对照表》
GLOSSARY = {
    "零件": [
        ("shock sub", "减震器"),
        ("top sub / bottom sub", "上接头 / 下接头"),
        ("housing, spring", "弹簧壳体"),
        ("integral stabilizer, 4 blade", "整体扶正器，4 棱"),
        ("slick (housing)", "光壳体（无扶正棱）"),
        ("mandrel, splined", "花键芯轴"),
        ("spline sleeve", "花键套"),
        ("lock nut, left hand", "锁紧螺母，左旋"),
        ("seal carrier", "密封座"),
        ("O-ring", "O 形圈"),
        ("back-up ring", "挡圈"),
        ("wiper ring", "防尘圈"),
        ("disc spring", "碟形弹簧"),
        ("spring guide", "弹簧导向座"),
        ("spacer, spring stack", "弹簧组隔环"),
        ("thrust bearing / bearing race", "推力轴承 / 轴承座圈"),
        ("wear sleeve", "耐磨套"),
        ("set screw, cup point", "凹端紧定螺钉"),
        ("grease fitting", "注脂嘴"),
        ("pipe plug, socket head", "内六角管堵"),
    ],
    "螺纹与装配": [
        ("API IF (internal flush)", "内平扣（代号 IF 保留）"),
        ("pin / box", "公扣 / 母扣"),
        ("tool joint connection", "钻具接头螺纹"),
        ("anti-seize compound", "防咬合剂"),
        ("thread locker, medium strength", "中强度螺纹锁固剂"),
        ("pipe sealant", "管螺纹密封剂"),
        ("seal grease", "密封脂"),
        ("stacked in series", "串联叠装"),
        ("preload gap", "预紧间隙"),
        ("select fit", "选配"),
        ("high / low pressure side", "高压侧 / 低压侧"),
    ],
    "图纸要素": [
        ("bill of materials (BOM)", "明细表"),
        ("revisions", "修订记录"),
        ("section A-A", "剖视图 A-A"),
        ("detail D", "局部详图 D"),
        ("overall length (OAL)", "全长"),
        ("unless otherwise specified", "除另有规定外"),
        ("break all sharp corners", "所有尖角均须倒钝"),
        ("TIR (total indicator reading)", "全跳动"),
        ("drawn / checked / eng. appr.", "制图 / 校对 / 工程批准"),
        ("assembly traveler", "装配流转卡"),
    ],
}

# 附录 A《译校勘误说明》
JIA = [
    ("第 3 张 · 明细表件号 2（光壳体行）备注", "USES ITEM #16", "引用件号错误",
     "译为「配用件 15」并在格内注明原文",
     "件 15 为 WEAR SLEEVE, SLICK HOUSING（光壳体用耐磨套，第 2 张剖视 B-B 以双点画线画在壳体外）；"
     "件 16 为弹簧组隔环，与壳体选型无关"),
]
YI = [
    ("第 2 张 · 明细表件号 9 备注", "10 PER STACK, 2 STACKS（每组 10 片 × 2 组 = 20 片）",
     "同行数量栏 16；剖视图 B-B 每组画 8 片（8 × 2 = 16）",
     "保留原值「每组 10 片，共 2 组」并加注存疑", "弹簧片数决定预紧量，须经工程部门确认后方可装配"),
]
BING = [
    ("装配路线", "图纸的主体是剖面线、尺寸线、件号气泡与引线，重排会失真",
     "保位叠印：redaction 只抹英文（线框不动），原位写中文；三张图纸的矢量图形全部保留"),
    ("标题栏「除另有规定外」注记格", "± / ° / 粗糙度符号是矢量，不在文本层；小数点列靠前导空格对齐；"
     "长句被物理换行切成两截", "整格抹掉按标准重排（dwgnote）：整句译出，± / ° 改为真文字，公差值逐图解析"),
    ("明细表", "ITEM / QTY 两列用「缺行线」表示纵向合并（件号 2 三种可选壳体共用一个件号与数量）；"
     "件号 7、12 的名称在 CAD 导出时重影（同位写了两遍）",
     "合并格按原版保留一个件号与数量；重影文字去重后只译一次"),
    ("总注、专有声明、标题", "长句被物理换行切开（悬挂缩进的编号条、7.2pt 行距压叠的小字、居中两行标题）",
     "续行拼回整句再译；标题栏商号字标与右侧地址行按字号断开，字标保留原样"),
    ("竖排尺寸", "Ø6.50 OD、Ø4.25 SPRING BORE 为旋转 90° 的文字", "旋转通道单独认领，中文按原方向竖排写回"),
    ("保留不译", "图纸上大量内容属图形语言或专名",
     "扭矩值与 FT-LBS、螺纹代号（4-1/2 IF、1/8 NPT、4-1/2 UN）、O 形圈规格（2-342）、零件号、图号、"
     "标准号 ASME Y14.5-2018、人名缩写、日期、分区编号保留原文"),
]

WHITELIST_ADD = ("TETHYS DOWNHOLE TOOLS", "tethys", "Harbor Point", "FT-LBS", "ECO", "ASME", "HNBR", "PEEK",
                 "NPT", "UN", "API", "IF", "psi", "AR", "MO")
TOKEN_IGNORE = ()
