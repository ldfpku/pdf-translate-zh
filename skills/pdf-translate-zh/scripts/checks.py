# -*- coding: utf-8 -*-
"""自检层。每一项都必须报 0（SKILL §2、§6）。

skill 自带的 scripts/verify.py 把页面尺寸写死为 612x792，本模块是它的
几何无关版本，供横版图纸（1224x792）与 A4 文档共用；letter 纵版文档
两者都跑，互为交叉验证。

  test_zh       zh() 全角规范化单元测试
  test_dsl      块 DSL 可选参数位置（避坑 ⑧ 曾让所有 alpha 静默退化成数字）
  test_fit      逐页装配：每个逻辑页单独排一次，实测必须 1 页（避坑 ㉓）
  test_assets   引用的图文件都存在；并列出未被引用的图供人判断
  test_labels   figures.json 里每条图内标注都有中文译名或属「保留不译」白名单
  test_terms    零件描述 100% 命中规则（避坑：杜绝同物异名）
  check_margins 版心外杂物：四边页边带内不得有任何墨迹（避坑 ⑱ 曾误画 981 条）
  check_footer  版心底沿与页脚之间留有净空（避坑 ㉒）
  check_labels  每页都有页码标签；正文页码序列连续（避坑 ㉔）
  check_text    残留英文行 / 中文行里的半角标点
  check_fig_clip   图边净空：插图裁框内不得残留未处置的英文（含英文图题）
  check_word_split 西文断词：西文词不得被折行从中间劈开
  check_margin_rules 页边杂线：版心右界之外不得有任何竖线
  check_thin_pages   孤页：正文页上不得只剩一两行字
"""
import json
import os
import re
import sys

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz
import numpy as np

from zhlib import zh

NUMERIC_KEEP = re.compile(r"^(?:\(?\d{1,2}\)?|[A-K])$")   # 件号气泡/尺寸字母：图形语言


# ---------------------------------------------------------------- 单元测试
_ZH_CASES = [
    # (输入, 期望)
    ("转子与定子的配合, 应符合下表;", "转子与定子的配合，应符合下表；"),
    ("公称尺寸 1,500 lbf 不变", "公称尺寸 1,500 lbf 不变"),
    ("间隙 3.75 mm", "间隙 3.75 mm"),
    ("见 Fig. 6-4 所示", "见 Fig. 6-4 所示"),
    ("型号 XS21.39947P 适用", "型号 XS21.39947P 适用"),
    ("扳手 T-20 与 NC31 接头", "扳手 T-20 与 NC31 接头"),
    ("温度范围 30-35 摄氏度", "温度范围 30-35 摄氏度"),
    ("尺寸 1/2 英寸", "尺寸 1/2 英寸"),
    ("打印时间 9:52 有效", "打印时间 9:52 有效"),
    ("打印于 2020 年 12 月 17 日 9:52:06", "打印于 2020 年 12 月 17 日 9:52:06"),
    ("（注意）本条适用", "（注意）本条适用"),
    ("说明(见附录)如下", "说明（见附录）如下"),
    # 不含中文的串一律原样返回：术语表英文列、保留原样的英文零件描述
    ("This is English, untouched;", "This is English, untouched;"),
    ("Rev A, Sheet 2 of 3", "Rev A, Sheet 2 of 3"),
    ("PolyPak Seal, Rod Style", "PolyPak Seal, Rod Style"),
    ("以中文结尾.", "以中文结尾。"),
    ("<b>加粗</b>, 保留标签", "<b>加粗</b>，保留标签"),
    # URL 保护不得吞掉紧随其后的逗号
    ("参见 www.example.com, 获取详情", "参见 www.example.com，获取详情"),
    ("详见 https://example.com/a?b=1, 另见附录", "详见 https://example.com/a?b=1，另见附录"),
    # 占位符碰撞（旧版印出「H\x0031,2004\x00S」）：受保护片段 ≥ 3 个且相邻
    ("<b>警告：</b>压差不得超过 1,200 psi, 含 H<sub>2</sub>S 时",
     "<b>警告：</b>压差不得超过 1,200 psi，含 H<sub>2</sub>S 时"),
]


def test_zh():
    bad = []
    for src, want in _ZH_CASES:
        got = zh(src)
        if got != want:
            bad.append((src, want, got))
    # 全角标点两侧不留空格
    if zh("甲 , 乙") != "甲，乙":
        bad.append(("甲 , 乙", "甲，乙", zh("甲 , 乙")))
    # 幂等：内容层可能对同一串反复调用
    for src, _ in _ZH_CASES:
        if zh(zh(src)) != zh(src):
            bad.append((src, "幂等", zh(zh(src))))
    return bad


