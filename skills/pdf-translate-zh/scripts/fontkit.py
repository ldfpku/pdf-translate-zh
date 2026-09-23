# -*- coding: utf-8 -*-
"""跨平台字体解析 —— 全部脚本取字体的**唯一入口**。

为什么要有它
    旧版各脚本各自写死 `C:\\Windows\\Fonts\\msyh.ttc`，换到 macOS / Linux
    或 Windows 装在 D 盘的机器上，ReportLab 路线直接 KeyError('ZH')，
    叠印路线则静默退化成西文字体 —— 成品满页豆腐块。

解析顺序（先命中者胜）
    1. 环境变量   PDF_ZH_FONT / PDF_ZH_FONT_BOLD / PDF_ZH_FONT_HEI /
                  PDF_ZH_FONT_SONG / PDF_ZH_FONT_LATIN_BOLD / PDF_ZH_FONT_MONO /
                  PDF_ZH_FONT_MONO_BOLD   —— 值为字体文件路径（可写 `路径#序号` 指定 TTC 子字体）
    2. 技能目录下 `fonts/`   —— 把同一套字体文件放进去，各机器产出逐字节一致
    3. 系统字体目录（Windows %WINDIR%\\Fonts 与用户字体目录 / macOS / Linux）
    4. PyMuPDF 内置 Droid Sans Fallback（中文角色的兜底，零依赖、永远可用）

由本模块统一处理的约束（都是实测踩到的，避坑 113、117）
    · ReportLab 只认 TrueType 轮廓（glyf），Noto/思源 的 CFF 版会抛
      "postscript outlines are not supported" → `reportlab=True` 时自动跳过 CFF；
    · PyMuPDF 的 insert_font 不能选 TTC 子字体（总取第 0 个；Noto CJK 的第 0 个
      是日文字形）→ TTC 需要非 0 子字体时，抽出单字体文件缓存后再返回路径；
    · PyMuPDF + CFF 字体：`subset_fonts()` 报 "Index bounds" 静默失败（成品 16 MB+），
      且 Noto CJK 的 cmap 让 `-`/空格与 U+2011/U+00A0 共用字形，文本层里图号
      「675‑200‑011」变成不可检索的非断连字符 → 叠印用字体**优先 TrueType、
      且无 ASCII 别名**，CFF 只作最后手段；
    · Linux 常见只有 Noto CJK（CFF）：`python doctor.py --fonts` 一次性转成
      TrueType（每个约 1 分钟，去掉别名映射）存进缓存，两条路线从此都用它；
    · macOS 的苹方也是 CFF，现成 TrueType 只剩华文黑体 —— 它的 ° ′ ″ · 是全角字宽
      （「90°」排成「90 °」）、Medium 与 Light 几乎拉不开粗细 → 同样首次运行时把
      苹方 SC 常规/中粗转成 TrueType（每个约 15 秒），缺的 ◦ 由 ○ 缩排补出。

用法
    import fontkit
    fontkit.find("zh")                  # 叠印（PyMuPDF）用
    fontkit.find("zh-bold", reportlab=True)
    fontkit.pil("mono", 14)             # PIL ImageFont
    python fontkit.py                   # 打印本机解析结果
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

ROLES = ("zh", "zh-bold", "hei", "song", "latin-bold", "mono", "mono-bold")

_ENV = {
    "zh": "PDF_ZH_FONT",
    "zh-bold": "PDF_ZH_FONT_BOLD",
    "hei": "PDF_ZH_FONT_HEI",
    "song": "PDF_ZH_FONT_SONG",
    "latin-bold": "PDF_ZH_FONT_LATIN_BOLD",
    "mono": "PDF_ZH_FONT_MONO",
    "mono-bold": "PDF_ZH_FONT_MONO_BOLD",
}

# 文件名候选（不分大小写），按偏好排序。各平台的常见中文字体都列上，
# 不存在的自然跳过。雅黑排第一：与历史交付稿的度量一致。
_CANDIDATES = {
    "zh": ["msyh.ttc", "msyh.ttf", "NotoSansCJKsc-Regular-tt.ttf", "Deng.ttf", "simhei.ttf",
           "PingFangSC-Regular-tt.ttf", "PingFang.ttc", "STHeiti Light.ttc", "Hiragino Sans GB.ttc",
           "NotoSansCJKsc-Regular.otf", "NotoSansSC-Regular.otf",
           "NotoSansSC-Regular.ttf", "SourceHanSansSC-Regular.otf",
           "SourceHanSansCN-Regular.otf", "NotoSansCJK-Regular.ttc",
           "wqy-microhei.ttc", "wqy-zenhei.ttc", "DroidSansFallbackFull.ttf",
           "Arial Unicode.ttf"],
    "zh-bold": ["msyhbd.ttc", "msyhbd.ttf", "NotoSansCJKsc-Bold-tt.ttf", "Dengb.ttf", "simhei.ttf",
                "PingFangSC-Semibold-tt.ttf", "PingFang.ttc", "STHeiti Medium.ttc",
                "NotoSansCJKsc-Bold.otf", "NotoSansSC-Bold.otf",
                "NotoSansSC-Bold.ttf", "SourceHanSansSC-Bold.otf",
                "SourceHanSansCN-Bold.otf", "NotoSansCJK-Bold.ttc",
                "wqy-microhei.ttc", "wqy-zenhei.ttc"],
    "hei": ["simhei.ttf", "msyh.ttc", "STHeiti Light.ttc",
            "NotoSansCJKsc-Regular.otf", "NotoSansCJK-Regular.ttc",
            "wqy-zenhei.ttc"],
    "song": ["simsun.ttc", "Songti.ttc", "STSong.ttf",
             "NotoSerifCJKsc-Regular.otf", "NotoSerifCJK-Regular.ttc",
             "SourceHanSerifSC-Regular.otf", "uming.ttc"],
    "latin-bold": ["arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf",
                   "Arimo-Bold.ttf", "DejaVuSans-Bold.ttf", "FreeSansBold.ttf"],
    "mono": ["consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf",
             "LiberationMono-Regular.ttf", "Courier New.ttf", "cour.ttf"],
    "mono-bold": ["consolab.ttf", "Menlo.ttc", "DejaVuSansMono-Bold.ttf",
                  "LiberationMono-Bold.ttf", "Courier New Bold.ttf", "courbd.ttf"],
}
_ZH_ROLES = {"zh", "zh-bold", "hei", "song"}

# 工程文档里高频出现、且各中文字体覆盖参差的符号。候选按偏好排序，但**缺这些
# 字形的会被排到后面**：实测 Linux 的文泉驿正黑缺 `•`，项目符号整列变空白，
# 而缺字闸门对 ReportLab 的 fallback 并不报。
ESSENTIAL = "•◦□±°×″′≤≥—–…①→·µ"
_BOLD_ROLES = {"zh-bold", "latin-bold", "mono-bold"}


# ---------------------------------------------------------------- 目录
def cache_dir():
    d = os.environ.get("PDF_ZH_CACHE")
    if not d:
        if sys.platform.startswith("win"):
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "pdf-translate-zh", "cache")
        else:
            base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
            d = os.path.join(base, "pdf-translate-zh")
    os.makedirs(os.path.join(d, "fonts"), exist_ok=True)
    return d


def font_dirs():
    """按优先级：技能 fonts/ → 缓存里转换好的字体 → 系统目录。"""
    dirs = [os.path.join(SKILL_ROOT, "fonts"), os.path.join(cache_dir(), "fonts", "converted")]
    if sys.platform.startswith("win"):
        win = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
        dirs.append(os.path.join(win, "Fonts"))
        la = os.environ.get("LOCALAPPDATA")
        if la:
            dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        dirs += ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
                 "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
        dirs += glob.glob("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData")
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts",
                 os.path.expanduser("~/.local/share/fonts"),
                 os.path.expanduser("~/.fonts")]
    return [d for d in dirs if os.path.isdir(d)]


_INDEX = None


def _index():
    """文件名(小写) → 路径。只建一次；Linux 字体目录是多层的，要递归。"""
    global _INDEX
    if _INDEX is None:
        _INDEX = {}
        for d in font_dirs():
            for root, _dirs, files in os.walk(d):
                for f in files:
                    _INDEX.setdefault(f.lower(), os.path.join(root, f))
    return _INDEX


# ---------------------------------------------------------------- 字体文件检查
def _faces(path):
    """[(序号, 家族名, 子族名, 是否 glyf)]；fontTools 缺失时返回 None。"""
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except Exception:
        return None
    try:
        if path.lower().endswith((".ttc", ".otc")):
            fonts = TTCollection(path, lazy=True).fonts
        else:
            fonts = [TTFont(path, lazy=True)]
    except Exception:
        return []
    out = []
    for i, f in enumerate(fonts):
        try:
            nm = f["name"]
            fam = str(nm.getDebugName(16) or nm.getDebugName(1) or "")
            sub = str(nm.getDebugName(17) or nm.getDebugName(2) or "")
        except Exception:
            fam, sub = "", ""
        out.append((i, fam, sub, "glyf" in f))
    return out


def _pick_face(faces, role):
    """TTC 里选子字体：简体优先；粗体角色优先 Bold/Semibold/Medium。"""
    def score(fc):
        _, fam, sub, _g = fc
        s = 0
        txt = (fam + " " + sub).lower()
        if role in _ZH_ROLES and any(k in txt for k in (" sc", "gb", "simplified", "cn")):
            s += 4
        if any(k in txt for k in (" jp", " kr", " tc", " hk", "mono")):
            s -= 2
        boldish = any(k in txt for k in ("bold", "semibold", "medium", "heavy", "black"))
        if role in _BOLD_ROLES:
            s += (3 if "bold" in txt else 2) if boldish else 0
        else:
            s -= 2 if boldish else 0
            s += 1 if any(k in txt for k in ("regular", "normal", "book")) else 0
        return s
    return max(faces, key=score) if faces else None


def _extract_face(path, idx):
    """把 TTC 的第 idx 个子字体抽成单文件（缓存）；失败返回 None。"""
    out = os.path.join(cache_dir(), "fonts",
                       "%s__%d%s" % (os.path.splitext(os.path.basename(path))[0], idx,
                                     ".ttf"))
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(path):
        return out
    try:
        from fontTools.ttLib import TTCollection
        TTCollection(path).fonts[idx].save(out)
        return out
    except Exception:
        return None


def _quirks(path):
    """(是否 CFF 轮廓, 是否有别名映射) —— 叠印（PyMuPDF）路线的两类隐患。

    别名 = 非首选码位（兼容汉字、部首、U+2011/U+00A0…）与首选码位共用字形。"""
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(path, lazy=True, fontNumber=0)
        cmap = f.getBestCmap()
        good = {g for k, g in cmap.items() if _preferred(k)}
        alias = any(g in good and not _preferred(k) for k, g in cmap.items())
        return ("CFF " in f or "CFF2" in f), alias
    except Exception:
        return False, False


def _missing(path):
    """ESSENTIAL 里该字体缺的字形数；读不了 cmap 时按 0 处理。"""
    try:
        from fontTools.ttLib import TTFont
        cmap = TTFont(path, lazy=True, fontNumber=0).getBestCmap()
        return sum(1 for ch in ESSENTIAL if ord(ch) not in cmap)
    except Exception:
        return 0


def _dealiased_copy(path):
    """单字体文件 → 去掉别名映射的副本（缓存，源文件更新则重做）。失败返回 None。"""
    base = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(cache_dir(), "fonts", "dealiased", base + ".ttf")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(path):
        return out
    try:
        from fontTools.ttLib import TTFont
        os.makedirs(os.path.dirname(out), exist_ok=True)
        f = TTFont(path, fontNumber=0)
        _dealias_cmap(f)
        f.save(out + ".part")
        f.close()
        os.replace(out + ".part", out)
        return out
    except Exception:
        return None


def _builtin_cjk():
    """PyMuPDF 内置的 Droid Sans Fallback（TrueType，ReportLab 也能用）。"""
    out = os.path.join(cache_dir(), "fonts", "DroidSansFallback-pymupdf.ttf")
    if not os.path.exists(out):
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        with open(out, "wb") as fh:
            fh.write(fitz.Font("cjk").buffer)
    return out


# ---------------------------------------------------------------- 解析
_CACHE = {}
_SOURCE = {}


def _resolve_file(path, role, reportlab):
    """路径（可带 #序号）→ 可直接用的单字体文件；不合格返回 None。"""
    idx = None
    if "#" in path and path.rsplit("#", 1)[1].isdigit():
        path, idx = path.rsplit("#", 1)
        idx = int(idx)
    if not os.path.isfile(path):
        return None
    faces = _faces(path)
    if faces is None:                      # 无 fontTools：只能按扩展名粗判
        if reportlab and path.lower().endswith(".otf"):
            return None
        return path
    if not faces:
        return None
    if idx is None:
        fc = _pick_face(faces, role)
    else:
        fc = next((f for f in faces if f[0] == idx), None)
    if fc is None:
        return None
    if reportlab and not fc[3]:            # CFF 轮廓，ReportLab 不支持
        return None
    if fc[0] == 0:
        return path
    return _extract_face(path, fc[0])


