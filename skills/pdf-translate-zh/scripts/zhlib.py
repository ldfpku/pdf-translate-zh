# -*- coding: utf-8 -*-
"""排版基础库：中文字体注册、全角标点规范化 zh()、样式表、品牌色。

样式覆盖 27 份文档共用所需（表格小字号档、警示框、填写栏、双栏术语表等）。zh() 的受保护正则与
判定逻辑保持与 skill 原版一致，不得随意放宽 —— 单元测试在 checks.py。

设计要点
  · zh() 程序化保证全角标点，数字千分位(1,500)、小数、型号/标准号不受影响；
  · wordWrap="CJK" 消除中英混排大空隙；
  · 英寸符 ″ / 度符 ° 等工程符号不参与全角化。
"""
import re
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------- 字体
# 路径不再写死：由 fontkit 按「环境变量 → 技能 fonts/ → 系统字体 → 内置兜底」
# 解析（Windows 上仍优先微软雅黑，与历史交付稿度量一致）。
# 需要固定某个字体时，设环境变量或把文件放进技能目录的 fonts/，不要改这里。
FONT_ROLES = {"ZH": "zh", "ZH-B": "zh-bold", "HEI": "hei", "SONG": "song"}
FONTS = {}          # 注册后回填：{名称: 实际字体文件}

_REGISTERED = False


def register_fonts():
    """幂等注册。多文档连续构建时会被反复调用。"""
    global _REGISTERED
    if _REGISTERED:
        return
    import fontkit
    for name, role in FONT_ROLES.items():
        try:
            path = fontkit.find(role, reportlab=True)
            pdfmetrics.registerFont(TTFont(name, path))
            FONTS[name] = path
        except Exception as e:
            print(f"[font] {name} 注册失败: {e}")
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("ZH", normal="ZH", bold="ZH-B", italic="ZH", boldItalic="ZH-B")
    _patch_kinsoku()
    # 第二、三处：ReportLab 只挂**一个**禁则字符（`），` 会把逗号丢到行首），
    # 且断点落在西文词内时只回溯到行长一半（「RotaMas / ter」）。
    # 这两处缺陷在**算法**里，不在字符表里，故另行打补丁（两个入口都要补）。
    try:
        import kinsoku2  # noqa: F401
    except Exception as e:
        print("[kinsoku2] 未装载: %s" % e)
    _REGISTERED = True


# 行首/行尾禁则（避头尾）。ReportLab 自带的表只收了 。）」 等，
# **没有收 ，；：！？** —— 而这几个正是 zh() 产出最多的全角标点，
# 于是 CJK 折行时会出现「，应将钻头提离井底」这样以逗号开头的行。
# 补齐后由 checks.check_line_start() 作机器判据复验。
_NO_START = "，、。．；：！？）〕］｝〉》」』】〗〞…‥ー～·’”%℃"
_NO_END = "（〔［｛〈《「『【〖‘“"


def _patch_kinsoku():
    """把避头尾表补到**所有会被用到的绑定**上。

    ⚠ 只改 `textsplit.ALL_CANNOT_START` 是**无效的**（避坑 92）：
    `platypus.paragraph` 在模块加载时就
        `from reportlab.lib.textsplit import wordSplit, ALL_CANNOT_START`
    取走了一份**字符串副本**，而 CJK 折行走的正是 `paragraph.cjkFragSplit`，
    它查的是自己那份副本。补丁看着打了、实际没生效 —— 实测附录里照样排出
    以「，」开头的行，且 `checks.check_line_start()` 能报出来、折行时却拦不住。
    ⇒ 两个绑定都要改。`paragraph` 只 import 了 START，故只需同步这一个。
    """
    try:
        from reportlab.lib import textsplit as ts
    except Exception:
        return
    for name, extra in (("ALL_CANNOT_START", _NO_START),
                        ("ALL_CANNOT_END", _NO_END)):
        cur = getattr(ts, name, "")
        add = "".join(ch for ch in extra if ch not in cur)
        if add:
            setattr(ts, name, cur + add)
    try:
        from reportlab.platypus import paragraph as _pp
        _pp.ALL_CANNOT_START = ts.ALL_CANNOT_START
    except Exception:
        pass