def test_dsl():
    """("ol", items, mode) 与 ("ol_from", start, items, mode) 的 mode 下标不同。"""
    from render import flow, marker
    from zhlib import styles
    S = styles()
    bad = []
    if marker(1, "alpha") != "a." or marker(3, "ALPHA") != "C.":
        bad.append(("marker", "alpha/ALPHA", marker(1, "alpha")))
    if marker(4, "roman") != "iv." or marker(2, "paren") != "（2）":
        bad.append(("marker", "roman/paren", marker(4, "roman")))
    got = flow([("ol", ["甲", "乙"], "alpha")], S)
    if "a." not in got[0].text:
        bad.append(("ol", "a. 前缀", got[0].text[:20]))
    got = flow([("ol_from", 3, ["甲", "乙"], "alpha")], S)
    if "c." not in got[0].text:
        bad.append(("ol_from", "c. 前缀", got[0].text[:20]))
    got = flow([("ol", ["甲"])], S)
    if "1." not in got[0].text:
        bad.append(("ol", "缺省 num", got[0].text[:20]))
    return bad


# ---------------------------------------------------------------- 素材自检
def _norm(s):
    """JSON 里的名称常含前导/多重空格，查字典必然 miss（避坑 ⑫）。"""
    return " ".join(str(s).split())


def test_labels(work, LABELS, keep_re=NUMERIC_KEEP):
    """figures.json 里每条被抹除的英文标注都必须有中文译名。"""
    fp = os.path.join(work, "data", "figures.json")
    if not os.path.exists(fp):
        return []
    figs = json.load(open(fp, encoding="utf-8"))
    keys = {_norm(k) for k in LABELS}
    miss = {}
    for m in figs:
        for lb in m["labels"]:
            t = _norm(lb["text"])
            if not t or keep_re.match(t) or t in keys:
                continue
            miss.setdefault(t, []).append(f"{m['file']}")
    return sorted((t, v[:4], len(v)) for t, v in miss.items())


def test_assets(work, used_files):
    """引用的图都在；并列出未被引用的图供人判断（可能是漏译的插图）。"""
    figdir = os.path.join(work, "figures")
    have = ({f for f in os.listdir(figdir) if f.lower().endswith(".png")}
            if os.path.isdir(figdir) else set())
    used = set(used_files)
    return sorted(used - have), sorted(have - used)


def test_terms(uniq_desc, desc_zh):
    """零件描述 100% 命中规则。未命中数必须为 0。"""
    miss = []
    for d in uniq_desc:
        try:
            r = desc_zh(d)
        except Exception as e:
            miss.append((d, f"异常 {e}"))
            continue
        if not r or r == d:
            miss.append((d, "未命中"))
    return miss


# ---------------------------------------------------------------- 成品自检
def _ink(page, rect, dpi=150, thr=170):
    if rect.height <= 0.5 or rect.width <= 0.5:
        return 0
    z = dpi / 72.0
    pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(z, z), alpha=False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, 3)
    return int((a.min(axis=2) < thr).sum())


def check_margins(pdf, geom, skip=(), inset=2.0, edge=8.0):
    """四边页边带内不得有任何墨迹。

    「表格右侧凭空多出竖线」正属此类 —— 阈值一旦放宽到版心之内，
    每张表的右边框都会被当成变更条（避坑 ⑱，实测误检 981 条）。
    """
    bad = []
    with fitz.open(pdf) as doc:
        top = geom.mast_top
        for i, p in enumerate(doc):
            if (i + 1) in skip:
                continue
            for name, r in (
                    ("右页边", fitz.Rect(geom.w - geom.mr + inset, top,
                                         geom.w - edge, geom.h - geom.mb)),
                    ("左页边", fitz.Rect(edge, top,
                                         geom.ml - inset, geom.h - geom.mb))):
                n = _ink(p, r)
                if n:
                    bad.append((i + 1, name, n))
    return bad


def check_footer(pdf, geom, skip=(), tol=30):
    """版心底沿与页脚上沿之间必须留净空（避坑 ㉒）。

    fitz 左上原点、ReportLab 左下原点，必须换算。
    """
    bad = []
    with fitz.open(pdf) as doc:
        for i, p in enumerate(doc):
            if (i + 1) in skip:
                continue
            r = fitz.Rect(geom.ml, geom.h - geom.mb + 2,
                          geom.w - geom.mr, geom.h - geom.foot_top - 2)
            if r.height <= 1:
                continue
            n = _ink(p, r)
            if n > tol:
                bad.append((i + 1, n))
    return bad


def check_labels(pdf, body_pages=0, offset=1, skip=(), start=1):
    """每页都有页码标签；正文页码序列必须严格 start..body_pages（避坑 ㉔）。

    start 不总是 1：原版封面往往不印「Page 1 of N」，页码自第 2 页起 ——
    此时 start=2，序列应为 2..N，硬套 1..N 会误报。
    """
    nolabel, nums = [], []
    with fitz.open(pdf) as doc:
        for i, p in enumerate(doc):
            t = p.get_text()
            if body_pages:
                m = re.search(rf"第\s*(\d+)\s*页\s*/\s*共\s*{body_pages}\s*页", t)
                if m:
                    nums.append(int(m.group(1)))
            if (i + 1) in skip:
                continue
            if not re.search(r"第\s*[\divx]+\s*页\s*/\s*共|附录\s*[A-Z]-\d", t):
                nolabel.append(i + 1)
    seq_ok = (nums == list(range(start, body_pages + 1))) if body_pages else True
    return nolabel, nums, seq_ok