def find(role="zh", reportlab=False, required=True):
    """返回该角色可用的单字体文件路径。"""
    if role not in _CANDIDATES:
        raise KeyError("未知字体角色 %r，可选 %s" % (role, ROLES))
    key = (role, reportlab)
    if key in _CACHE:
        return _CACHE[key]
    hit, src = None, None
    env = os.environ.get(_ENV[role])
    if env:
        hit = _resolve_file(env, role, reportlab)
        src = "环境变量 %s" % _ENV[role]
        if hit is None:
            print("[fontkit] %s=%s 不可用（不存在或为 CFF 且用于 ReportLab），继续自动查找"
                  % (_ENV[role], env), file=sys.stderr)
    if hit is None:
        idx = _index()
        best = None                          # (缺字数, 次序, 路径, 来源)
        for order, name in enumerate(_CANDIDATES[role]):
            p = idx.get(name.lower())
            if not p:
                continue
            q = _resolve_file(p, role, reportlab)
            if not q:
                continue
            miss = _missing(q) if role in _ZH_ROLES else 0
            if role in _ZH_ROLES and not reportlab:
                cff, _alias = _quirks(q)          # 别名可自动去除（见下），CFF 不行
                miss += 5 if cff else 0
            from_skill = p.startswith(os.path.join(SKILL_ROOT, "fonts"))
            conv = os.sep + "converted" + os.sep in p
            cand = (0 if from_skill else miss, order, q,
                    "技能 fonts/" if from_skill else ("缓存（CFF→TrueType 转换）" if conv else "系统字体"))
            if best is None or cand[:2] < best[:2]:
                best = cand
            if cand[0] == 0:                 # 首个全覆盖者即取，不必再比
                break
        if best:
            hit, src = best[2], best[3]
            if best[0]:
                src += ("（有缺陷：缺常用符号或为 CFF 字体；本机现成字体里最好的，" +
                        ("`doctor.py --fonts` 可改善）" if sys.platform.startswith("linux")
                         else "可设 PDF_ZH_FONT / PDF_ZH_FONT_BOLD 指定更好的 TrueType 字体）"))
    if hit and role in _ZH_ROLES and not reportlab and _quirks(hit)[1]:
        # 叠印用字体有别名映射（「量」→U+F97E、`-`→U+2011）：做一份去别名副本（秒级、缓存）
        dq = _dealiased_copy(hit)
        if dq:
            hit, src = dq, (src or "") + "（已去别名）"
    if hit is None and role in _ZH_ROLES:
        if role == "zh-bold":                # 没有粗体中文就退回常规体，好过豆腐块
            hit = find("zh", reportlab, required=False)
            src = "退回常规体（未找到中文粗体）"
        if hit is None:
            hit, src = _builtin_cjk(), "PyMuPDF 内置 Droid Sans Fallback"
    if hit is None and role == "mono-bold":
        hit, src = find("mono", reportlab, required=False), "退回等宽常规体"
    if hit is None and required and role not in ("latin-bold", "mono", "mono-bold"):
        raise FileNotFoundError("找不到字体角色 %s；请设置环境变量 %s 或把字体放进 %s"
                                % (role, _ENV[role], os.path.join(SKILL_ROOT, "fonts")))
    _CACHE[key], _SOURCE[key] = hit, src
    return hit