def has_glyph(ch, font="ZH"):
    """已注册的 ReportLab 字体里有没有这个字形（字体随机器而变，符号不能想当然）。"""
    register_fonts()
    try:
        return ord(ch) in pdfmetrics.getFont(font).face.charToGlyph
    except Exception:
        return True


def pick_glyph(options, font="ZH"):
    """从候选符号里挑第一个本机字体有的，例如 pick_glyph("•●·")。"""
    for ch in options:
        if has_glyph(ch, font):
            return ch
    return options[-1]


# ---------------------------------------------------------------- 品牌色
# 缺省品牌色（中性蓝灰）。换品牌在 build.py 里调 set_brand()，不要改本文件。
BRAND_PRIMARY = colors.HexColor("#0B5FA5")   # 徽标主色：强调、线条
BRAND_DARK = colors.HexColor("#123A5C")      # 标题字色
BRAND_RULE = colors.HexColor("#9AA7B2")      # 分隔线、页脚线


def set_brand(primary=None, dark=None, rule=None):
    """按文档换品牌色（在 build.py 里调用，不要改本文件）。参数为 '#RRGGBB'。"""
    global BRAND_PRIMARY, BRAND_DARK, BRAND_RULE
    if primary:
        BRAND_PRIMARY = colors.HexColor(primary)
    if dark:
        BRAND_DARK = colors.HexColor(dark)
    if rule:
        BRAND_RULE = colors.HexColor(rule)


HILITE = colors.HexColor("#FFF200")        # 原版修订高亮黄
TBL_HDR = colors.HexColor("#DCE3EA")
TBL_GRID = colors.HexColor("#4A5A68")
WARN_BG = colors.HexColor("#FFF4D6")
WARN_ED = colors.HexColor("#C69200")
DANGER_BG = colors.HexColor("#FDE7E7")
DANGER_ED = colors.HexColor("#B23030")
NOTE_BG = colors.HexColor("#EAF2FA")
NOTE_ED = colors.HexColor("#5C8DBF")

# ---------------------------------------------------------------- 全角规范化
CJK = "\u4e00-\u9fff"
FW = "\uff00-\uffef\u3000-\u303f"

_PROTECT = [
    # 尾字符必须是 [\w/]：原版 \S+ 会把紧随其后的逗号一并吞进保护区，
    # 于是「参见 www.example.com, 获取详情」的逗号永远转不成全角。
    r"https?://\S*[\w/]",
    r"www\.\S*[\w/]",
    r"<[^>]+>",                            # 保护 ReportLab 内联标签
    r"\d+(?:,\d{3})+(?:\.\d+)?",           # 1,500 / 1,642,963
    r"\d{1,2}:\d{2}(?::\d{2})?",           # 时刻 9:52 —— 原版遗漏，冒号会被全角化
    r"\d+\.\d+",                           # 3.75
    r"[A-Za-z]{1,6}\.\s?\d[\w.\-]*",       # Fig. 6-4 / Sec. 6.10
    r"[A-Za-z]{1,5}\d[\w.\-/]*",           # XS21.39947P / T-20 / NC31
    r"\d+\s*[-\u2013]\s*\d+",              # 30-35
    r"\d+/\d+",                            # 1/2
]
_PROT_RE = re.compile("|".join(f"(?:{p})" for p in _PROTECT))

_PUNC = {",": "\uff0c", ";": "\uff1b", ":": "\uff1a",
         "?": "\uff1f", "!": "\uff01", "(": "\uff08", ")": "\uff09"}