# 通用白名单：修订号、版权符、网址。品牌名/人名/型号等**逐文档**用
# Job.whitelist_add / whitelist_re 追加。
_WL_DEFAULT = r"Rev\b|©|http|www\."


# 「纯技术记号行」：整行只由单位、螺纹/连接代号、标准组织名、含数字的记号、
# ≤2 字母的大写代号组成 —— 这是原样保留的内容（表格单位列、「4-1/2 REG」），
# 不算残留英文。按**整行每个词**判，不按子串：`Do not exceed 1,000 psi`
# 里有 psi 也照样报（旧做法若把 psi 加进白名单正则，这句漏译就被放行了）。
_TECH_WORDS = set("""
psi ksi kpa mpa bar gpm bpm lpm spm rpm rev/gal rev/min r/min ft in mm cm m km
lb lbs lbf klb klbs kip kips ft-lb ft-lbf ft-lbs lbf-ft lb-ft n-m n·m nm kn kgf kg g t
hp kw w kwh v a hz °f °c f c ppg sg cp mpa·s gal bbl bbl/min l ml cc hr h min s sec
deg ° in. ft. od id md tvd wob rop bht nbr hnbr fkm
reg if fh nc pac ht xt ih sh eue nue btc ltc stc vam premium pin box
api astm asme aws iso nace din sae ams ansi iec gb sy en bs jis ieee
""".split())


def _tech_only(s):
    toks = re.findall(r"\S+", s)
    if not toks:
        return False
    for t in toks:
        w = t.strip(".,;:()[]（）").lower()
        if not w or re.search(r"\d", w) or w in _TECH_WORDS:
            continue
        if re.fullmatch(r"[A-Z]{1,2}", t.strip(".,;:()[]（）")):
            continue
        if re.fullmatch(r"[-–—/×x±~≈=+*%#&]+", w):
            continue
        return False
    return True


def check_text(pdf, allow_pages=(), whitelist=_WL_DEFAULT):
    """残留英文行 / 中文行里的半角标点。

    人名、URL、勘误表引用的英文原文、术语对照表属合法白名单，须人工过一遍。
    """
    NOISE = re.compile(r"[A-Za-z]{3,}")
    WL = re.compile(whitelist)
    eng, half = [], []
    with fitz.open(pdf) as doc:
        for i, p in enumerate(doc):
            if (i + 1) in allow_pages:
                continue
            for line in p.get_text().splitlines():
                s = line.strip()
                if not s:
                    continue
                if NOISE.search(s) and not re.search(r"[一-鿿]", s) \
                        and not WL.search(s) and not _tech_only(s):
                    eng.append((i + 1, s[:90]))
                if re.search(r"[一-鿿]", s):
                    for m in re.finditer(r"[,;:?!]", s):
                        j = m.start()
                        prv = s[j - 1] if j else ""
                        nxt = s[j + 1] if j + 1 < len(s) else ""
                        if m.group(0) in ",:" and prv.isdigit() and nxt.isdigit():
                            continue
                        half.append((i + 1, m.group(0), s[:80]))
    return eng, half


_MISSING_GLYPHS = None


def font_missing(fontfile=None):
    """正文字体的字符集合（缓存）。缺省取 ReportLab 路线实际注册的正文字体。"""
    global _MISSING_GLYPHS
    if _MISSING_GLYPHS is not None:
        return _MISSING_GLYPHS
    try:
        if fontfile is None:
            import fontkit
            fontfile = fontkit.find("zh", reportlab=True)
        from fontTools.ttLib import TTCollection, TTFont
        f = (TTCollection(fontfile).fonts[0] if fontfile.lower().endswith(".ttc")
             else TTFont(fontfile))
        _MISSING_GLYPHS = f.getBestCmap()
    except Exception:
        _MISSING_GLYPHS = None
    return _MISSING_GLYPHS


_OUR_CMAPS = None


def _our_cmaps():
    """{规范化字体名: cmap} —— 本机实际用来写中文的全部字体（fontkit 解析结果）。

    字体随机器而变（雅黑 / 苹方 / Noto / 文泉驿 / 内置 Droid），缺字判据必须按
    **实际写入的那个字体**查 cmap；旧版只认名字里带 yahei 的 span，换到
    Linux 上一个字都不查，闸门静默放行（实测文泉驿缺 `•`，项目符号整列空白）。
    """
    global _OUR_CMAPS
    if _OUR_CMAPS is not None:
        return _OUR_CMAPS
    _OUR_CMAPS = {}
    try:
        import fontkit
        from fontTools.ttLib import TTFont
    except Exception:
        return _OUR_CMAPS
    paths = set()
    for role in ("zh", "zh-bold", "hei", "song"):
        for rl in (False, True):
            try:
                p = fontkit.find(role, reportlab=rl, required=False)
            except Exception:
                p = None
            if p:
                paths.add(p)
    for p in paths:
        try:
            f = TTFont(p, lazy=True, fontNumber=0)
            names = {str(f["name"].getDebugName(6) or ""), str(f["name"].getDebugName(4) or "")}
            cmap = f.getBestCmap()
        except Exception:
            continue
        for n in names:
            key = re.sub(r"[\s\-_]", "", n).lower()
            if key:
                _OUR_CMAPS[key] = cmap
    return _OUR_CMAPS