def _preferred(k):
    """写中文技术文档时真正会输入的码位。"""
    if 0x20 <= k <= 0x7E:                                   # ASCII
        return True
    if 0xA1 <= k <= 0xFF and k != 0xAD:                     # Latin-1（不含 NBSP/软连字符）
        return True
    if 0x2000 <= k <= 0x206F and k not in (0x2011, 0x2007, 0x202F, 0x2027):   # 通用标点（不含不换行变体、连字点）
        return True
    if (0x2100 <= k <= 0x23FF or 0x2460 <= k <= 0x27BF) and k not in (0x2219, 0x22C5):  # 符号/数学/箭头/带圈数字/几何（不含与 •· 同形的运算符）
        return True
    if 0x3000 <= k <= 0x303F or 0xFF01 <= k <= 0xFF5E:      # CJK 标点、全角
        return True
    return 0x3400 <= k <= 0x4DBF or 0x4E00 <= k <= 0x9FFF or 0x20000 <= k <= 0x2A6DF


def _dealias_cmap(font):
    """同一字形被多个码位共用时，删掉「不会被输入」的那些码位。

    PyMuPDF 反查字形 → Unicode 取到的是别名：`-` 变 U+2011、空格变 U+00A0、
    「量」变兼容汉字 U+F97E、「一」可能变康熙部首 U+2F00 —— 渲染毫无差别，
    文本层里却搜不到「675-200-011」「数量」（实测，避坑 117）。
    只删**非首选**码位（兼容汉字、部首、不换行变体、片假名中点…），且只在同一字形
    还留有首选码位时才删；两个首选码位共用字形（如 `•`/`·`）时都保留 —— 删了
    其中一个它就成了缺字形（实测过，不划算）。
    """
    for t in font["cmap"].tables:
        if not t.isUnicode():
            continue
        by_glyph = {}
        for k, g in t.cmap.items():
            by_glyph.setdefault(g, []).append(k)
        for g, ks in by_glyph.items():
            if len(ks) < 2 or not any(_preferred(k) for k in ks):
                continue
            for k in ks:
                if not _preferred(k):
                    del t.cmap[k]