def zh(text, parens=True):
    """英式半角标点 → 中文全角。数字千分位/小数/型号/缩写点均受保护。

    与 skill 原版的一处刻意偏离：**整串不含中文时原样返回**。
    原版对任何串都无条件全角化 `,;:()` 等，于是术语对照表的英文列、
    保留原样的英文零件描述、"Rev A, Sheet 2" 之类都会被打成全角，
    交付稿里表现为英文里夹全角逗号。判据取「有无中文」最稳，
    且使 zh() 天然幂等。
    """
    if not text:
        return text
    # 源文本里的不换行空格/非断连字符/软连字符一律归一：它们让成品文本层里的
    # 图号、件号不可检索（checks.check_codepoints 会报），渲染上又毫无差别。
    text = text.replace("\u00a0", " ").replace("\u2011", "-").replace("\u00ad", "")
    if not re.search("[" + CJK + "]", text):
        return text
    holes = []

    # 占位符用**成对的 Unicode 非字符** U+FDD0/U+FDD1 包序号，一次性按正则回填。
    # 旧版用 \x00N\x00 前后同一个分隔符再逐个 str.replace：相邻两个占位符的
    # 「前一个的尾 \x00 + 普通数字 + 后一个的首 \x00」会被误认成另一个占位符 ——
    # 实测 `H<sub>2</sub>S` 与 `1,200` 同段时印出「H\x0031,2004\x00S」。
    def _stash(m):
        holes.append(m.group(0))
        return "\ufdd0%d\ufdd1" % (len(holes) - 1)

    s = _PROT_RE.sub(_stash, text)

    out = []
    for ch in s:
        if ch in _PUNC and not (ch in "()" and not parens):
            out.append(_PUNC[ch])
        else:
            out.append(ch)
    s = "".join(out)

    # 句点 → 句号：紧跟中文字符/全角标点之后；或整串结尾且本串含中文
    s = re.sub(r"(?<=[" + CJK + FW + r"])\.", "\u3002", s)
    if re.search("[" + CJK + "]", s):
        s = re.sub(r"\.(?=\s*$)", "\u3002", s)

    s = re.sub(r"\uff0c{2,}", "\uff0c", s)
    s = re.sub(r"\u3002{2,}", "\u3002", s)
    # 全角标点两侧不留空格
    s = re.sub(r"([\uff0c\u3002\uff1b\uff1a\uff1f\uff01\uff08])[ \t]+", r"\1", s)
    s = re.sub(r"[ \t]+([\uff0c\u3002\uff1b\uff1a\uff1f\uff01\uff09])", r"\1", s)
    s = re.sub(r"[ \t]+\uff08", "\uff08", s)
    s = re.sub(r"\uff09[ \t]+(?=[" + CJK + "])", "\uff09", s)

    return re.sub("\ufdd0(\\d+)\ufdd1", lambda m: holes[int(m.group(1))], s)


# ---------------------------------------------------------------- 填写栏
# ── 不可断记号（原子记号）────────────────────────────────────────
#
# `wordWrap="CJK"` 是中英混排必须开的（不开，中文长串被当成一个词，
# 首行只排三分之一）。代价是 ReportLab 认为**任意两个字符之间**都可断 ——
# 于是 `2020-08-17` 会被劈成 `2020-08-1` / `7`，`0.005"~0.009"` 会从引号
# 中间断开。这类记号是**工程标识**，断开即改变含义，必须整体不落地就不落地。
#
# 判据不能只列日期：零件号、型号、标准号、尺寸、数值+单位是同一类。
# **次序即优先级**：正则的择一是最左最先匹配，短模式排前面会把长记号
# 咬掉一截 —— 千分位那条排在「数值+单位」之前，`10,000 psi` 就只认到
# `10,000`，剩下的 ` psi` 仍可断行。故一律**长模式在前**。
ATOM_RE = re.compile(
    # 括号里的单位组整体成原子：表头「近似重量（lb）」在只有 15pt 宽的列里
    # 被劈成「（l / b）」（实测 规范 H 第 9 页）。括号+单位读者当一个记号，
    # 劈开就成了两个 —— 而这一列本来没有原子，也就没有列宽下限。
    r"[（(][A-Za-z0-9/·.%°µ]{1,10}[）)]|"
    # 油田件号与分数尺寸族（本项目实测补入）：
    #  · 纯数字件号 80020610 原表**一条都不匹配** —— 该列因此没有列宽下限，
    #    件号被 CJK 折行从中间劈开（实测「DPS00055-00 / 3」，避坑 60）；
    #  · `2-3/8IF`、`5-1/2` 这类分数尺寸同理，旧表只咬到 `2-3`。
    r"\d+-\d+/\d+\s?[A-Z]{0,4}"                  # 2-3/8IF / 5-1/2
    r"|\d{5,}"                                   # 80020610（纯数字件号）
    r"|\d{4}-\d{1,2}-\d{1,2}"                    # 2020-08-17
    r"|\d{1,2}/\d{1,2}/\d{2,4}"                  # 08/17/2020
    r"|(?:[A-Z0-9]+[-.]){2,}[A-Z0-9]+"           # 200-675-1500 / 7.1.1（多段）
    r"|\d+(?:\.\d+)?[\"″'′]?\s*[~～–—-]\s*"
    r"\d+(?:\.\d+)?[\"″'′]?(?![-.]\d)"           # 0.005"~0.009" / 30-35
    r"|\d+(?:\.\d+)?[\"″'′]"                     # 4.75"
    r"|\d+(?:,\d{3})*(?:\.\d+)?\s?"
    r"(?:psi|ksi|kgf|lbf|klbs|rpm|mm|cm|µm|um|in|ft|°F|°C|HV|N·m|Nm|"
    r"gal|ppg|kg|lb)\b"                          # 10,000 psi / 1100 HV
    r"|[A-Z]{2,}\s?[A-Z]?\d{2,}(?:[.\-/]\d+)*"   # ASTM E384 / SAE J442 / AMS 2432
    r"|[A-Z0-9]+[-.][A-Z0-9]+"                   # 手册 A（单段）
    r"|\d+(?:,\d{3})+(?:\.\d+)?"                 # 10,000（无单位）
    # 品牌名/长英文词：中英混排格里 `RotaMaster` 被 CJK 折行削成
    # 「RotaMast / er」很难看，且读者会以为是两个词。给它列宽下限。
    r"|[A-Z][A-Za-z]{5,}"
    , re.I)