def _cmap_for(fontname, fallback):
    """span 字体名 → 对应 cmap；不是我们写入的字体返回 None（不查）。"""
    key = re.sub(r"[\s\-_]", "", fontname.split("+", 1)[-1]).lower()
    ours = _our_cmaps()
    for k, cm in ours.items():
        if key.startswith(k) or k.startswith(key.rstrip("0123456789")):
            return cm
    if re.search(r"yahei|^zh", fontname.replace(" ", ""), re.I):
        return fallback
    return None


def check_glyphs(pdf, skip=(), only_fonts="ours"):
    """缺字自检：正文出现字体没有的字符会渲染成豆腐块 □（或空白）。

    实测微软雅黑**缺 ⑪~⑳（U+246A~U+2473）**，而 ①~⑩ 与 ㉑~㉘ 都有 ——
    在勘误里引用「SKILL 避坑 ⑮／⑳」就会渲染成方框；Linux 的文泉驿缺 `•`。
    属「靠肉眼才能发现」的缺陷，必须有机器判据（SKILL ㉘）。

    ⚠ **只查我们自己写进去的那些字**（避坑 86）。拿整页文本去比对中文字体的
    cmap，会把**原版保留下来的**符号（自带 Wingdings 的项目符号）一律报成
    豆腐块 —— 实测一次 41 处全是假阳。⇒ 按 span 的**字体名**分流：
    only_fonts="ours"（缺省）= 按 fontkit 实际解析出的字体逐 span 查各自 cmap；
    传正则 = 旧行为（名字匹配的 span 用正文字体 cmap 查）；传 None = 整页扫描。
    """
    cmap = font_missing()
    if not cmap and only_fonts != "ours":
        return []
    pat = (re.compile(only_fonts, re.I)
           if only_fonts and only_fonts != "ours" else None)
    bad, seen = [], set()
    with fitz.open(pdf) as doc:
        for i, p in enumerate(doc, 1):
            if i in skip:
                continue
            if only_fonts is None:
                for ch in p.get_text():
                    if ch.isspace() or ord(ch) < 0x80 or (i, ch) in seen:
                        continue
                    seen.add((i, ch))
                    if cmap and ord(ch) not in cmap:
                        bad.append((i, ch, hex(ord(ch))))
                continue
            for blk in p.get_text("dict")["blocks"]:
                if blk.get("type") != 0:
                    continue
                for ln in blk["lines"]:
                    for sp in ln["spans"]:
                        if pat is not None:
                            if not pat.search(sp["font"].replace(" ", "")):
                                continue
                            cm = cmap
                        else:
                            cm = _cmap_for(sp["font"], cmap)
                            if cm is None:
                                continue
                        for ch in sp["text"]:
                            if ch in "\x00\ufffd":
                                # PyMuPDF 写入字体里没有的字形时，文本层留下 \x00
                                bad.append((i, "<缺字形>", sp["text"][:20]))
                                continue
                            if ch.isspace() or ord(ch) < 0x80 or (i, ch) in seen:
                                continue
                            seen.add((i, ch))
                            if ord(ch) not in cm:
                                bad.append((i, ch, hex(ord(ch))))
    return bad


def check_codepoints(pdf, skip=()):
    """文本层异常码位：U+2011 / U+00A0 / U+00AD，以及兼容汉字、康熙部首（「量」→U+F97E）。

    字体 cmap 让 `-`、空格与这些码位共用字形时，PyMuPDF 反查会取到别名 ——
    渲染看不出任何异样，但图号「675-200-011」在成品里搜不到、复制出来也不对
    （实测 Noto CJK，避坑 117）。返回 [(页, 码位, 上下文)]。
    """
    bad = []
    # 不换行变体 + 兼容汉字（U+F900~FAFF、U+2F800~2FA1F）+ 康熙部首/部首补充
    pat = re.compile("[\u2011\u00a0\u00ad\uf900-\ufaff\u2e80-\u2fdf\U0002f800-\U0002fa1f]")
    with fitz.open(pdf) as doc:
        for i, p in enumerate(doc, 1):
            if i in skip:
                continue
            t = p.get_text()
            for m in pat.finditer(t):
                bad.append((i, "U+%04X" % ord(m.group(0)),
                            t[max(0, m.start() - 12):m.end() + 12].replace("\n", " ")))
                if len(bad) > 50:
                    return bad
    return bad


# ---------------------------------------------------------------- 内容对账
_TOKEN_RE = re.compile(
    r"(?=[A-Za-z0-9\-./,]*\d)"            # 至少含一个数字：数值、件号、型号、标准号
    r"[A-Za-z0-9][A-Za-z0-9\-./,]*[A-Za-z0-9]|\d")