def convert_to_truetype(src, dst, max_err=1.0):
    """CFF（.otf / Noto CJK）→ TrueType 轮廓，并去掉 ASCII 别名映射。约 1 分钟/个。"""
    from fontTools.ttLib import TTFont, newTable
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    font = TTFont(src)
    order = font.getGlyphOrder()
    gs = font.getGlyphSet()
    font["loca"] = newTable("loca")
    font["glyf"] = glyf = newTable("glyf")
    glyf.glyphOrder, glyf.glyphs = order, {}
    for name in order:
        pen = TTGlyphPen(gs)
        gs[name].draw(Cu2QuPen(pen, max_err, reverse_direction=True))
        glyf[name] = pen.glyph()
    font["head"].glyphDataFormat = 0
    for tag in ("CFF ", "CFF2", "VORG"):
        if tag in font:
            del font[tag]
    maxp = font["maxp"] = newTable("maxp")
    maxp.tableVersion = 0x00010000
    for a in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs",
              "maxInstructionDefs", "maxStackElements", "maxSizeOfInstructions",
              "maxComponentElements"):
        setattr(maxp, a, 0)
    maxp.maxZones = 1
    font["post"].formatType = 3.0          # 6 万余字形放不进 format 2 的名表
    _synth_white_bullet(font)
    _dealias_cmap(font)
    font.sfntVersion = "\x00\x01\x00\x00"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    font.save(tmp)
    os.replace(tmp, dst)
    return dst


