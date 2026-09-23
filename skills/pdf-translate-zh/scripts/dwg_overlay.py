# -*- coding: utf-8 -*-
"""整页叠印汉化：在原页上 redaction 英文、按原位写中文。

适用于 D 号工程图纸（图纸族 J）。这类图纸的主体是剖视图线框、剖面线、
尺寸线与件号气泡；若在 ReportLab 里重画，既费工又**不如原版忠实**。
故把 SKILL §3「图内中文回叠」放大到整页：
线框全部保持原始矢量不动，只把文字换掉。

三条不可省的约束
  · `apply_redactions` 必须带 `graphics=PDF_REDACT_LINE_ART_NONE` 与
    `images=PDF_REDACT_IMAGE_NONE` —— 否则会把与文字矩形相交的线框一并抹掉，
    表格线与尺寸线会出现缺口。
  · 中文比英文宽，须按原文字框宽度**自适配字号**（下限 4.2pt），
    否则相邻单元格必然压叠。
  · 叠印分两趟：先铺完所有白底，再统一写字（SKILL ⑮），
    否则后一条的底会盖掉前一条的字脚。
"""
import os
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

import fontkit

# 字体由 fontkit 跨平台解析（环境变量 → 技能 fonts/ → 系统 → 内置兜底）
ZH_FONT = fontkit.find("zh")
ZH_FONT_B = fontkit.find("zh-bold")


def _norm(s):
    return " ".join(str(s or "").split())


def block_align(rows, tol=2.5, rel=0.03):
    """一组行框的对齐方式：0 左 / 1 居中 / 2 右 / -1 判不出。

    判据只看**墨迹**（行 bbox），不看写入框 —— 写入框常被放宽到单元格
    边界，对齐信息全在墨迹里。

    这是「多行居中标题」与「多行两端对齐段落」的唯一可靠分界：
      · 居中标题：各行中线取齐，左右两端都不齐；
      · 两端对齐段落：左右两端都齐（中线自然也齐）—— 故居中判据要求
        中线离散**严格小于**左右离散，否则会把整段正文判成居中。

    容差**相对块宽**。写死几 pt 会因字号不同带来的字边距差把「明明居中」
    判成无定形（实测 手册 B 源封面标题块中线离散 2.6pt，绝对容差取 2.5
    就差 0.1pt 失手）。
    """
    if len(rows) < 2:
        return -1
    x0 = [r.x0 for r in rows]
    x1 = [r.x1 for r in rows]
    mid = [(r.x0 + r.x1) / 2.0 for r in rows]
    dl, dr, dm = max(x0) - min(x0), max(x1) - min(x1), max(mid) - min(mid)
    lim = max(tol, rel * (max(x1) - min(x0)))
    if dm <= lim and dm < dl and dm < dr:
        return 1
    if dl <= lim and dl <= dr:
        return 0
    if dr <= lim:
        return 2
    return -1


_FZFONT = None


def _width(text, size):
    """量中文串宽度 —— **必须用 `fitz.Font`，与 insert_textbox 同一套度量**。

    踩过两次：
    · `fitz.get_text_length` 只认 PDF 内置字体，对 insert_font 装进去的 msyh
      会抛「Font 'zh' is unsupported」；
    · 改用 reportlab 的 `pdfmetrics.stringWidth` 后度量「看着能放下」，
      但 insert_textbox 用自己的度量判定放不下、于是**一字不写且不报错**。
      实测该页 116 段里有 48 段（全是较长的字段名）就这样静默丢失 ——
      写入计数照报 116，页面上却只落了 68。
    两套度量必须同源，否则「能放下」的判断根本不作数。
    """
    global _FZFONT
    if _FZFONT is None:
        try:
            _FZFONT = fitz.Font(fontfile=ZH_FONT)
        except Exception:
            _FZFONT = False
    if _FZFONT:
        return _FZFONT.text_length(text, fontsize=size)
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in text) * size