def doc_tokens(pdf, pages=None, min_len=2):
    """整册「应原样保留」的记号全集（数字/件号/型号/标准号），按出现次数计。"""
    from collections import Counter
    cnt = Counter()
    with fitz.open(pdf) as d:
        for i, pg in enumerate(d, 1):
            if pages is not None and i not in pages:
                continue
            for m in _TOKEN_RE.finditer(pg.get_text()):
                t = m.group(0).strip(".,")
                if len(t) >= min_len:
                    cnt[t] += 1
    return cnt


def check_content_tokens(src, out, src_pages=None, out_pages=None,
                         ignore=(), min_len=2):
    """**R 级第一关：内容对账**（整册，不按页 —— 重排后页码与原版脱钩）。

    源版上每一个数字/件号/型号/标准号记号，都必须在译版正文里找到归宿。
    译文不改写这类记号，所以「源有、译无」＝漏译整段、丢表格行、丢图题。
    比对时两边都去掉全部空白（表格列在源上常被并成一串）。

    src_pages / out_pages : 参与比对的页号集合（1 基）；out 通常要排除附录页，
                            否则术语表里恰好出现的数字会替漏译「作证」。
    ignore                : 允许消失的记号（页眉页脚里的原版页码、修订号等）。
    返回 [(记号, 源版出现次数)]。
    """
    want = doc_tokens(src, src_pages, min_len)
    with fitz.open(out) as d:
        have = "".join("".join(pg.get_text().split())
                       for i, pg in enumerate(d, 1)
                       if out_pages is None or i in out_pages)
    ign = set(ignore)
    return [(t, n) for t, n in sorted(want.items())
            if t not in ign and t not in have]


_NO_START_RE = re.compile(r"^[，、。．；：！？）〕］｝〉》」』】〗…‥ー～·’”%]")


def check_line_start(pdf, skip=()):
    """避头尾自检：中文行不得以收尾类标点开头。

    ReportLab 自带的 CJK 禁则表漏收 ，；：！？，zhlib._patch_kinsoku() 补齐后
    用本判据复验 —— 属「靠肉眼才能发现」的缺陷，必须有机器判据（SKILL ㉘）。
    按渲染后的实际行首字符判定，而非按源文本。
    """
    bad = []
    with fitz.open(pdf) as doc:
        for i, p in enumerate(doc):
            if (i + 1) in skip:
                continue
            for blk in p.get_text("dict")["blocks"]:
                if blk.get("type") != 0:
                    continue
                for ln in blk["lines"]:
                    t = "".join(s["text"] for s in ln["spans"]).lstrip()
                    if t and _NO_START_RE.match(t):
                        bad.append((i + 1, t[:40]))
    return bad


_NO_END_RE = re.compile(r"[（〔［｛〈《「『【〖‘“]$")


def check_line_end(pdf, skip=()):
    """行尾禁则：中文行不得以起首类标点收尾（「（」「“」「《」…）。

    与行首禁则成对。ReportLab 从不查 ALL_CANNOT_END，而「断点回溯到西文词首」
    恰好把词前的「（」留在上一行行尾（kinsoku2 补丁三已修，本判据复验）。
    """
    bad = []
    with fitz.open(pdf) as doc:
        for i, p in enumerate(doc):
            if (i + 1) in skip:
                continue
            for blk in p.get_text("dict")["blocks"]:
                if blk.get("type") != 0:
                    continue
                for ln in blk["lines"]:
                    t = "".join(s["text"] for s in ln["spans"]).rstrip()
                    if t and _NO_END_RE.search(t) and re.search(r"[\u4e00-\u9fff]", t):
                        bad.append((i + 1, t[-40:]))
    return bad


def check_fig_pages(src_pdf, work):
    """每幅裁图必须来自它自己那一页（避坑 ⑤/㉘：内层循环覆盖页序号）。

    参考图墨迹按 ±2px 膨胀以容忍取整位移；抗锯齿差异 ≤2%，取错页面 ≥50%。
    """
    from PIL import Image
    fp = os.path.join(work, "data", "figures.json")
    if not os.path.exists(fp):
        return [], 0
    figs = json.load(open(fp, encoding="utf-8"))
    bad, n = [], 0
    with fitz.open(src_pdf) as doc:
        for m in figs:
            path = os.path.join(work, "figures", m["file"])
            if not os.path.exists(path):
                continue
            b = fitz.Rect(m["bbox"])
            z = m["dpi"] / 72.0
            ref = doc[m["page"] - 1].get_pixmap(clip=b, matrix=fitz.Matrix(z, z),
                                                alpha=False)
            a = np.frombuffer(ref.samples, dtype=np.uint8).reshape(
                ref.height, ref.width, 3).min(axis=2)
            im = Image.open(path).convert("L")
            if abs(im.width - ref.width) > 3 or abs(im.height - ref.height) > 3:
                bad.append((m["file"],
                            f"尺寸不符 {im.size} vs {(ref.width, ref.height)}"))
                continue
            h, w = min(im.height, ref.height), min(im.width, ref.width)
            g, a = np.asarray(im)[:h, :w], a[:h, :w]
            ri = a < 200
            dil = ri.copy()
            for dy in (-2, -1, 0, 1, 2):
                for dx in (-2, -1, 0, 1, 2):
                    dil |= np.roll(np.roll(ri, dy, axis=0), dx, axis=1)
            gi = g < 200
            both = (ri | gi).sum()
            extra = (gi & ~dil).sum()
            n += 1
            if both and extra / max(both, 1) > 0.08:
                bad.append((m["file"],
                            f"多出墨迹 {extra/both:.1%}（疑似取错页面）"))
    return bad, n