def _synth_white_bullet(font):
    """补 U+25E6 ◦（二级项目符号，ESSENTIAL 之一）：把 ○ 缩到 • 的大小、落在 • 的位置。

    苹方缺这个字形；不补的话缺字排序会把它排到全角符号的华文黑体后面。
    只在已转成 glyf 轮廓的字体上调用。"""
    cmap = font.getBestCmap()
    if 0x25E6 in cmap or 0x25CB not in cmap or 0x2022 not in cmap:
        return
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    glyf = font["glyf"]
    dot, ring = glyf[cmap[0x2022]], glyf[cmap[0x25CB]]
    dot.recalcBounds(glyf)
    ring.recalcBounds(glyf)
    if not dot.numberOfContours or not ring.numberOfContours or ring.xMax <= ring.xMin:
        return
    s = (dot.xMax - dot.xMin) / (ring.xMax - ring.xMin)
    dx = (dot.xMin + dot.xMax) / 2 - s * (ring.xMin + ring.xMax) / 2
    dy = (dot.yMin + dot.yMax) / 2 - s * (ring.yMin + ring.yMax) / 2
    pen = TTGlyphPen(None)
    ring.draw(TransformPen(pen, (s, 0, 0, s, dx, dy)), glyf)
    g = pen.glyph()
    g.recalcBounds(glyf)
    name = "uni25E6.synth"
    order = font.getGlyphOrder()
    if name not in order:
        order.append(name)
        font.setGlyphOrder(order)
    glyf.glyphOrder = order
    glyf.glyphs[name] = g
    font["hmtx"][name] = (font["hmtx"][cmap[0x2022]][0], g.xMin)
    if "vmtx" in font:
        font["vmtx"][name] = font["vmtx"][cmap[0x2022]]
    for tag in ("hdmx", "LTSH"):               # 逐字形的可选表，长度须与字形数一致，删掉最省事
        if tag in font:
            del font[tag]
    for t in font["cmap"].tables:
        if t.isUnicode() and 0x2022 in t.cmap:
            t.cmap[0x25E6] = name