class Overlay:
    """收集「原文矩形 → 中文」，最后一次性落到页面上。"""

    def __init__(self, page, font="zh", fontfile=ZH_FONT):
        self.page = page
        self.font, self.fontfile = font, fontfile
        self.items = []          # (rect, 中文, 字号上限, 对齐)

    def add(self, rect, text, size=None, align=1):
        self.items.append((fitz.Rect(rect), text, size, align))

    def _fit(self, text, rect, cap):
        """按框宽自适配字号。中文字宽≈字号，留 4% 余量。"""
        w = rect.width - 1.6
        n = max(len(text), 1)
        s = min(cap, rect.height * 0.86)
        # 单行估算：中文按 1.0em、ASCII 按 0.55em
        em = sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in text) or 1
        s = min(s, w / em * 0.96)
        return max(s, 4.2)

    def apply(self):
        pg = self.page
        if not self.items:
            return 0
        _rr = [rect + (-0.4, -0.4, 0.4, 0.4) for rect, _t, _s, _a in self.items]
        for r in _rr:
            pg.add_redact_annot(r)
        # 抹除会连带删掉**仅仅触碰**到框的邻行字形（如紧贴上一行的
        # 表面粗糙度值 `125`）—— 先快照，抹完补回。见 rescue_snapshot。
        _rs = rescue_snapshot(pg, _rr)
        # 线框与位图一律不动，只抹文字
        pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                            graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        rescue_restore(pg, _rs)
        pg.insert_font(fontname=self.font, fontfile=self.fontfile)
        n = 0
        for rect, text, cap, align in self.items:
            if not text:
                continue
            box = fitz.Rect(rect.x0 - 0.6, rect.y0 - 1.2,
                            rect.x1 + 0.6, rect.y1 + 1.6)
            # **先量后画，只画一次。**
            # 曾用「画一次，rc<0 再缩号画第二次」—— insert_textbox 在放不下时
            # 仍会把能放的部分画出来，第二次就叠在第一次上，
            # 表现为两个字重影成一个怪字（实测「返修」叠成「多」）。
            # 宽**与高**都要收敛。只收宽是先前静默丢字的真因：
            # insert_textbox 单行约占 1.58×字号（实测 box 高 11.8 时
            # 7.0pt 返回 +0.73、7.7pt 就放不下），放不下时它**一字不写也不报错**。
            # 于是宽度明明够、字号却超高的段全部静默消失
            # （实测该页 116 段只落了 46 段，丢的全是较长的字段名）。
            s = self._fit(text, rect, cap or rect.height * 0.9)
            avail = box.width - 1.0
            s = min(s, (box.height - 0.3) / 1.60)
            while s > 4.0 and _width(text, s) > avail:
                s -= 0.2
            s = max(s, 3.6)
            pg.insert_textbox(box, text, fontname=self.font, fontsize=s,
                              align=align, color=(0, 0, 0))
            n += 1
        return n


def boxes_on(page, lo=3.0, hi=11.0):
    """页面上的勾选框：近正方形的小矩形。

    表单里 `□ OK □ RWK □ SCRAP` 的三个词在同一基线上，MuPDF 并成一行；
    若整行按一个矩形写中文，中文就会压到第 2、3 个勾选框上。
    **词间空隙都是一个空格，按空隙宽度切不开** —— 真正的分隔物是
    夹在词间的勾选框图形。故按勾选框位置切行。
    """
    out = []
    for d in page.get_drawings():
        for it in d.get("items", []):
            r = None
            if it[0] == "re":
                r = fitz.Rect(it[1])
            if r is None:
                continue
            if (lo <= r.width <= hi and lo <= r.height <= hi
                    and abs(r.width - r.height) < 3.0):
                out.append(r)
    return out


