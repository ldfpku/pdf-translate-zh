# -*- coding: utf-8 -*-
"""待译键的清理。叠印路线的词表键必须先过这一层，否则词表白写。

四次实证下来的结论：**自动提取出的「待译单元」本身不可信**，
每次失效方式都不同。前三种已在别处解决（`find_tables` 的三类失效 →
改用线框几何，见 dwg_bom / hybrid_overlay）；本模块收拾剩下的三类：

  1. 叠印重复词 —— `CATCH CATCH`／`END END`／`AVG. RACES RACES`。
     原版把同一标注叠印两份（SKILL 避坑 ⑳），两份副本相距 >3pt 时
     位置去重漏过，按词装桶就成了重复串。
  2. 目录点导线断行 —— `ASSEMBLY SUMMARY .....` ／ `...... ASSY` 各成一行。
  3. 跨行截断 —— `(If “ ”>.125 in. (3.18 mm), check`、`FACE OFF “`、
     `(measured on`。表格区内的多行说明格走行级，未被段级的合并照顾到。
"""
import re

_DOTS = re.compile(r"\.{3,}\s*$")
_DOTS_HEAD = re.compile(r"^\s*\.{3,}")
# 句末标记：以这些收尾视为完整句/完整标签
# 右括号／右引号**单独不算句末**：原先把 `)` 也当成结束标记，
# 于是 `… The Drive Shaft (Bit Box)` 这种以插入语收尾的行被当成已结束，
# 下一行拼不回来 —— 注意框里的一句话就被切成两条各自翻译，
# 读起来断在半句（目测清单「不必严格按英文原文对齐，造成译文阅读断裂」）。
# 只有句末点号类字符（可后跟一个右括号／引号）才算结束。
_ENDED = re.compile(r"[.:;?!][”\")\]]?\s*$|^\S{1,3}$")
# 但**短串**以右括号／引号收尾的，是堆叠的**表头格**而不是折行：
# `(mm)` 上方是 `Kelly Mandrel`、`(inch)` 上方是 `Size ID`。
# 把它们拼起来会凭空造出 `(mm) Kelly Mandrel` 这类键（实测 规范 G/规范 F 共 10 条）。
_PAREN_END = re.compile(r"[)\]”\"]\s*$")