def convert_system_cjk(verbose=True):
    """找本机的 CFF 中文字体简体常规+粗体，转成 TrueType 存进缓存。

    Linux / Windows：Noto/思源 CJK；macOS：苹方 SC（Regular + Semibold，子字体由
    `_pick_face` 选）。返回 [(角色, 目标路径, 状态)]。已转换过的跳过；转换后清空解析缓存。
    """
    global _INDEX
    out = []
    if sys.platform == "darwin":
        targets = {"zh": "PingFangSC-Regular-tt.ttf", "zh-bold": "PingFangSC-Semibold-tt.ttf"}
        sources = {"zh": ["PingFang.ttc"], "zh-bold": ["PingFang.ttc"]}
    else:
        targets = {"zh": "NotoSansCJKsc-Regular-tt.ttf", "zh-bold": "NotoSansCJKsc-Bold-tt.ttf"}
        sources = {"zh": ["NotoSansCJKsc-Regular.otf", "NotoSansSC-Regular.otf",
                          "SourceHanSansSC-Regular.otf", "NotoSansCJK-Regular.ttc"],
                   "zh-bold": ["NotoSansCJKsc-Bold.otf", "NotoSansSC-Bold.otf",
                               "SourceHanSansSC-Bold.otf", "NotoSansCJK-Bold.ttc"]}
    conv_dir = os.path.join(cache_dir(), "fonts", "converted")
    idx = _index()
    for role, tname in targets.items():
        dst = os.path.join(conv_dir, tname)
        if os.path.exists(dst):
            if _quirks(dst)[1]:              # 旧版转换留下的别名：只重做 cmap，不重转轮廓
                from fontTools.ttLib import TTFont
                f = TTFont(dst)
                _dealias_cmap(f)
                f.save(dst + ".part")
                f.close()
                os.replace(dst + ".part", dst)
                out.append((role, dst, "已更新别名映射"))
            else:
                out.append((role, dst, "已存在"))
            continue
        src = None
        for n in sources[role]:
            p = idx.get(n.lower())
            if p:
                src = _resolve_file(p, role, False)
                if src:
                    break
        if not src:
            out.append((role, None, "本机没有可转换的 CFF 中文字体"))
            continue
        if verbose:
            print(f"  转换 {os.path.basename(src)} → {tname}（约 {'15 秒' if sys.platform == 'darwin' else '1~2 分钟'}，勿中断）…",
                  flush=True)
        convert_to_truetype(src, dst)
        out.append((role, dst, "已转换"))
    _INDEX = None
    _CACHE.clear()
    _SOURCE.clear()
    return out