def lines_of(page, clip=None, split_gap=None, drop_font=None, vxs=None):
    """页面文字行：[(rect, 文本, 最大字号)]。

    split_gap 非 None 时按**行内夹着的勾选框**把行切开（见 boxes_on 说明）；
    传 None 表示不切（图纸走整行即可）。
    """
    if split_gap is not None:
        return _lines_split_by_boxes(page, clip, drop_font=drop_font,
                                     vxs=vxs)
    out = []
    # 逐字符位置只有 "rawdict" 才给；"dict" 的 span 里没有 chars。
    mode = "dict" if split_gap is None else "rawdict"
    for b in page.get_text(mode, clip=clip)["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            if split_gap is None:
                t = _norm("".join(s["text"] for s in ln["spans"]))
                if t:
                    out.append((fitz.Rect(ln["bbox"]), t,
                                max(s["size"] for s in ln["spans"])))
                continue
            # 逐字符取位置，按空隙切段
            chars = []
            for s in ln["spans"]:
                for ch in s.get("chars", []):
                    chars.append((ch["c"], fitz.Rect(ch["bbox"]), s["size"]))
            if not chars:
                t = _norm("".join(s["text"] for s in ln["spans"]))
                if t:
                    out.append((fitz.Rect(ln["bbox"]), t,
                                max(s["size"] for s in ln["spans"])))
                continue
            seg = [chars[0]]
            for c in chars[1:]:
                gap = c[1].x0 - seg[-1][1].x1
                if gap > split_gap * c[2]:
                    out += _emit(seg)
                    seg = [c]
                else:
                    seg.append(c)
            out += _emit(seg)
    return out


def _emit(seg):
    t = _norm("".join(c[0] for c in seg))
    if not t:
        return []
    r = fitz.Rect(seg[0][1])
    for c in seg[1:]:
        r |= c[1]
    return [(r, t, max(c[2] for c in seg))]


# 行级通道每条单元的**墨迹右界**（写入框会向右放宽到单元格边界）。
# 键是 (round(x0,1), round(y0,1))。见 `_lines_split_by_boxes` 里的说明。
INK_X1 = {}


# 被水印规则剔掉的词，供调用方 log —— **不能静默丢**，
# 否则真正文被误剔也无从察觉。
_WM_DROPPED = []


def font_spans(page, pat, size_mul=2.0, abs_min=20.0):
    """字体名匹配 `pat`（子串，不分大小写）的 span 矩形集合。

    用途：把**页面水印／徽标**从待译单元里排除。实测 手册 B Manual 的
    「ACME DRILLING TOOLS」徽标是**真文字**（`Swiss721BT-BlackCondense` 13.9pt），
    与正文（`Georgia` 11pt）同 y 坐标，按水平行装桶时被并进正文串 ——
    产出 `Torquing, untorquing DRILLING of`、
    `Heat internal connections to 375° DRILLING F (191° C).` 这类怪键。

    **判据必须用字体／字号，不能用文字内容** —— `DRILLING` 也可能出现在正文。

    但**字体名单独也不够用**：手册 B 真正被并进正文的是另一处水印
    `ACME DRILLING TOOLS` 33.9pt `MicrosoftSansSerif`，而**正文也用这个字体**。
    只按字体名剔，一次剔掉 1476 词，连 `on`／`used`／`ft-lbs` 都剔了，
    未命中反而从 190 涨到 251。（幸好剔除有 log —— 静默丢就查不出来了。）

    故再加一道**自校准的字号闸门**：只剔字号 ≥ 本页正文字号 × `size_mul` 的
    span。正文字号取本页**众数**（最常见的那档），不写死。

    另一条教训：**同一份文档里水印可能有多套字体**（手册 B 有 6.4pt 页眉徽标
    与 33.9pt 页面水印两套），要按 span 逐个查过再定 pattern，
    不能看到一个就收工 —— 我先只挡了小的那套，怪键只从 192 降到 190。
    """
    import re as _re
    from collections import Counter
    rx = _re.compile(pat, _re.I)
    spans = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            for sp in ln["spans"]:
                if sp["text"].strip():
                    spans.append(sp)
    if not spans:
        return [], set()
    # 众数字号在**插图密集页**上不是正文字号（图内标注可能只有 5pt），
    # 此时 body×2 会低到 10pt，把 11pt 的正文一并剔掉 ——
    # 实测这样剔了 1941 词、含 `on`／`ft-lbs`，未命中从 190 涨到 261。
    # 故再加一道**绝对下限**：水印字号远大于任何正文，取 20pt 兜底。
    body = Counter(round(sp["size"], 1) for sp in spans).most_common(1)[0][0]
    lim = max(body * size_mul, abs_min)
    hits = [sp for sp in spans if rx.search(sp["font"]) and sp["size"] >= lim]
    rects = [fitz.Rect(sp["bbox"]) for sp in hits]
    toks = {w for sp in hits for w in sp["text"].split() if w}
    return rects, toks


def font_rects(page, pat, size_mul=2.0, abs_min=20.0):
    """只要矩形的薄封装（段级用；段级有 span 可直接比对，无需词形）。"""
    return font_spans(page, pat, size_mul, abs_min)[0]


def vrules(page, min_h=14.0):
    """页面上的**竖直表格线** x 坐标（去重后升序）。

    行级通道按基线聚行，会把**跨列**的内容并成一条：实测 手册 B 检验表
    第 130 行，「记录」列尾的 `ft-lbs. (Nm)` 与「备注」列的整句
    `Loctite 243 used on Set Screw? Set Screw Torque.` 是同一个单元
    （x 250→565，横跨 x=418 的列分隔线）。写中文时整条从 250 起排，
    两列内容就叠在一起 —— 目测清单点名的「记录列与备注列跨列」。
    竖线正是列边界的客观依据，据此切段最稳。
    """
    try:
        from dwg_bom import segments
    except Exception:
        return []
    H, V = segments(page, min_h=8.0, min_v=min_h)
    # **只保留真表格的列分隔线**：竖线的纵向区间内必须有 ≥3 条横线横穿它。
    # 单靠「纵向覆盖本行」不够 —— 插图的外框也有两条贯通的竖边，
    # 会把框内的散文按框宽切碎（实测 规范 F 密封装配各页碎出 99 条半句）。
    # 真表格必有多条行线穿过列分隔线，图框只有上下两条。
    def _crossed(x, y0, y1, need=3):
        n = 0
        for hy, hx0, hx1 in H:
            if y0 - 1 <= hy <= y1 + 1 and hx0 <= x + 1 and hx1 >= x - 1:
                n += 1
                if n >= need:
                    return True
        return False
    V = [(x, y0, y1) for x, y0, y1 in V if _crossed(x, y0, y1)]
    # 返回 (x, y0, y1) —— **纵向范围必须一并带出**。只给 x 的话，
    # 页底一张小表的竖线会被当成整页的列边界，把上方正文长句从中间劈开
    # （实测 手册 B 第 3 页整段散文碎成十几条、未命中 329）。
    out = []
    for x, y0, y1 in sorted(V):
        if out and abs(x - out[-1][0]) <= 2.0 and y0 <= out[-1][2] + 2.0:
            out[-1] = (out[-1][0], min(out[-1][1], y0), max(out[-1][2], y1))
        else:
            out.append((round(x, 1), round(y0, 1), round(y1, 1)))
    return out


def _lines_split_by_boxes(page, clip=None, ygap=3.0, drop_font=None,
                          vxs=None):
    """按「词间夹有勾选框」切行，其余照整行。

    必须用 `get_text("words")` 取**词级**位置 —— 用 span 不行：
    span 是样式段，`OK / RWK / SCRAP` 整条同一样式即一个 span，无处可切。

    `drop_font` 给字体名子串时，落在该字体 span 内的词**在聚行前剔除**
    （水印必须在装桶前剔，事后再拆已经拆不开了）。
    """
    INK_X1.clear()
    cbs = boxes_on(page)
    # **竖线必须由调用方限定在表格区内**。整页取的话，页面边框、插图轮廓
    # 都算竖线，正文长句会被从中间劈开（实测 手册 B 第 3 页整段散文被切成
    # 十几条碎片、未命中 329 条）。列切分只对表格有意义。
    vxs = list(vxs or ())
    words = page.get_text("words", clip=clip)
    if not words:
        return []
    if drop_font:
        wm, wtok = font_spans(page, drop_font)
        if wm:
            # **位置单独不够** —— 33.9pt 的大水印 span 覆盖大半页，
            # 只按「词心落在水印矩形内」剔，会把压在水印上的正文一并剔掉
            # （实测剔了 1941 词，含 `on`×27、`ft-lbs`×22）。
            # 故位置**与**词形都要命中：词必须是水印自身的词之一。
            # 词形判据要放宽到**子串**：`get_text("words")` 对大字号水印的切分
            # 并不稳定，同一个 `DRILLING` 在不同页可能被切成 `D` + `RILLING`。
            # 只认全等会漏掉碎片，成品上就留下 `RILLING TOOLS`／`ILLING TO`
            # 这种被抹了一半的残迹。子串 + 位置双条件仍然安全：
            # 正文词既要落在水印框内、又要是水印词的一部分，概率极低。
            def _in_wm(w):
                t = w[4].strip()
                if not t or not any(t in k for k in wtok):
                    return False
                c = fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
                return any(c in r for r in wm)
            kept = [w for w in words if not _in_wm(w)]
            if len(kept) < len(words):
                _WM_DROPPED.extend(w[4] for w in words if _in_wm(w))
            words = kept
        if not words:
            return []
    # 叠印去重必须在**聚行之前**做（避坑 ⑳）：该表单的标题等处文字叠印两份，
    # 若先聚行后去重，重复词会交错成「Disassembly Disassembly Service Service」。
    seen, uniq = set(), []
    for w in words:
        k = (w[4], round(w[0] / 2.5), round(w[1] / 2.5))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(w)
    words = sorted(uniq, key=lambda w: (round(w[3], 1), w[0]))
    rows, cur = [], [words[0]]
    for w in words[1:]:
        if abs(w[3] - cur[-1][3]) <= ygap:
            cur.append(w)
        else:
            rows.append(cur)
            cur = [w]
    rows.append(cur)

    # 字号由词高估计（words 不带 size）。**必须用中位数、且逐段算** ——
    # 先前按整行取 max：一行里只要混进一个高词（或两条基线在 ygap 内被并进同行），
    # sz 就被抬到 13.5pt（实测 6.7pt 的文字被估成 13.5）。后果有两个：
    # ① 切段阈值 0.75×sz 涨到 10pt，2pt 的词间空隙再也切不开；
    # ② 写字字号起点过大，缩到下限仍放不下，insert_textbox 一字未画（整格空白）。
    def _sz(ws):
        hs = sorted(w[3] - w[1] for w in ws)
        return hs[len(hs) // 2] * 0.82

    out = []
    for row in rows:
        row = sorted(row, key=lambda w: w[0])
        sz = _sz(row)
        # ── **两端对齐的散文行**：词距天然大于 0.75 em ──────────────
        # 手册 A 正文是 justified 排版，词距实测 8.0~8.4pt，而固定门槛
        # 0.75×loc = 7.57pt —— 每个词都被切成独立单元，逐词查词表、
        # 逐词写进自己那只窄框，渲染成「该　拆卸　与　总成　说明　提供…」，
        # 词序照抄英文、词间空得老远，一眼就是机翻（目测清单第 6 页点名）。
        # 判据要能把它与「同一行里的多个表格字段」区分开，三条同时成立：
        #   ① 词数够多（≥6）；② 词距**均匀**（最大/**最小** ≤ 1.6）——
        #   比值必须除以**最小**值：表头行 `(in) Style Allowed in (mm) Diameter (in)`
        #   的空隙是 2.9/53.5/72.1/80.7，中位数已被大值拉到 53.5，
        #   最大/中位 只有 1.5 —— 就把四个列头当成一句散文不切了。
        #   表格行的词距是双峰的（词内 ~2pt、跨列 ~40pt）；
        #   ③ 多数词**含小写字母**（是英文单词，不是编号／数值列）——
        #   规范 F 表 7-2 那种 13 列等距扭矩值同样均匀，但不能不切。
        _uni = 0.0
        _g = sorted(b[0] - a[2] for a, b in zip(row, row[1:]) if b[0] > a[2])
        if len(_g) >= 5 and _g[len(_g) // 2] > 0:
            _med = _g[len(_g) // 2]
            _low = sum(1 for w in row if any(c.islower() for c in w[4]))
            #   ④ 词距本身要**接近一个空格**（≤ 1.1 em）。规范 G 第 32 页的
            #   表头 `Extended Load Strength Strength (mm) inches inches` 也均匀
            #   （空隙 16.6~23.4）、也都带小写，但 20pt 空隙在 7.4pt 字号下
            #   是 2.7 em —— 那是列距，不是词距。
            if (_g[-1] <= 1.6 * _g[0] and _low >= 0.6 * len(row)
                    and _med <= 1.1 * max(sz, 1.0)):
                _uni = 2.2 * _med
        segs, seg = [], [row[0]]
        for w in row[1:]:
            gx0, gx1 = seg[-1][2], w[0]
            # 空隙判据用**相邻两词自身**的高度，不用整行统计值
            loc = min(w[3] - w[1], seg[-1][3] - seg[-1][1]) * 0.82
            # 两个判据都要：① 空隙里夹着勾选框；② 空隙本身够宽。
            # 只按 ① 切不开同样式的 `OK / RWK / SCRAP`；
            # 只按基线聚行则会把同一基线上**不同栏的字段**并成一条
            # （如「Customer:」与「Motor Jetted:」分处左右两栏）。
            hit = any(c.x0 >= gx0 - 1.5 and c.x1 <= gx1 + 1.5
                      and c.y1 > min(w[1], seg[-1][1]) - 1
                      and c.y0 < max(w[3], seg[-1][3]) + 1
                      for c in cbs) if gx1 > gx0 else False
            if not hit and (gx1 - gx0) > max(0.75 * loc, _uni):
                hit = True
            # ③ 空隙里**跨过一条竖直表格线** —— 列边界，必须切开。
            #    没有这一条，「记录」列尾与「备注」列首会并成一条，
            #    中文从记录列起排、压到备注列上（目测清单点名）。
            # ③ 空隙里**跨过一条纵向覆盖本行的竖直表格线** —— 列边界。
            #    「纵向覆盖」这一条不能省：同页别处小表的竖线不该切正文。
            wy0 = min(w[1], seg[-1][1])
            wy1 = max(w[3], seg[-1][3])
            if not hit and gx1 > gx0 and any(
                    gx0 - 0.5 <= vx <= gx1 + 0.5
                    and vy0 <= wy0 + 1.0 and vy1 >= wy1 - 1.0
                    for vx, vy0, vy1 in vxs):
                hit = True
            if hit:
                segs.append(seg)
                seg = [w]
            else:
                seg.append(w)
        segs.append(seg)
        # 每段的矩形要放到**可用书写区**，而不是英文墨迹的紧包围盒 ——
        # `OK` 只有约 11pt 宽，写「合格」放不下就会被 insert_textbox 丢字
        # （实测表现为「格」）。向右放宽到「下一段左界」或「右侧最近的勾选框
        # 左界」之前 1pt 为止；末段无下一段可依，放宽固定余量。
        # 不能无限放宽：redaction 会连同放宽区一并抹，越过勾选框就会把框抹掉。
        n = len(segs)
        for i, s in enumerate(segs):
            t = _norm(" ".join(w[4] for w in s))
            if not t:
                continue
            y0, y1 = min(w[1] for w in s), max(w[3] for w in s)
            ssz = _sz(s)
            x0, x1 = s[0][0], s[-1][2]
            # 右侧最近的**列分隔线** —— 既是放宽的**上界**，也是末段的
            # **可用书写区右界**。原先一律 `min(limit, vx-1)`：末段的
            # 默认 limit 只有 x1+6，取 min 后等于没放宽，中文只能挤在
            # 英文墨迹那点宽度里缩号折行（实测 手册 A 页眉最右格
            # `HS&E` → 「健康、安／全与环境」两行 5pt）。格内本来空着，
            # 放宽到列线之前是安全的（redaction 也只到列线）。
            vlim = None
            for vx, vy0, vy1 in vxs:
                if vx > x1 - 0.5 and vy0 <= y0 + 1.0 and vy1 >= y1 - 1.0:
                    vlim = vx - 1.0
                    break
            if i + 1 < n:
                limit = segs[i + 1][0][0] - 1.0
                if vlim is not None:
                    limit = min(limit, vlim)
            else:
                limit = vlim if vlim is not None else x1 + 6.0
            for c in cbs:                      # 不得越过右侧勾选框
                if c.x0 > x1 - 0.5 and c.y1 > y0 - 1 and c.y0 < y1 + 1:
                    limit = min(limit, c.x0 - 1.0)
            # 记下**墨迹右界**：写入框已向右放宽到单元格边界，凡按 x1 聚类
            # 判「整列右对齐」的判据若拿放宽后的框去看，同一格里的每一条
            # 都天然齐平右边框 —— 实测 手册 A 第 9 页消耗品清单的项目符号
            # 因此被判成右对齐，整列贴到中缝上。判据必须看墨迹。
            INK_X1[(round(x0, 1), round(y0, 1))] = x1
            out.append((fitz.Rect(x0, y0, max(x1, limit), y1), t, ssz))
    return out


def dedupe(items, tol=3.0):
    """叠印去重（避坑 ⑳）：文本相同且位置相差 < tol 的只保留一份。"""
    seen, out = set(), []
    for rect, t, sz in items:
        k = (t, round(rect.x0 / tol), round(rect.y0 / tol))
        if k in seen:
            continue
        seen.add(k)
        out.append((rect, t, sz))
    return out


def translate_page(page, lookup, keep=None, split_gap=None):
    """按 lookup(文本) → 中文（返回 None 表示保留原文）逐行叠印。

    返回 (已译行数, 未命中清单)。未命中即「既不在保留白名单、
    又查不到译名」者 —— 必须清零后方可交付。
    """
    ov = Overlay(page)
    miss = []
    for rect, t, sz in dedupe(lines_of(page, split_gap=split_gap)):
        if keep and keep(t):
            continue
        zh = lookup(t)
        if zh is None:
            miss.append(t)
            continue
        if zh == "":                      # 显式声明「保留原文」
            continue
        # 切段模式下矩形已向右放宽到「可用书写区」，故必须**左对齐锚在原左界**：
        # 若仍用居中，文字会被放宽后的框推向右侧，看起来整条标签移了位。
        ov.add(rect, zh, size=sz * 1.05, align=0 if split_gap else 1)
    n = ov.apply()
    return n, miss


def build(src, dst, lookup, keep=None, verbose=True, split_gap=None):
    doc = fitz.open(src)
    total, allmiss = 0, []
    for i, page in enumerate(doc, 1):
        n, miss = translate_page(page, lookup, keep, split_gap)
        total += n
        allmiss += [(i, m) for m in miss]
        if verbose:
            print(f"   页 {i}: 叠印 {n} 处，未命中 {len(miss)}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    doc.save(dst, garbage=3, deflate=True)
    doc.close()
    return total, allmiss


def font_char_rects(page, pat, size_mul=2.0, abs_min=20.0, pad=1.0):
    """与 `font_spans` 同判据，但返回**逐字符**矩形。

    专供**斜置水印的精确抹除**。斜排文本的 span bbox 是轴对齐包围盒 ——
    45° 时是个大方块（实测 手册 B 的 33.9pt 水印：293×293 pt），
    其中大半是空白，按它抹除会连带擦掉压在下面的表格数值
    （p4 的 `5,500`／`8,600` 就是这样消失的，而五道关一处看不见）。

    逐字符矩形沿对角线排成阶梯，紧贴字形、不碰空白角；
    也不必像 Quad 那样靠 helv 度量反推长度（字体不同必然估偏，
    实测留下 `RILLING TOOLS` 这类半截残字 26 行）。
    """
    import re as _re
    from collections import Counter
    rx = _re.compile(pat, _re.I)
    raw = page.get_text("rawdict")
    sizes = [sp["size"] for b in raw["blocks"] if b["type"] == 0
             for ln in b["lines"] for sp in ln["spans"]
             if "".join(c["c"] for c in sp["chars"]).strip()]
    if not sizes:
        return []
    body = Counter(round(s, 1) for s in sizes).most_common(1)[0][0]
    lim = max(body * size_mul, abs_min)
    out = []
    for b in raw["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            for sp in ln["spans"]:
                if not (rx.search(sp["font"]) and sp["size"] >= lim):
                    continue
                for c in sp["chars"]:
                    if not c["c"].strip():
                        continue
                    out.append(fitz.Rect(c["bbox"]) + (-pad, -pad, pad, pad))
    return out


def rescue_snapshot(page, rects, wm_rects=(), drop_font=None,
                    size_mul=2.0, abs_min=20.0):
    """记录会被 redaction **误伤**的字形，供抹除后原样补回。

    `apply_redactions` 删除的是「bbox **与框相交**」的整个字形，不是
    「落在框内」的部分。于是紧邻写入框的内容会被连带抹掉 ——
    实测 图纸族 J 图纸标题栏：`DIMENSIONS ARE IN INCHES` 的行框
    (…, 636.1, …, 644.3) 与其下方表面粗糙度值 `125` (…, 643.5, …, 649.0)
    **本就重叠 0.8pt**（MuPDF 的行框允许交叠），于是 `125` 整个消失。
    这类数值属「保留原样」，既不进词表也不报未命中，五道关全看不见。

    两组框要**分别对待**：
      · `rects`（正文写入框）—— 中心落在框内的字形本就该抹，不救；
      · `wm_rects`（水印抹除框）—— **不能**用「中心落在框内」判该不该抹。
        45° 斜置的 33.9pt 水印，单个字形的轴对齐 bbox 就有 50×50 pt，
        压在里面的图内标注（实测 手册 B p7 的 `T2`）中心自然落在框内，
        照此判据会连它一起丢。水印自身改用**字体**识别（`drop_font`），
        位置只用来判「会不会被殃及」。
    """
    wmset = set()
    if drop_font:
        for r in font_char_rects(page, drop_font, size_mul, abs_min, pad=0.0):
            wmset.add((round(r.x0, 1), round(r.y0, 1)))
    allr = [fitz.Rect(r) for r in rects] + [fitz.Rect(r) for r in wm_rects]
    body = [fitz.Rect(r) for r in rects]
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            dx, dy = ln.get("dir", (1.0, 0.0))
            for sp in ln["spans"]:
                for c in sp.get("chars", []):
                    if not c["c"].strip():
                        continue
                    cb = fitz.Rect(c["bbox"])
                    if (round(cb.x0, 1), round(cb.y0, 1)) in wmset:
                        continue                       # 水印自身，不救
                    ctr = fitz.Point((cb.x0 + cb.x1) / 2, (cb.y0 + cb.y1) / 2)
                    if any(ctr in r for r in body):
                        continue                       # 本就该被中文替换
                    if any(cb.intersects(r) for r in allr):
                        out.append((c["c"], fitz.Point(c["origin"]),
                                    sp["size"], sp["color"], (dx, dy)))
    return out


def rescue_restore(page, snap, font="helv"):
    """把 `rescue_snapshot` 记下的字形逐个画回原位。

    **必须先核对哪些真的没了。** `apply_redactions` 是否删掉一个字形，
    取决于它与框的重叠程度，并非「一碰就删」；快照里那些只是**擦边**、
    实际仍在页上的字，若也照画一遍，页面上就出现两份错开约 1pt 的重影
    （实测 规范 G 第 33 页出现两个 `Inches`，其中一份还被残留英文自检抓到）。
    故这里按**抹除后的实际字形位置**过滤，只补真正消失的那些。
    """
    import math
    alive = set()
    for b in page.get_text("rawdict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            for sp in ln["spans"]:
                for c in sp.get("chars", []):
                    o = c["origin"]
                    alive.add((c["c"], round(o[0], 0), round(o[1], 0)))
    snap = [x for x in snap
            if (x[0], round(x[1].x, 0), round(x[1].y, 0)) not in alive]
    for ch, org, size, color, (dx, dy) in snap:
        try:
            col = fitz.sRGB_to_pdf(color) if isinstance(color, int) else color
            if abs(dx - 1.0) < 0.2 and abs(dy) < 0.2:
                page.insert_text(org, ch, fontname=font, fontsize=size,
                                 color=col)
            else:
                deg = math.degrees(math.atan2(-dy, dx))
                page.insert_text(org, ch, fontname=font, fontsize=size,
                                 color=col, morph=(org, fitz.Matrix(deg)))
        except Exception:
            pass
    return len(snap)