def collapse_dup(text):
    """折叠相邻重复的词序列：[A,A]→[A]、[A,B,B]→[A,B]、[A,B,A,B]→[A,B]。

    只折叠**相邻且完全相同**的序列，故不会误伤 `INNER OUTER THRUST`
    或同格内合法重复（如「扭矩套 扭矩套」若真是两处标注，位置去重已先处理）。
    """
    w = text.split()
    if len(w) < 2:
        return text
    n = len(w)
    for k in range(n // 2, 0, -1):          # 先试长序列，避免过度折叠
        i = 0
        out = []
        changed = False
        while i < n:
            if i + 2 * k <= n and w[i:i + k] == w[i + k:i + 2 * k]:
                out += w[i:i + k]
                i += 2 * k
                changed = True
            else:
                out.append(w[i])
                i += 1
        if changed:
            return collapse_dup(" ".join(out))
    return text


def join_dot_leaders(items):
    """把目录点导线断成两行的条目拼回一条。

    items: [(rect, text, size), ...]（同一页，按阅读顺序）
    判据：本行以 3 个以上点结尾，且下一行以 3 个以上点开头。
    """
    out = []
    i = 0
    while i < len(items):
        r, t, s = items[i]
        if i + 1 < len(items) and _DOTS.search(t) and _DOTS_HEAD.match(items[i + 1][1]):
            r2, t2, s2 = items[i + 1]
            merged = _DOTS.sub(" ", t).strip() + " " + _DOTS_HEAD.sub("", t2).strip()
            out.append((r | r2, " ".join(merged.split()), s))
            i += 2
            continue
        out.append((r, t, s))
        i += 1
    return out


def join_wrapped(items, max_gap=3.0, xtol=6.0):
    """把同一单元格内被框宽截断的多行说明拼回一条。

    判据三条同时成立：上一行**不以句末标记收尾**、两行左界基本对齐
    （|Δx0| ≤ xtol）、纵向紧邻（间距 ≤ max_gap）。
    """
    items = sorted(items, key=lambda it: (round(it[0].y0, 1), it[0].x0))
    out = []
    for r, t, s in items:
        if out:
            pr, pt, ps = out[-1]
            _end = bool(_ENDED.search(pt))
            if not _end and _PAREN_END.search(pt) and len(pt) < 40:
                _end = True          # 短括号串 = 表头格，不拼
            if (not _end and abs(pr.x0 - r.x0) <= xtol
                    and 0 <= r.y0 - pr.y1 <= max_gap):
                out[-1] = (pr | r, " ".join((pt + " " + t).split()), ps)
                continue
        out.append((r, t, s))
    return out


# Symbol 字体的希腊字母被编码到**造字区**（PUA, U+F020~U+F0FF），
# 提取出来就是  /  这样的码位。实测 手册 D 用
# α/β 作台肩间隙的测量标记（与 手册 C 的 X/Y 同义），若原样写入：
#   · 键对不上（字典里写的是普通 α 或引号，永远 miss）；
#   · 即便命中，微软雅黑没有 PUA 字形，渲染成方框（check_glyphs 会报）。
# 故一律先归一到真 Unicode。映射依 Symbol 字体的标准编码表（偏移 0xF000）。
_PUA = {
    "": " ", "": "α", "": "β",
    "": "γ", "": "δ", "": "ε",
    "": "θ", "": "λ", "": "μ",
    "": "π", "": "σ", "": "τ",
    "": "φ", "": "ω", "": "Δ",
    "": "Σ", "": "Ω", "": "°",
    "": "±", "": "×", "": "÷",
    "": "≤", "": "≥", "": "≠",
    # Symbol 字体的**项目符号**与破折号 —— 实测 规范 F 全书用 U+F0B7
    # 作项目符号，未归一时该串首字符不是空白，`split()` 清不掉，
    # 于是同一段文字产生两个键（带符号／不带符号），词表必漏一个。
    "": "•", "": "▪", "": "✓",
    "": "→", "": "←", "": "→",
}


# Wingdings 的项目符号另有一族（实测 某客户讲义：U+F0A7 小实心方、
# U+F06E 实心方、U+F075 菱形）。Symbol 表里没有它们，不补就归一不掉。
_PUA.update({"": "▪", "": "▪", "": "◆",
             "": "▶", "": "•"})

PUA_LEFT = set()          # 归一后仍残留的造字区码位，交付前必须为空


def norm_pua(text, report=True):
    """把 Symbol／Wingdings 造字区码位归一为真 Unicode 字符。

    ⚠ **归一必须做在「导键与装配共用的那个 norm()」里**，而不是只在
    keyclean 内部（避坑 83）。实测一份文档的 `3° per 100'` 里度符是
    U+F0B0：内容层自己写 `" ".join(s.split())` 当归一函数，词表里写普通
    `°` 就永远 miss，而未命中报告只会说「有一条没命中」，不会说为什么。
    残留码位记进 `PUA_LEFT` 由闸门报出来 —— **不许静默**，因为雅黑没有
    PUA 字形，漏网的一律渲染成方框。
    """
    if not text:
        return text
    out = "".join(_PUA.get(c, c) for c in text)
    if report:
        for c in out:
            if 0xE000 <= ord(c) <= 0xF8FF:
                PUA_LEFT.add(c)
    return out


def norm_leaders(text):
    """把 3 个以上连续点的导线归一为单个「…」，使键稳定可查。

    目录／维护记录里的点导线长度随标题长短而变（同一条目在不同页
    点数都不同），若原样入键则同一标题会产生多个键。
    另：本页若把点导线单独排成一个文本项（实测 马达手册 目录页即如此），
    该项全为点与空格，会被 KEEP 规则直接判为「保留不译」，无须在此处理。
    """
    t = re.sub(r"\.{3,}", " … ", text)
    return " ".join(t.split())


def clean(items, dot_leaders=True, wrapped=True, leaders=True):
    """一次过：拼点导线 → 拼截断行 → 归一导线 → 折叠重复词。"""
    if dot_leaders:
        items = join_dot_leaders(items)
    if wrapped:
        items = join_wrapped(items)
    out = []
    for r, t, s in items:
        t = norm_pua(t)
        if leaders:
            t = norm_leaders(t)
        out.append((r, collapse_dup(t), s))
    return out