def save_subset(src, dst=None):
    """叠印成品的**最后一步**：字体子集化后存盘，返回 (字节数, 方式)。

    `insert_font` 逐页嵌入整个中文字体，不子集化文件涨几十倍（避坑 96）；而
    PyMuPDF 对 CFF 字体 `subset_fonts()` 会报 "Index bounds" 且**不抛异常**
    （只在 stderr 打一行），成品照样 16 MB —— 所以存完要量体积，没瘦就换
    `fallback=True` 再来一次。src 可以是路径或已打开的 Document。
    """
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    own = not hasattr(src, "save")
    doc = fitz.open(src) if own else src
    dst = dst or (src if own else doc.name)
    before = len(doc.tobytes(garbage=3, deflate=True))
    how = "subset_fonts()"
    try:
        doc.subset_fonts()
    except Exception:
        how = "失败"
    data = doc.tobytes(garbage=3, deflate=True)
    if len(data) > 0.5 * before and before > 2_000_000:
        try:
            doc = fitz.open(stream=doc.tobytes(), filetype="pdf")
            doc.subset_fonts(fallback=True)
            data = doc.tobytes(garbage=3, deflate=True)
            how = "subset_fonts(fallback=True)"
        except Exception:
            how += " / fallback 失败"
    if own:
        doc.close()
    with open(dst, "wb") as fh:
        fh.write(data)
    return len(data), how


def pil(role, size):
    """PIL ImageFont；拉丁/等宽角色缺字体时退回 PIL 内置字体而不是抛错。"""
    from PIL import ImageFont
    p = find(role, required=False)
    if p:
        try:
            return ImageFont.truetype(p, int(size))
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=int(size))
    except TypeError:                      # Pillow < 10.1
        return ImageFont.load_default()


def report():
    """{角色: (路径, 来源)} —— doctor.py 用。"""
    out = {}
    for r in ROLES:
        for rl in (False, True):
            try:
                p = find(r, reportlab=rl, required=False)
            except Exception as e:           # pragma: no cover
                p = "ERROR %s" % e
            out[(r, rl)] = (p, _SOURCE.get((r, rl)))
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.path.insert(0, HERE)
    import bootstrap                         # 挂上私有依赖目录：没有 fontTools 时解析结果与实际不符
    bootstrap.ensure(quiet=True)
    for (r, rl), (p, s) in report().items():
        print("%-10s %-9s %s   [%s]" % (r, "reportlab" if rl else "pymupdf", p, s))