def atoms(text):
    """串里的全部原子记号。"""
    return [m.group(0) for m in ATOM_RE.finditer(str(text or ""))]


def atom_width(text, font="ZH", size=10.0):
    """串里**最宽的一个原子记号**的实测宽度（列宽下限的来源）。

    量的是记号本身，不是整段 —— 整段该折还得折，只有记号不许断。
    """
    w = 0.0
    for a in atoms(text):
        w = max(w, pdfmetrics.stringWidth(a, font, size))
    return w


# ── 上下标 ───────────────────────────────────────────────────────
#
# 两条实测事实（reportlab 5.0，`Paragraph(...).frags` 直接量出来的）：
#   · `<sub>` 默认 rise = **−0.5 × 母字号**、size = 0.8 × 母字号；
#     `<super>` 默认 rise = **+0.5 × 母字号**、size 同上；
#   · 标签上的 `rise=` 是**增量**（叠加在上面那个默认值上），单位是 **pt**，
#     且默认值按**母字号**算 —— 同时给 `size=` 不影响这一点。
#
# 两处毛病由此而来：
#   ① **下沉太深**。−0.5 em 是 ReportLab 的老默认，排版惯例约 −0.2 em。
#   ② **行距不跟着变**。上下标只改字号与基线偏移，`leading` 纹丝不动。
#      实测 tbl 样式 7.4pt/9.6pt：下标探到基线下 0.5+0.8×0.21 = 0.668 em
#      = 4.94pt，而该行到次行字顶只剩 3.1pt —— **压进去 1.8pt**，
#      于是 `1100 HV(0.3 kgf)` 的下标贴死在下一行字头上。
#
# 故：内容层只写朴素的 `<sub>`／`<super>`（与字号无关），
# 由 `fix_scripts()` 在知道实际字号时改写成浅下沉，再由 `lead_bump()`
# 把剩下那点亏空补进 leading。两件事缺一不可 —— 只压浅仍会蹭到，
# 只加行距则行高白白涨一截。
SUB_RISE, SUP_RISE = -0.20, 0.32      # 目标基线偏移（相对母字号）
SCRIPT_SIZE = 0.72                     # 目标上下标字号（相对母字号）
_RL_DEFAULT = 0.5                      # ReportLab 的默认偏移（±0.5 em）
_DESC, _ASC = 0.21, 0.88               # 雅黑下伸部／字高，占字号的比例

_HAS_SUB = re.compile(r"<sub(?![a-z])", re.I)
_HAS_SUP = re.compile(r"<super(?![a-z])", re.I)