# ---------------------------------------------------------------- 汇总
def report(name, bad, detail=6):
    ok = not bad
    print(f"  {'OK  ' if ok else 'FAIL'} {name}: {len(bad) if not ok else 0} 处")
    for x in list(bad)[:detail]:
        print("        ", x)
    return ok


def check_overlap(pdf, frac=0.35, skip=()):
    """**中文重叠自检**：同页两处中文写入区互相压叠即报。

    为什么需要这道关：前四关（未命中／溢出／残留英文／缺字）**全部看不见重叠** ——
    字确实写进去了、字号够、rc 非负、无方框。已两次栽在这上面：
      · 手册 C 旋转页：中文写成镜像／竖排（靠出图目检才发现）；
      · 手册 I 第 14 页：同一竖排文字被旋转通道与行级通道各写一次，
        「旋转钻进」与碎片「钻进」「旋转」叠在一起。

    判据：取每页所有含中文的文本行 bbox，两两求交；
    交集面积 ≥ frac × 较小者面积即判为重叠。
    frac 取 0.35 —— 正常相邻行的 bbox 会轻微相接（抗锯齿与行距容差），
    但不会大面积重叠。
    """
    try:
        import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
    except ImportError:
        import fitz
    import re as _re
    doc = fitz.open(pdf)
    bad = []
    for i, pg in enumerate(doc, 1):
        if i in skip:
            continue
        boxes = []
        for b in pg.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                t = "".join(s["text"] for s in ln["spans"]).strip()
                if t and _re.search(r"[\u4e00-\u9fff]", t):
                    boxes.append((fitz.Rect(ln["bbox"]), t))
        for a in range(len(boxes)):
            for c in range(a + 1, len(boxes)):
                ra, rc = boxes[a][0], boxes[c][0]
                inter = (ra & rc).get_area()
                if inter <= 0:
                    continue
                small = min(ra.get_area(), rc.get_area()) or 1
                # **纵向判据**：真正的叠字几乎共线，行框上下重合大半；
                # 而相邻两行只是轻微相接。缺这一条会误报 —— 实测
                # ReportLab 附录表里 MuPDF 把同一基线的**两个单元格**并成
                # 一行（行框因此偏高），下一行与它交叠 3pt 就被判成叠字。
                vov = min(ra.y1, rc.y1) - max(ra.y0, rc.y0)
                vmin = min(ra.height, rc.height) or 1
                if inter / small >= frac and vov / vmin >= 0.55:
                    bad.append((i, boxes[a][1][:24], boxes[c][1][:24],
                                round(100 * inter / small)))
    doc.close()
    return bad


def check_kept_tokens(src, out, keep=None, min_len=3):
    """**第六关：保留项失踪自检**（源 PDF → 成品 PDF 逐页比对）。

    前五关（未命中／溢出／残留英文／缺字／重叠）都只看**成品上写了什么**，
    看不见**源文档上少了什么**。而叠印路线最凶险的失效恰恰是后者：

      · MuPDF 把「表格最后一行的 8pt 单元格」与其下方「12pt 脚注」归进
        同一个 block ⇒ 合并框进 redaction ⇒ **整行 13 列扭矩值被抹掉**；
      · 几何去重把内容无关的小框并进大框 ⇒ 被丢者文本无人翻译，
        却仍随大框一起被抹；
      · keep 规则前缀匹配失当 ⇒ 整行正文被跳过（这一类反而残留英文能抓到）。

    三者的共同症状是「五关全绿、页面上东西没了」，只有出图目检能发现 ——
    而 92 页逐页目检不现实。本关把它变成机器判据。

    判据：取源页上**应当原样保留**的记号（件号、扭矩值、尺寸等，
    即 `keep()` 判真且长度 ≥ min_len 的词），逐页检查它们是否仍出现在
    成品同一页的文本里。译文不会改写这类记号，所以「源有、成品无」
    只可能是被 redaction 抹掉了。

    返回 [(页号, 失踪记号, 该页失踪总数)]，每页最多报 6 条。
    """
    import re
    try:
        import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
    except ImportError:
        import fitz
    if keep is None:
        _k = re.compile(r"^(?=[A-Za-z0-9\-.,/]*\d)[A-Za-z0-9\-.,/()]{3,}$")
        def keep(t):
            return bool(_k.match(t))
    a, b = fitz.open(src), fitz.open(out)
    bad = []
    for i in range(min(len(a), len(b))):
        # 成品里记号常紧贴中文标点（「，7/8」「0.015。」），按空白分词比对必然误报；
        # 源记号也常带句末点号（`E709.`）。⇒ 源侧去掉首尾标点，成品侧去掉全部空白
        # 后按**子串**找（两边都不分词）。
        have = "".join(b[i].get_text().split())
        want = [w.strip(".,;:()[]") for w in a[i].get_text().split()]
        want = [w for w in want if len(w) >= min_len and keep(w)]
        miss = [w for w in dict.fromkeys(want) if w not in have]
        for w in miss[:6]:
            bad.append((i + 1, w, len(miss)))
    a.close()
    b.close()
    return bad


