# -*- coding: utf-8 -*-
"""TDT-650-0100 叠印词表。键 = hybrid_overlay.units_of() 清理后的单元（见 pending.txt）。

值 = 中文（前缀 \x02 = 整条居中、\x05 = 强制左对齐，见 references/overlay.md §4）；扭矩值、螺纹代号、零件号、标准号原样写进译文；"\\n" 显式分行。
"" = 保留原文不动（商号字标、人名缩写、纯扭矩值）—— 同时进 build.py 的 WHITELIST。
标题栏「除另有规定外」注记格不在这里：由 dwgnote 整格重排（build.py）。
"""
D = {
    # ---- 修订栏
    "REVISIONS": "修订记录",
    "REV": "版次",
    "DATE": "日期",
    "BY": "编制",
    "APPR.": "批准",
    "INITIAL RELEASE, ECO 1042": "首次发布，ECO 1042",
    "ADDED ALT. HOUSINGS, ECO 1107": "增加可选壳体，ECO 1107",
    "AR": "",
    "MO": "",
    # ---- 标题栏
    "HEAT TREAT:": "热处理：",
    "MATERIAL:": "材料：",
    "SEE BOM": "见明细表",
    "DRAWN": "制图",
    "CHECKED": "校对",
    "ENG APPR.": "工程批准",
    "PROPRIETARY NOTICE THIS FICTIONAL DRAWING WAS PREPARED FOR THE PDF-TRANSLATE-ZH PROJECT AS A "
    "DEMONSTRATION. IT DOES NOT DESCRIBE A REAL PRODUCT AND MUST NOT BE USED FOR MANUFACTURE.":
        "\x05专有声明\n本图为 pdf-translate-zh 项目制作的虚构演示图纸，不描述任何真实产品，不得用于制造。",
    "INTERPRET DIMENSIONS AND TOLERANCES PER ASME Y14.5-2018.": "尺寸与公差按 ASME Y14.5-2018 解释。",
    "tethys": "",
    "TETHYS DOWNHOLE TOOLS HARBOR POINT ASSEMBLY SHOP FICTIONAL DEMONSTRATION ONLY":
        "TETHYS DOWNHOLE TOOLS\nHarbor Point 装配车间\n仅供演示（虚构）",
    '6-1/2" SHOCK SUB ASSEMBLY, DUAL SPRING STACK': '\x026-1/2" 减震器总成\n双弹簧组',
    "PART NO.": "零件号",
    "DWG. NO.": "图号",
    "SCALE: 1:4": "比例：1:4",
    "WEIGHT: 640 LBS": "重量：640 磅",
    "SHEET 1 OF 3": "共3张 第1张",
    "SHEET 2 OF 3": "共3张 第2张",
    "SHEET 3 OF 3": "共3张 第3张",
    # ---- 明细表
    "ITEM": "件号",
    "DESCRIPTION": "名称及规格",       # 修订栏同名表头另译「说明」，见 build.py 的 lookup
    "QTY": "数量",
    "NOTES": "备注",
    "TOP SUB, 6-1/2": "上接头，6-1/2",
    "HOUSING, SPRING, 6-1/2, INTEGRAL STABILIZER, 4 BLADE": "弹簧壳体，6-1/2，整体扶正器，4 棱",
    "HOUSING, SPRING, 6-1/2, INTEGRAL STABILIZER, 3 BLADE": "弹簧壳体，6-1/2，整体扶正器，3 棱",
    "HOUSING, SPRING, 6-1/2, SLICK": "弹簧壳体，6-1/2，光壳体",
    "USES ITEM #16": "配用件 15（原文误作 #16，见附录 A 甲）",
    "MANDREL, SPLINED, 6-1/2": "花键芯轴，6-1/2",
    "SEAL CARRIER, UPPER": "上密封座",
    "SEAL CARRIER, LOWER": "下密封座",
    "O-RING, 2-348, HNBR 90": "O 形圈，2-348，HNBR 90",
    "O-RING, 2-342, HNBR 90": "O 形圈，2-342，HNBR 90",
    "BACK-UP RING, 2-348, PEEK": "挡圈，2-348，PEEK",
    "WIPER RING": "防尘圈",
    "SET SCREW, 3/8-16 X 1/2, CUP POINT": "凹端紧定螺钉，3/8-16 × 1/2",
    "DISC SPRING, 4.25 OD X 2.25 ID": "碟形弹簧，外径 4.25 × 内径 2.25",
    "10 PER STACK, 2 STACKS": "每组 10 片，共 2 组（存疑，见附录 A 乙）",
    "SPRING GUIDE, UPPER": "上弹簧导向座",
    "SPRING GUIDE, LOWER": "下弹簧导向座",
    "THRUST BEARING, 4-3/4": "推力轴承，4-3/4",
    "BEARING RACE, THRUST": "推力轴承座圈",
    "WEAR SLEEVE, SLICK HOUSING": "耐磨套（光壳体用）",
    "SPACER, SPRING STACK": "弹簧组隔环",
    "SELECT FIT AT ASSEMBLY": "装配时选配",
    "SLICK HOUSING ONLY": "仅用于光壳体",
    "SPLINE SLEEVE, 6-1/2": "花键套，6-1/2",
    "LOCK NUT, 4-1/2 UN, LEFT HAND": "锁紧螺母，4-1/2 UN，左旋",
    "BOTTOM SUB, 6-1/2": "下接头，6-1/2",
    "GREASE FITTING, 1/8 NPT": "注脂嘴，1/8 NPT",
    "PIPE PLUG, 1/8 NPT, SOCKET HEAD": "内六角管堵，1/8 NPT",
    "API 4-1/2 IF PIN": "API 4-1/2 IF 公扣",
    "API 4-1/2 IF BOX": "API 4-1/2 IF 母扣",
    # ---- 总注
    "NOTES:": "注：",
    "1. CLEAN ALL THREADS AND SEAL BORES BEFORE ASSEMBLY.": "1. 装配前清洁全部螺纹与密封孔。",
    "2. APPLY ANTI-SEIZE COMPOUND TO ALL TOOL JOINT CONNECTIONS UNLESS OTHERWISE NOTED.":
        "2. 除另有注明外，所有钻具接头螺纹均涂防咬合剂。",
    "3. PRESSURE TEST SEAL SECTION TO 1,500 PSI FOR 10 MINUTES WITH NO VISIBLE LEAKAGE. "
    "RECORD THE RESULT ON THE ASSEMBLY TRAVELER.":
        "3. 密封段试压 1,500 psi，保压 10 分钟，不得有可见泄漏；结果记入装配流转卡。",
    '4. STAMP ASSEMBLY SERIAL NUMBER ON ITEM 20 WITHIN 2.0" OF THE SHOULDER.':
        '4. 在件 20 上距台肩 2.0" 以内打总成序列号钢印。',
    # ---- 视图、尺寸、引线标注
    "ASSEMBLY OVERVIEW": "总装概览",
    "SCALE 1:12": "比例 1:12",
    "SCALE 1:4": "比例 1:4",
    "SECTION A-A": "剖视图 A-A",
    "SECTION B-B": "剖视图 B-B",
    "SECTION C-C": "剖视图 C-C",
    "DETAIL D SCALE 2:1": "\x02局部详图 D\n比例 2:1",
    "OAL": "全长",
    "BOX TO SPRING STACK": "母扣端至弹簧组",
    "BOX END (UPHOLE)": "母扣端（上端）",
    "PIN END (DOWNHOLE)": "公扣端（下端）",
    "Ø6.50 OD": "外径 Ø6.50",
    "Ø4.25 SPRING BORE": "弹簧腔 Ø4.25",
    "2,000 ± 100 FT-LBS": "",
    "15,000 ± 1,000 FT-LBS ANTI-SEIZE COMPOUND": "15,000 ± 1,000 FT-LBS\n防咬合剂",
    "LEFT HAND": "左旋",
    "THREAD LOCKER, MEDIUM STRENGTH": "中强度螺纹锁固剂",
    "ANTI-SEIZE COMPOUND": "防咬合剂",
    "18,000 ± 1,000 FT-LBS ANTI-SEIZE COMPOUND": "18,000 ± 1,000 FT-LBS\n防咬合剂",
    "25 ± 5 FT-LBS PIPE SEALANT": "25 ± 5 FT-LBS\n管螺纹密封剂",
    "35 ± 5 FT-LBS THREAD LOCKER, MEDIUM STRENGTH": "35 ± 5 FT-LBS\n中强度螺纹锁固剂",
    "DISC SPRINGS STACKED IN SERIES, CONVEX FACES OPPOSED": "碟形弹簧串联叠装，\n相邻两片凸面相对",
    "SHIM ITEM 16 TO OBTAIN 0.020 - 0.040 STACK PRELOAD GAP": "以件 16 调整垫厚，使弹簧组\n预紧间隙为 0.020 - 0.040",
    "LUBRICATE O-RINGS WITH SEAL GREASE BEFORE INSTALLING": "O 形圈装入前\n涂密封脂",
    "HIGH PRESSURE": "高压侧",
    "LOW PRESSURE": "低压侧",
    "BACK-UP RING ON LOW PRESSURE SIDE": "挡圈装在低压侧",
}


def lookup(t):
    return D.get(t)