def sub(t):
    """下标。**标点与单位不要包进来** —— `HV<sub>0.3 kgf</sub>。` 才对，
    写成 `HV<sub>0.3 kgf。</sub>` 会把句号一并缩小压低，读起来像下标的
    一部分（实测附图：`1100 HV(0.3 kgf。)`）。"""
    return f"<sub>{t}</sub>"


def sup(t):
    return f"<super>{t}</super>"


def fix_scripts(text, size):
    """把朴素 `<sub>/<super>` 改写成浅下沉、并显式定字号。

    `rise` 是增量：要达到目标 R，增量 = R − 默认值。
    """
    s = str(text or "")
    if not (_HAS_SUB.search(s) or _HAS_SUP.search(s)):
        return s
    zs = SCRIPT_SIZE * size
    ds = (SUB_RISE + _RL_DEFAULT) * size          # 下标增量（正，抬起来）
    us = (SUP_RISE - _RL_DEFAULT) * size          # 上标增量（负，压下来）
    s = _HAS_SUB.sub(f'<sub rise="{ds:.2f}" size="{zs:.2f}"', s)
    s = _HAS_SUP.sub(f'<super rise="{us:.2f}" size="{zs:.2f}"', s)
    return s


def lead_bump(text, size):
    """含上下标时行距需额外让出的量（pt）；不含则为 0。

    下标探到基线下 |R| + 上下标字号×下伸部，常规行本就留了 1×下伸部，
    差额即须补的量；上标同理，比的是字高。
    """
    s = str(text or "")
    extra = 0.0
    if _HAS_SUB.search(s):
        extra = max(extra, (abs(SUB_RISE) + SCRIPT_SIZE * _DESC - _DESC) * size)
    if _HAS_SUP.search(s):
        extra = max(extra, (SUP_RISE + SCRIPT_SIZE * _ASC - _ASC) * size)
    return max(0.0, extra)


def fill_rule(n=8):
    """扫描件表单的填写栏。

    坑（SKILL ⑩）：全角 ＿ 之间会断开，半角 _ 在部分中文字体里也不连。
    用带下划线的全角空格渲染为连续实线。
    """
    return "<u>" + "\u3000" * n + "</u>"


CHECKBOX = "\u25a1"        # □ —— 不要用（  ），全角括号太宽必然撞线