def check_fig_clip(entries):
    """图边净空：成品插图的裁框内不得残留任何未处置的英文。

    ⚠ 这一关是用户目检报回来才补的（避坑 ㊾ 的又一例）：中文图题正上方
    横着半截「Figure 4-7」，而**九道关一处不报** —— 图题被裁进了位图，
    位图不进文本层，残留英文关（关2）扫的是文本层。规范 G 24 幅里 16 幅、
    规范 H 6 幅里 1 幅、第 7 节 22 张照片里 12 张全中，同一根因。

    根因是坐标来源：裁框由「位图 bbox / 矢量簇并集 / 标注外扩」推出，
    **三者都不知道英文图题在哪**，各加几 pt 余量就吃进去了。
    ⇒ 判据只能回到源页几何：裁框 ∩ 未 redaction 的文本 span = ∅。

    entries: [dict(name, src, page, clip, red=[矩形...], keep=正则)]
    """
    import figclip
    bad = []
    cache = {}
    for e in entries:
        key = (e["src"], e["page"], tuple(tuple(r) for r in e.get("red", ())))
        page = cache.get(key)
        if page is None:
            d = fitz.open(e["src"])
            page = d[e["page"] - 1]
            for r in e.get("red", ()):
                page.add_redact_annot(fitz.Rect(*r))
            if e.get("red"):
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            cache[key] = page
        for t, r, ov in figclip.residual(page, fitz.Rect(*e["clip"]),
                                         keep=e.get("keep")):
            bad.append((e["name"], t[:44], "交%d%%" % round(ov * 100)))
    return bad


def check_word_split(out, src=None, skip_pages=()):
    """西文断词：西文词不得被折行从中间劈开。

    ⚠ 目检报回来的：窄栏里排出「（第 2 代 RotaMas / ter）」，读者会当成
    两个词。`wordWrap="CJK"` 认为任意两字符之间都可断，而 ReportLab 原生的
    「往回找空格」只允许回溯到**行长的一半** —— 空格在前半段就放弃回溯、
    原地硬断。列宽的原子下限（ATOM_RE）保证不了这一点：它只保证「该词
    单独一行放得下」，管不了前面还压着几个汉字。

    判据走了三稿，前两稿都不成立，记在这里免得再走一遍：

    ①「上一行西文字母收尾 + 下一行小写西文字母起头」——**假阳**。纯英文
      段落在空格处正常折行，提取层一模一样；四册共报 36 处，全是
      「positive displacement / motor」这类。靠「跳过附录页」压下去等于把
      附录整块放行（避坑 59）。
    ② 再加「两截须各自是本文档里独立出现过的词」——**假阴，而且是自证式的**：
      词表取自成品自己，劈开的两截恰恰因为被劈开才各自单独成行，于是
      「RotaMas」「ter」双双进了词表，判据反过来给自己盖章。负对照
      （停用断行补丁重建）实测报 0 —— 完全失效而毫无征兆。
    ③ **看拼起来是不是一个词**：`RotaMas` + `ter` = `rotamaster`，
      是这份文档里真实存在的词 ⇒ 被劈开了；`displacement` + `motor` =
      `displacementmotor`，哪儿都不存在 ⇒ 是空格处正常折行。
      词表取源版 ∪ 成品，不需要外部词典，也不需要页码黑名单。
    """
    import re as _re
    tail = _re.compile(r"[A-Za-z][A-Za-z'-]*$")
    head_ = _re.compile(r"^[a-z][A-Za-z'-]*")
    tok = _re.compile(r"(?<![A-Za-z])[A-Za-z][A-Za-z'-]*(?![A-Za-z])")
    vocab = set()
    for path in ([src] if src else []) + [out]:
        with fitz.open(path) as a:
            for p in a:
                vocab.update(m.group(0).lower() for m in tok.finditer(p.get_text()))
    bad = []
    with fitz.open(out) as d:
        for i, p in enumerate(d):
            if (i + 1) in skip_pages:
                continue
            for blk in p.get_text("dict")["blocks"]:
                if blk["type"] != 0:
                    continue
                prev = None
                for l in blk["lines"]:
                    t = "".join(s["text"] for s in l["spans"]).strip()
                    if prev:
                        a = tail.search(prev)
                        b = head_.match(t)
                        if a and b and (a.group(0) + b.group(0)).lower() in vocab:
                            bad.append((i + 1, prev[-18:] + " / " + t[:18]))
                    prev = t
    return bad


