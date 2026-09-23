# -*- coding: utf-8 -*-
"""避头尾的第二处补丁：**连续**的行首禁则字符要一起挂到上一行。

ReportLab 的换行只处理「溢出的那一个字符不能起行 ⇒ 让它悬挂」，
源码注释写得很明白：`We won't do two or more though`。
于是 `），` / `）。` 这种连着两个禁则字符的序列，第一个挂在上一行、
**第二个就成了下一行的行首** —— 实测附录表格里排出
「，同图字号统一…」「。范围号统一…」四处，而 `check_line_start`
报得出来、折行时却拦不住（避坑 92 的同族：那一条修的是字符表，
这一条修的是算法）。

⚠ 要补的是**两个**入口，缺一不可：
  · `textsplit.dumbSplit`   —— 单 fragment 段落（纯文本，无内联标记）走这条；
  · `paragraph.cjkFragSplit` —— 多 fragment 段落（含 <b>/<br/> 等）走这条。
只补后者时，附录里的纯文本单元格照样断错（本项目实测）。
"""
from reportlab.lib import textsplit as _ts
from reportlab.platypus import paragraph as _pp
from reportlab.platypus.paragraph import ParaLines

_MAXHANG = 2
_DONE = False

# ▼ 第三处补丁：不在**西文词内部**断行。
#
# ReportLab 本来就想避开：断点落在 <0x3000 的字符上时，它从断点往回找空格或
# 汉字。但回溯**只允许到行长的一半**（`limitCheck = (lineStartPos+i)>>1`），
# 而窄栏里「（第 2 代 RotaMaster）」的那个空格恰好在前半段 ——
# 于是回溯放弃、原地硬断，排出「（第 2 代 RotaMas / ter）」。
#
# 表格列宽的原子下限（`zhlib.ATOM_RE` + `fit_cols`）保证**这个词单独一行**
# 放得下，但保证不了「前面还压着几个汉字时不被劈开」——那是断行算法的事。
# ⇒ 断点若落在西文词中间，回溯到词首（除非整行就这一个词，那时只能硬断）。
_WORDCH = frozenset("abcdefghijklmnopqrstuvwxyz"
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def _hangable(ch, nostart):
    return ch in nostart and ch.strip()


# ▼ 第四处补丁：**行尾禁则**。ReportLab 只查行首表，从不查 ALL_CANNOT_END；
# 补丁一把断点回溯到西文词首后，词前的「（」「“」就被留在上一行行尾 ——
# 实测「……（ / Bearing Assembly）」。断点前一个字符不能收行时，把它（至多 2 个）
# 一起推到下一行。
_MAXPUSH = 2


def _push_back(get, i, lo, noend):
    k = 0
    while k < _MAXPUSH and i - 1 > lo + 1 and get(i - 1) in noend and get(i - 1).strip():
        i -= 1
        k += 1
    return i


def _word_start(get, i, lo, n):
    """断点 i 落在西文词内时，返回该词词首；否则原样返回 i。

    `i == n` 表示断在串尾 —— 后面没有字符，谈不上「词被劈开」，直接返回。
    """
    if i <= lo + 1 or i >= n:
        return i
    if get(i) not in _WORDCH or get(i - 1) not in _WORDCH:
        return i
    j = i - 1
    while j > lo + 1 and get(j - 1) in _WORDCH:
        j -= 1
    return j if j > lo + 1 else i


def _patch_dumbsplit():
    _orig = _ts.dumbSplit

    def dumbSplit(word, widths, maxWidths):
        if not isinstance(maxWidths, (list, tuple)):
            maxWidths = [maxWidths]
        NOSTART = _ts.ALL_CANNOT_START
        FUZZ = _ts._FUZZ
        from unicodedata import category
        lines = []
        i = widthUsed = lineStartPos = 0
        maxWidth = maxWidths[0]
        nW = len(word)
        while i < nW:
            w = widths[i]
            c = word[i]
            widthUsed += w
            i += 1
            if widthUsed > maxWidth + FUZZ and widthUsed > 0:
                extraSpace = maxWidth - widthUsed
                if ord(c) < 0x3000:
                    limitCheck = (lineStartPos + i) >> 1
                    for j in range(i - 1, limitCheck, -1):
                        cj = word[j]
                        if category(cj) == "Zs" or ord(cj) >= 0x3000:
                            k = j + 1
                            if k < i:
                                j = k + 1
                                extraSpace += sum(widths[j:i])
                                w = widths[k]
                                c = word[k]
                                i = j
                                break
                if c not in NOSTART and i > lineStartPos + 1:
                    i -= 1
                    extraSpace += w
                # ▼ 本补丁一：断点落在西文词内就回溯到词首
                j = _word_start(lambda k: word[k], i, lineStartPos, nW)
                if j < i:
                    extraSpace += sum(widths[j:i])
                    i = j
                # ▼ 本补丁三：行尾不留起首类标点（「（」「“」…）
                j = _push_back(lambda k: word[k], i, lineStartPos,
                               getattr(_ts, "ALL_CANNOT_END", ""))
                if j < i:
                    extraSpace += sum(widths[j:i])
                    i = j
                # ▼ 本补丁二：紧随其后、同样不能起行的字符一并挂上来
                hung = 0
                while hung < _MAXHANG and i < nW and _hangable(word[i], NOSTART):
                    extraSpace -= widths[i]
                    i += 1
                    hung += 1
                lines.append([extraSpace, word[lineStartPos:i].strip()])
                try:
                    maxWidth = maxWidths[len(lines)]
                except IndexError:
                    maxWidth = maxWidths[-1]
                lineStartPos = i
                widthUsed = 0
        if widthUsed > 0:
            lines.append([maxWidth - widthUsed, word[lineStartPos:]])
        return lines

    _ts.dumbSplit = dumbSplit
    return _orig


def _patch_cjkfrag():
    _orig = _pp.cjkFragSplit

    def cjkFragSplit(frags, maxWidths, calcBounds, encoding="utf8"):
        from unicodedata import category
        U = []
        for f in frags:
            text = f.text
            if isinstance(text, bytes):
                text = text.decode(encoding)
            if text:
                U.extend([_pp.cjkU(t, f, encoding) for t in text])
            else:
                U.append(_pp.cjkU(text, f, encoding))
        NOSTART = _pp.ALL_CANNOT_START
        lines = []
        i = widthUsed = lineStartPos = 0
        maxWidth = maxWidths[0]
        nU = len(U)
        while i < nU:
            u = U[i]
            i += 1
            w = u.width
            if hasattr(w, "normalizedValue"):
                w._normalizer = maxWidth
                w = w.normalizedValue(maxWidth)
            widthUsed += w
            lineBreak = hasattr(u.frag, "lineBreak")
            endLine = (widthUsed > maxWidth + _pp._FUZZ and widthUsed > 0) or lineBreak
            if endLine:
                extraSpace = maxWidth - widthUsed
                if not lineBreak:
                    if ord(u) < 0x3000:
                        limitCheck = (lineStartPos + i) >> 1
                        for j in range(i - 1, limitCheck, -1):
                            uj = U[j]
                            if uj and category(uj) == "Zs" or ord(uj) >= 0x3000:
                                k = j + 1
                                if k < i:
                                    j = k + 1
                                    extraSpace += sum(U[ii].width
                                                      for ii in range(j, i))
                                    w = U[k].width
                                    u = U[k]
                                    i = j
                                    break
                    if u not in NOSTART and i > lineStartPos + 1:
                        i -= 1
                        extraSpace += w
                    j = _word_start(lambda k: str(U[k]), i, lineStartPos, nU)
                    if j < i:
                        extraSpace += sum(U[ii].width for ii in range(j, i))
                        i = j
                    j = _push_back(lambda k: str(U[k]), i, lineStartPos,
                                   getattr(_ts, "ALL_CANNOT_END", ""))
                    if j < i:
                        extraSpace += sum(U[ii].width for ii in range(j, i))
                        i = j
                    hung = 0
                    while (hung < _MAXHANG and i < nU
                           and _hangable(str(U[i]), NOSTART)):
                        extraSpace -= U[i].width
                        i += 1
                        hung += 1
                lines.append(_pp.makeCJKParaLine(U[lineStartPos:i], maxWidth,
                                                 widthUsed, extraSpace,
                                                 lineBreak, calcBounds))
                try:
                    maxWidth = maxWidths[len(lines)]
                except IndexError:
                    maxWidth = maxWidths[-1]
                lineStartPos = i
                widthUsed = 0
        if widthUsed > 0:
            lines.append(_pp.makeCJKParaLine(U[lineStartPos:], maxWidth,
                                             widthUsed, maxWidth - widthUsed,
                                             False, calcBounds))
        return ParaLines(kind=1, lines=lines)

    _pp.cjkFragSplit = cjkFragSplit
    return _orig


def install():
    global _DONE
    if _DONE:
        return
    _patch_dumbsplit()
    _patch_cjkfrag()
    _DONE = True


install()