def styles(flow=False):
    """全文样式表。原版正文 12pt → 中文 10.2pt，符合 CJK 阅读密度。

    自行注册字体：ParagraphStyle 一旦被 Paragraph 使用，reportlab 会用
    ps2tt() 反查字族以支持 <b>/<i>，未注册字族即抛
    「Can't map determine family/bold/italic for zh」。放在这里保证漏不掉。
    """
    register_fonts()
    S = {}
    S["section"] = ParagraphStyle("section", fontName="ZH-B", fontSize=19, leading=25,
                                  textColor=BRAND_DARK, spaceAfter=2, alignment=TA_LEFT)
    S["h1"] = ParagraphStyle("h1", fontName="ZH-B", fontSize=14.5, leading=20,
                             textColor=BRAND_DARK, spaceBefore=2, spaceAfter=8)
    S["h2"] = ParagraphStyle("h2", fontName="ZH-B", fontSize=11.5, leading=17,
                             textColor=BRAND_DARK, spaceBefore=8, spaceAfter=4)
    S["h3"] = ParagraphStyle("h3", fontName="ZH-B", fontSize=10.8, leading=16,
                             textColor=colors.HexColor("#1E3A52"), spaceBefore=6,
                             spaceAfter=3)
    S["body"] = ParagraphStyle("body", fontName="ZH", fontSize=10.2, leading=15.6,
                               alignment=TA_JUSTIFY, wordWrap="CJK", spaceAfter=5)
    S["bodyb"] = ParagraphStyle("bodyb", parent=S["body"], fontName="ZH-B")
    S["step"] = ParagraphStyle("step", parent=S["body"], leftIndent=17,
                               firstLineIndent=-17, spaceAfter=4)
    S["step2"] = ParagraphStyle("step2", parent=S["body"], leftIndent=34,
                                firstLineIndent=-17, spaceAfter=4)
    S["bullet"] = ParagraphStyle("bullet", parent=S["body"], leftIndent=15,
                                 firstLineIndent=-11, spaceAfter=3)
    S["bullet2"] = ParagraphStyle("bullet2", parent=S["body"], leftIndent=30,
                                  firstLineIndent=-11, spaceAfter=3)
    S["cap"] = ParagraphStyle("cap", fontName="ZH-B", fontSize=9.2, leading=12.6,
                              alignment=TA_CENTER, textColor=BRAND_DARK, spaceBefore=3,
                              spaceAfter=6, wordWrap="CJK")
    S["tcap"] = ParagraphStyle("tcap", fontName="ZH-B", fontSize=9.2, leading=12.6,
                               alignment=TA_LEFT, textColor=BRAND_DARK, spaceAfter=3,
                               wordWrap="CJK")
    S["tbl"] = ParagraphStyle("tbl", fontName="ZH", fontSize=7.4, leading=9.6,
                              alignment=TA_CENTER, wordWrap="CJK")
    S["tblL"] = ParagraphStyle("tblL", parent=S["tbl"], alignment=TA_LEFT)
    S["tblR"] = ParagraphStyle("tblR", parent=S["tbl"], alignment=TA_RIGHT)
    S["tblH"] = ParagraphStyle("tblH", parent=S["tbl"], fontName="ZH-B")
    S["tblHL"] = ParagraphStyle("tblHL", parent=S["tblH"], alignment=TA_LEFT)
    # 稍大一档的表格样式：短文档的表格列少、留白多，7.4pt 显小
    S["tbl9"] = ParagraphStyle("tbl9", parent=S["tbl"], fontSize=9.0, leading=12.4)
    S["tbl9L"] = ParagraphStyle("tbl9L", parent=S["tbl9"], alignment=TA_LEFT)
    S["tbl9H"] = ParagraphStyle("tbl9H", parent=S["tbl9"], fontName="ZH-B")
    S["tbl9HL"] = ParagraphStyle("tbl9HL", parent=S["tbl9H"], alignment=TA_LEFT)
    S["tnote"] = ParagraphStyle("tnote", fontName="ZH", fontSize=8.4, leading=12,
                                wordWrap="CJK", alignment=TA_JUSTIFY, spaceAfter=2)
    S["toc1"] = ParagraphStyle("toc1", fontName="ZH-B", fontSize=10, leading=17,
                               textColor=BRAND_DARK)
    S["toc2"] = ParagraphStyle("toc2", fontName="ZH", fontSize=9.6, leading=15.5)
    S["cover_t"] = ParagraphStyle("cover_t", fontName="ZH-B", fontSize=31, leading=41,
                                  textColor=BRAND_DARK, alignment=TA_LEFT)
    S["cover_s"] = ParagraphStyle("cover_s", fontName="ZH", fontSize=17, leading=24,
                                  textColor=colors.HexColor("#33475B"), alignment=TA_LEFT)
    # 警示框正文
    S["warn"] = ParagraphStyle("warn", parent=S["body"], fontSize=9.8, leading=14.6,
                               spaceAfter=0)
    S["warnh"] = ParagraphStyle("warnh", parent=S["warn"], fontName="ZH-B",
                                spaceAfter=2)
    # 附录术语双栏
    S["gloss"] = ParagraphStyle("gloss", fontName="ZH", fontSize=8.6, leading=11.8,
                                wordWrap="CJK", alignment=TA_LEFT, spaceAfter=0)
    S["glossH"] = ParagraphStyle("glossH", parent=S["gloss"], fontName="ZH-B")
    # 大标题（文档题名）居中
    S["title"] = ParagraphStyle("title", fontName="ZH-B", fontSize=17.5, leading=24,
                                alignment=TA_CENTER, textColor=colors.black,
                                spaceAfter=10, wordWrap="CJK")
    S["subtitle"] = ParagraphStyle("subtitle", fontName="ZH-B", fontSize=12.5,
                                   leading=18, alignment=TA_CENTER,
                                   textColor=BRAND_DARK, spaceAfter=8, wordWrap="CJK")
    if flow:
        # 流式重排：标题/表题不许落在页底与正文分离（孤标题）。1:1 模式不开 ——
        # 每页自成一个 PageBreak 单元，开了反而改动已交付稿的分页。
        for k in ("section", "h1", "h2", "h3", "tcap", "title", "subtitle", "warnh"):
            S[k].keepWithNext = 1
    return S