def check_margin_rules(out, frame_right, skip_pages=(), tol=1.0):
    """页边杂线：版心右界之外不得有任何竖线。

    ⚠ 用户两轮都点了同一处：正文右侧一条细竖线，读作「线画重了」。
    查证结果是**源版的修订条**（`Revision bar in margin indicates the latest
    revision.`），译版与源版逐段对得上，并非画错 —— 但用户判定不要它。
    去掉之后必须有判据顶上：页边一旦再冒出竖线，就只可能是真正的杂线
    （表格右框线跑出版心、装饰线、残留的抹除框边），而这一类**六道关
    一处不报**（它既不是文字也不越界，只是「多了一根线」）。

    判据只需一条常数：**版心右界**。表格的右框线正好落在版心右界上，
    合法；再往右一律非法。封面/封底等满版美术页另行豁免。
    """
    bad = []
    with fitz.open(out) as d:
        for i, p in enumerate(d):
            if (i + 1) in skip_pages:
                continue
            for dr in p.get_drawings():
                for it in dr["items"]:
                    seg = None
                    if it[0] == "l":
                        a, b = it[1], it[2]
                        if abs(a.x - b.x) < 0.6 and abs(a.y - b.y) > 3:
                            seg = (a.x, min(a.y, b.y), max(a.y, b.y))
                    elif it[0] == "re":
                        r = it[1]
                        if r.width < 2 and r.height > 3:
                            seg = (r.x0, r.y0, r.y1)
                    if seg and seg[0] > frame_right + tol:
                        bad.append((i + 1, round(seg[0], 1),
                                    "y=%.1f~%.1f" % (seg[1], seg[2])))
    return bad


def check_thin_pages(out, min_lines=3, skip_pages=()):
    """孤页：正文页上只剩一两行字，且无表无图。

    ⚠ 空白页判据（关7）看不见它 —— 页上确实有字。实测撤掉修订条包装后
    段距恢复正常，正文正好多出**一行**，而其后紧跟着「报告检查表」的硬分页，
    于是那一行独占一页。整册缩览一眼可辨，逐页文本却查不出来。
    """
    bad = []
    with fitz.open(out) as d:
        for i, p in enumerate(d):
            if (i + 1) in skip_pages:
                continue
            if p.get_images() or len(p.get_drawings()) > 12:
                continue
            lines = [l for b in p.get_text("dict")["blocks"] if b["type"] == 0
                     for l in b["lines"]
                     if "".join(s["text"] for s in l["spans"]).strip()]
            # 页眉页脚固定占若干行，扣掉：只数落在版心带内的
            body = [l for l in lines if 50 < l["bbox"][1] < p.rect.height - 90]
            if 0 < len(body) < min_lines:
                bad.append((i + 1, len(body),
                            "".join(s["text"] for s in body[0]["spans"])[:40]))
    return bad


def check_appendix_pages(pdf, spans, need=("A", "B")):
    """附录与译文分隔：附录 A、B 齐全，各自另起一页，标题落在起始页顶部。

    spans = [(tag, 起始页, 结束页)]（1 基），由 build_2pass / appendix.append_to 返回。
    判据：
      · A、B 都在（每份译稿必须附两份附件）；
      · A 起于正文之后的新页，B 紧接 A 的末页之后另起一页（页号衔接、不重叠）；
      · 起始页上附录标题是**版心里的第一段文字** —— 标题上方还有正文，
        就是正文与附录挤在了同一页。
    """
    from appendix import A_TITLE, B_TITLE
    titles = {"A": A_TITLE, "B": B_TITLE}
    norm = lambda t: re.sub(r"\s+", "", t or "")
    bad = []
    tags = [t for t, _, _ in spans]
    for t in need:
        if t not in tags:
            bad.append((t, "缺失（terms.py 的 GLOSSARY / JIA / YI / BING 未填？）"))
    with fitz.open(pdf) as d:
        prev = None
        for tag, p0, p1 in spans:
            if not (1 <= p0 <= p1 <= d.page_count):
                bad.append((tag, f"页号越界 {p0}~{p1}（共 {d.page_count} 页）"))
                continue
            if prev is not None and p0 != prev + 1:
                bad.append((tag, f"起始页 {p0} 未紧接上一附录末页 {prev}"))
            prev = p1
            page = d[p0 - 1]
            h = page.rect.height
            blocks = sorted((b for b in page.get_text("blocks") if b[4].strip()),
                            key=lambda b: (b[1], b[0]))
            want = norm(titles.get(tag))
            hit = next((b for b in blocks if want and want in norm(b[4])), None)
            if hit is None:
                bad.append((tag, f"第 {p0} 页找不到标题「{titles.get(tag)}」"))
                continue
            # 页眉（抬头/题名/页眉块）不算正文：相邻页同一位置重复出现的文字即页眉
            run = set()
            for q in (p0 - 2, p0):
                if 0 <= q < d.page_count:
                    run |= {(norm(b[4]), round(b[1])) for b in d[q].get_text("blocks")}
            above = [b for b in blocks if b[3] <= hit[1] + 0.5
                     and (norm(b[4]), round(b[1])) not in run]
            if above or hit[1] > h * 0.45:
                bad.append((tag, f"第 {p0} 页标题上方还有 {len(above)} 段文字"
                                 f"（正文与附录同页？）"))
    return bad
