# -*- coding: utf-8 -*-
"""版式引擎：页面几何、抬头/页脚装饰、装配、逐页装配自检。

两种装配模式
  · flow=True（**R 级语义重排，V2 默认**）：pages 是「章」的块列表，章内流式
    排版、页数由内容决定；章与章接排（chapter_break=True 则每章另起一页）。
    页码按实排物理页生成；交叉引用一律按节号/图表号，不按页码。
    fit_check 不适用（无框可溢）。
  · flow=False（P/H 级 1:1 同源）：每源页对应一输出页，逐页建 P001…PNNN
    块列表，装配时每页一个 PageBreak，页码体系与原版一致。

三个不可省的机制
  · fit_check()  每个逻辑页**单独排一次**，实测页数必须为 1（避坑 ㉓ 估高不可靠）
  · Marker       零高度 flowable，记录自己落在第几物理页 —— 附录标签用它
                 做两趟构建，不预估页数（避坑 ㉕）
  · 硬闸门       build() 可传 assert_pages，物理页数不符即抛错终止（避坑 ㉔）
"""
import io
import os
from dataclasses import dataclass, field

from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, PageBreak,
                                Flowable, Paragraph, Table, TableStyle, Spacer)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle

import zhlib as _Z
from zhlib import zh, styles, register_fonts
from render import flow, P, NAV


# ================================================================ 几何
@dataclass(frozen=True)
class Geom:
    """页面几何。单位 pt，原点约定：mast_top/foot_top 均自各自那一边量起。

    frozen：几何一经确定不得就地改动（Job 用它作 dataclass 默认值也要求不可变）。
    需要变体时用 dataclasses.replace(LETTER, ml=54)。
    """
    w: float = 612.0
    h: float = 792.0
    ml: float = 72.0
    mr: float = 72.0
    mast_top: float = 21.6       # 抬头上沿距页顶
    body_gap: float = 12.0       # 抬头下沿到版心上沿
    foot_top: float = 70.0       # 页脚上沿距页底
    foot_gap: float = 8.0        # 版心下沿必须高于页脚上沿（避坑 ㉒）
    top_only: float = 58.0       # 无抬头时的版心上沿距页顶

    @property
    def fw(self):
        return self.w - self.ml - self.mr

    @property
    def mb(self):
        return self.foot_top + self.foot_gap


LETTER = Geom()
LETTER_LS = Geom(w=792.0, h=612.0)
A4 = Geom(w=595.0, h=842.0)
D_LS = Geom(w=1224.0, h=792.0, ml=54.0, mr=54.0)      # 图纸族 J 装配图纸
CHART_LS = Geom(w=792.0, h=545.0, ml=48.0, mr=48.0,
                mast_top=18.0, foot_top=44.0, body_gap=10.0)


# ================================================================ 抬头
def _fit_size(text, cell_w, base, floor=6.4, font="ZH", pad=6.0):
    """把 text 收进 cell_w 所需的字号。下限 floor，步长 0.2pt。"""
    from reportlab.pdfbase import pdfmetrics
    avail = cell_w - pad
    s = base
    while s > floor and pdfmetrics.stringWidth(text, font, s) > avail:
        s -= 0.2
    return s


class Masthead:
    """抬头表：徽标（或品牌文字）| 文档类别大标题 ／ 下方一行元信息。

    原版是 Word 页眉，每页重复。故画在 canvas 上而非进流，
    保证每页位置完全一致，且不吃版心高度预算。
    """

    def __init__(self, title, info_cells, logo=None, logo_w=138.0,
                 info_w=None, S=None, title_size=18.0, logo_text=""):
        self.title = title
        self.logo_text = logo_text     # 无徽标图时左格写的品牌文字（缺省留空）
        self.info = list(info_cells)
        self.logo = logo
        self.logo_w = logo_w
        self.info_w = info_w
        self.S = S or styles()
        self.title_size = title_size
        self._t = None
        self._h = None

    def _build(self, width):
        from reportlab.platypus import Image as RLImage
        S = self.S
        st_t = ParagraphStyle("mast_t", fontName="ZH-B", fontSize=self.title_size,
                              leading=self.title_size * 1.22, alignment=TA_CENTER,
                              textColor=colors.black, wordWrap="CJK")
        st_i = ParagraphStyle("mast_i", fontName="ZH", fontSize=8.2, leading=10.6,
                              alignment=TA_CENTER, wordWrap="CJK")
        if self.logo and os.path.exists(self.logo):
            from PIL import Image as PILImage
            with PILImage.open(self.logo) as im:
                iw, ih = im.size
            cell0 = RLImage(self.logo, width=self.logo_w - 10,
                            height=(self.logo_w - 10) * ih / float(iw))
        else:
            cell0 = P(self.logo_text, st_i)

        # 第二行列宽：未指定则等分整幅
        n = len(self.info)
        iw2 = self.info_w or [width / float(n)] * n
        k = width / float(sum(iw2))
        iw2 = [x * k for x in iw2]

        # 元信息单元格逐格自适配字号：中文日期「2020 年 12 月 11 日」比
        # 「Dec 11, 2020」宽得多，照抄原版列宽必然折行，抬头随之变高两倍。
        # 收缩优于折行 —— 折行会把抬头撑高、连带压低版心上沿。
        r1 = [cell0, P(self.title, st_t)]
        r2, self.shrunk = [], []
        for c, cw in zip(self.info, iw2):
            s = _fit_size(zh(str(c)), cw, st_i.fontSize)
            if s < st_i.fontSize - 0.01:
                self.shrunk.append((str(c), round(s, 1)))
            st = (st_i if s >= st_i.fontSize - 0.01 else
                  ParagraphStyle(f"mast_i{len(r2)}", parent=st_i, fontSize=s,
                                 leading=s * 1.3))
            r2.append(P(c, st))

        inner = Table([r2], colWidths=iw2)
        inner.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))

        t = Table([r1, [inner, ""]],
                  colWidths=[self.logo_w, width - self.logo_w])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, 0), 0.7, colors.black),
            ("SPAN", (0, 1), (-1, 1)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("LEFTPADDING", (0, 1), (-1, 1), 0),
            ("RIGHTPADDING", (0, 1), (-1, 1), 0),
            ("TOPPADDING", (0, 1), (-1, 1), 0),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
            ("LEFTPADDING", (0, 0), (-1, 0), 4),
            ("RIGHTPADDING", (0, 0), (-1, 0), 4),
            ("TOPPADDING", (0, 0), (-1, 0), 4),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4)]))
        self._t = t
        self._h = t.wrap(width, 400)[1]
        return t

    def height(self, width):
        if self._h is None:
            self._build(width)
        return self._h

    def draw(self, cv, geom):
        w = geom.fw
        if self._t is None:
            self._build(w)
        self._t.drawOn(cv, geom.ml, geom.h - geom.mast_top - self._h)


class Footer:
    """页脚：左中右三段小字 + 右下角页码标签。原版无分隔线，不擅自添加。"""

    def __init__(self, left="", center="", right="", rule=False):
        self.left, self.center, self.right, self.rule = left, center, right, rule

    def draw(self, cv, geom, label):
        cv.saveState()
        cv.setFont("ZH", 7.6)
        cv.setFillColor(colors.HexColor("#555555"))
        y = geom.foot_top - 8.0
        if self.rule:
            cv.setStrokeColor(_Z.BRAND_RULE)
            cv.setLineWidth(0.5)
            cv.line(geom.ml, geom.foot_top, geom.w - geom.mr, geom.foot_top)
        for i, ln in enumerate(str(self.left).split("\n")):
            cv.drawString(geom.ml, y - i * 9.4, zh(ln))
        if self.center:
            cv.drawCentredString(geom.w / 2.0, y, zh(self.center))
        if self.right:
            cv.drawRightString(geom.w - geom.mr, y, zh(self.right))
        if label:
            cv.setFont("ZH", 8.6)
            cv.setFillColor(colors.black)
            cv.drawRightString(geom.w - geom.mr, geom.foot_top - 22.0, label)
        cv.restoreState()


# ================================================================ 标记
class Decor:
    """把任意 flowable 画在页面固定位置的装饰件（页眉块 / 页脚签署块）。

    比 Masthead 通用：fn(page_no) 每页可返回不同内容，故「第 N 页 / 共 M 页」
    这类随页变化的页眉可照原版印在页眉里。位置用 y_top（距页顶）或
    y_bot（块下沿距页底）给出，版心上下沿由本类实测高度反推 ——
    不写死间距（SKILL §10）。
    """

    def __init__(self, fn, width, y_top=None, y_bot=None, gap=8.0,
                 pages=None):
        assert (y_top is None) != (y_bot is None), "y_top 与 y_bot 二选一"
        self.fn, self.width = fn, width
        self.y_top, self.y_bot, self.gap = y_top, y_bot, gap
        self.pages = pages           # None = 每页都画
        self._cache = {}

    def _get(self, pno):
        if pno not in self._cache:
            t = self.fn(pno)
            t.wrap(self.width, 10000)
            self._cache[pno] = t
        return self._cache[pno]

    def height(self, pno=1):
        return self._get(pno).wrap(self.width, 10000)[1]

    def reserve(self):
        """(边, 该边需让出的净空)。取前几页的最大实测高度，避免逐页抖动。"""
        h = max(self.height(p) for p in (self.pages or (1, 2, 3)))
        if self.y_top is not None:
            return ("top", self.y_top + h + self.gap)
        return ("bottom", self.y_bot + h + self.gap)

    def draw(self, cv, geom, pno):
        if self.pages is not None and pno not in self.pages:
            return
        t = self._get(pno)
        h = t.wrap(self.width, 10000)[1]
        y = (geom.h - self.y_top - h) if self.y_top is not None else self.y_bot
        t.drawOn(cv, geom.ml, y)


class Marker(Flowable):
    """零高度探针：记录自己被画在第几物理页。

    附录页数不可预估（避坑 ㉕），用它做两趟构建远比「文本搜标记词」可靠 ——
    封面若写有「见附录 A」，按文本搜就会命中封面。
    """

    def __init__(self, key, sink):
        Flowable.__init__(self)
        self.key, self.sink = key, sink
        self.width = self.height = 0

    def wrap(self, *a):
        return (0, 0)

    def draw(self):
        self.sink[self.key] = self.canv.getPageNumber()


# ================================================================ 装配
# 成品 PDF 的文档属性（标题/作者/主题），由 driver 按 Job 设置；出版级成品不应留 "(anonymous)"
DOC_META = {}


class _Doc(BaseDocTemplate):
    def __init__(self, path, geom, mast, foot, labels, decors=(), **kw):
        kw = dict(DOC_META, **kw)
        self.geom, self.mast, self.foot = geom, mast, foot
        self.decors = list(decors or ())
        self.labels = labels or {}
        # 版心上下沿由装饰件的**实测高度**反推，不写死间距
        mh = mast.height(geom.fw) if mast else 0.0
        top = (geom.mast_top + mh + geom.body_gap) if mast else geom.top_only
        bot = geom.mb
        for d in self.decors:
            side, need = d.reserve()
            if side == "top":
                top = max(top, need)
            else:
                bot = max(bot, need)
        BaseDocTemplate.__init__(self, path, pagesize=(geom.w, geom.h),
                                 leftMargin=geom.ml, rightMargin=geom.mr,
                                 topMargin=0, bottomMargin=bot, **kw)
        self.body_top, self.body_bot = top, bot
        self.addPageTemplates([PageTemplate(
            id="main",
            frames=[Frame(geom.ml, bot, geom.fw, geom.h - top - bot, id="body",
                          leftPadding=0, rightPadding=0,
                          topPadding=0, bottomPadding=0)],
            onPage=self._decorate)])

    def _decorate(self, cv, doc):
        n = cv.getPageNumber()
        if self.mast and n not in self.labels.get("_nomast", ()):
            self.mast.draw(cv, self.geom)
        for d in self.decors:
            d.draw(cv, self.geom, n)
        if self.foot:
            self.foot.draw(cv, self.geom, self.labels.get(n, ""))


def assemble(pages, S, figdir, flow_mode=False, chapter_break=False):
    """块列表 → 单一 flowable 流。

    1:1 模式：每页一个 PageBreak；flow 模式：章与章之间按 chapter_break 分页。
    """
    story = []
    for i, blocks in enumerate(pages):
        if i and (not flow_mode or chapter_break):
            story.append(PageBreak())
        story += flow(blocks, S, figdir)
    return story


def build(path, pages, geom=LETTER, mast=None, foot=None, labels=None,
          S=None, figdir=None, extra_story=None, pre_story=None,
          assert_pages=None, decors=(), flow_mode=False, chapter_break=False,
          body_marker=None):
    """构建。pre_story 在主体之前（封面/目录），extra_story 在其后（附录）。"""
    register_fonts()
    S = S or styles()
    NAV.reset()                      # 每趟重新编号锚点（书签 key 两趟一致）
    story = list(pre_story or [])
    body = assemble(pages, S, figdir, flow_mode, chapter_break) if pages else []
    if body and body_marker is not None:
        body.insert(0, body_marker)
    if body:
        if story:
            story.append(PageBreak())
        story += body
    if extra_story:
        if story:
            story.append(PageBreak())
        story += extra_story
    doc = _Doc(path, geom, mast, foot, labels or {}, decors)
    doc.build(story)
    try:
        import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
    except ImportError:
        import fitz
    # 第一趟构建写入 BytesIO（只为读页号），fitz 需按 stream 打开
    if isinstance(path, io.BytesIO):
        with fitz.open(stream=path.getvalue(), filetype="pdf") as d:
            n = d.page_count
    else:
        with fitz.open(path) as d:
            n = d.page_count
    if assert_pages is not None and n != assert_pages:
        raise AssertionError(
            f"硬闸门：物理页数 {n} != 预期 {assert_pages}。"
            f"1:1 同源版式下任一逻辑页溢出，其后所有页眉页脚标签会整体错位"
            f"（页码看着仍连续，内容与页码对不上）。先跑 fit_check 定位。")
    return n


def build_2pass(path, pages, appendices, geom=LETTER, mast=None, foot=None,
                S=None, figdir=None, pre_story=None, body_offset=None,
                body_total=None, front_labels=None, verbose=True,
                body_labels_on=True, decors=(), flow_mode=False,
                chapter_break=False, info=None):
    """两趟构建：先排一遍读出各附录真实起止物理页，再带正确标签重排。

    附录页数**不可预估** —— 预估与实排差 1 页，附录之后所有标签就整体错位
    （避坑 ㉕）。用零高度 Marker 读真实页号，比「文本搜标记词」可靠：
    封面若写有「见附录 A」，按文本搜会命中封面。

    appendices : [(标签字母, [flowable, ...]), ...] 或返回该结构的**工厂函数**。
                 两趟构建会把同一 story 排两遍，而 ReportLab 的 flowable 有状态
                 （Table 记住拆分状态），复用同一实例第二趟会抛 LayoutError。
                 故务必传工厂，使每趟拿到全新对象。
    body_offset: 正文首页之前的物理页数，缺省按 pre_story 实排结果自动求得
    flow_mode  : R 级流式重排 —— 正文物理页数由第一趟实排读出，不等于 len(pages)
    info       : 可选 dict，回填 n_body（正文物理页数）与 body_offset
    返回 (物理总页数, labels, spans)
    """
    register_fonts()
    S = S or styles()
    n_body = len(pages)

    def _apx():
        return appendices() if callable(appendices) else appendices

    def make_extra(sink):
        out = []
        for i, (tag, flows) in enumerate(_apx()):
            if i:
                out.append(PageBreak())
            out.append(Marker(tag, sink))
            out += list(flows)
        return out

    def make_pre(sink):
        if not pre_story:
            return None
        return [Marker("_body0", sink)] + list(pre_story)

    NAV.reset(full=True)
    has_toc = any(isinstance(b, tuple) and b and b[0] == "toc" for blocks in (pages or []) for b in blocks)
    if has_toc:
        # 第〇趟：先收集全部标题条目（目录行数由它定），目录高度随之固定，后两趟版面才稳定
        build(io.BytesIO(), pages, geom, mast, foot, {}, S, figdir,
              extra_story=make_extra({}), pre_story=list(pre_story or []), decors=decors,
              flow_mode=flow_mode, chapter_break=chapter_break, body_marker=Marker("_body", {}))
        NAV.entries = list(NAV.seen)

    # ---- 第一趟：只为读页号，标签留空 ----
    sink = {}
    tmp = io.BytesIO()
    n1 = build(tmp, pages, geom, mast, foot, {}, S, figdir,
               extra_story=make_extra(sink), pre_story=list(pre_story or []),
               decors=decors, flow_mode=flow_mode, chapter_break=chapter_break,
               body_marker=Marker("_body", sink))

    if flow_mode and "_body" in sink:
        # 流式重排：正文页数 = 第一个附录起始页（或总页数 + 1）− 正文首页
        _t = [t for t, _ in _apx()]
        body0 = sink["_body"]
        n_body = (sink[_t[0]] if _t else n1 + 1) - body0
        if body_offset is None:
            body_offset = body0 - 1
    if body_offset is None:
        # 正文之前的物理页数 = 第一个附录起始页 - 1 - 正文页数
        _t = [t for t, _ in _apx()]
        body_offset = ((sink[_t[0]] - 1 - n_body) if _t else n1 - n_body)
    body_total = body_total or n_body

    tags = [t for t, _ in _apx()]
    spans = []
    for i, tag in enumerate(tags):
        p0 = sink[tag]
        p1 = (sink[tags[i + 1]] - 1) if i + 1 < len(tags) else n1
        spans.append((tag, p0, p1))

    labels = dict(front_labels or {})
    # body_labels_on=False：原版把「Page 1 of 2」印在页眉里，页脚再放一份就成了
    # 双重页码。此时正文页码由内容层写进页眉，check_labels 一样能匹配到。
    if body_labels_on:
        labels.update(body_labels(n_body, body_offset, body_total))
    labels.update(appendix_labels(spans))

    # ---- 第二趟：带正确标签重排。Marker 零高度，不影响版面 ----
    NAV.toc_pages, NAV.labels = dict(NAV.pages), dict(labels)
    sink2 = {}
    n2 = build(path, pages, geom, mast, foot, labels, S, figdir,
               extra_story=make_extra(sink2), pre_story=list(pre_story or []),
               assert_pages=n1, decors=decors, flow_mode=flow_mode,
               chapter_break=chapter_break, body_marker=Marker("_body", sink2))
    if info is not None:
        info.update(n_body=n_body, body_offset=body_offset, body_total=body_total)
    if verbose:
        seg = "  ".join(f"附录{t}={a}~{b}" for t, a, b in spans)
        print(f"  两趟构建：共 {n2} 页  正文偏移 {body_offset}  {seg}")
    return n2, labels, spans


# ================================================================ 自检
def fit_check(pages, geom=LETTER, mast=None, foot=None, S=None, figdir=None,
              names=None, decors=()):
    """每个逻辑页**单独排一次**，实测页数必须为 1。

    不可用 flowable.wrap() 累加估高 —— 对「单元格内嵌套 flowable 的表格」
    估不准，会漏检溢出（避坑 ㉓）。
    """
    try:
        import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
    except ImportError:
        import fitz
    register_fonts()
    S = S or styles()
    bad = []
    for i, blocks in enumerate(pages):
        nm = (names[i] if names and i < len(names) else f"P{i+1:03d}")
        buf = io.BytesIO()
        doc = _Doc(buf, geom, mast, foot, {}, decors)
        try:
            doc.build(flow(blocks, S, figdir))
        except Exception as e:
            bad.append((nm, f"排版异常 {type(e).__name__}: {e}"))
            continue
        with fitz.open(stream=buf.getvalue(), filetype="pdf") as d:
            n = d.page_count
        if n != 1:
            bad.append((nm, f"实测 {n} 页（必须为 1）"))
    return bad


def body_labels(n_body, offset, total=None):
    """正文页码标签字典：物理页 → 「第 k 页 / 共 N 页」。

    offset 为正文首页之前的物理页数（封面等）。verify.py 的正则要求
    「第 N 页 / 共 M 页」这一确切形式。
    """
    total = total or n_body
    return {offset + k: f"第 {k} 页 / 共 {total} 页" for k in range(1, n_body + 1)}


def appendix_labels(spans):
    """附录页码标签：{('A', 起始物理页, 结束物理页), ...} → 物理页 → 「附录 A-1」。"""
    out = {}
    for tag, p0, p1 in spans:
        for k, p in enumerate(range(p0, p1 + 1), 1):
            out[p] = f"附录 {tag}-{k}"
    return out


def collapse(flow):
    """整页模板切换的空白页折叠（避坑 75）。

    `NextPageTemplate('full') + PageBreak` 自带换页——它前面若还残留一个
    PageBreak（可再带一个 NPT('body')），那个 PageBreak 会先撕出一张空
    body 页再切模板。凡 [<NPT(body)>?, PB, NPT(full), PB] 折叠为
    [NPT(full), PB]。构建收尾对整条 flow 跑一遍，并配合
    「空白页 = 0」（无文本且无图）常驻判据。
    """
    from reportlab.platypus import PageBreak

    def _npt(x):
        a = getattr(x, "action", None)
        return a[1] if a and a[0] == "nextPageTemplate" else None

    out = []
    for x in flow:
        out.append(x)
        n = len(out)
        if (n >= 2 and isinstance(out[-1], PageBreak)
                and _npt(out[-2]) == "full"):
            j = n - 3
            if j >= 0 and isinstance(out[j], PageBreak):
                k = j - 1
                if k >= 0 and _npt(out[k]) == "body":
                    del out[k:j + 1]
                else:
                    del out[j]
    return out


class SectionBreak(Flowable):
    """节前分页：**本页已经排了东西才断**，页面本来就空就不断。

    ⚠ ReportLab 5.0.0 的 `PageBreakIfNotEmpty` 是个空壳
      （`class PageBreakIfNotEmpty(PageBreak): pass`，`handle_flowable` 里
      只按 `isinstance(f, PageBreak)` 分派），与 `PageBreak` 完全同义 ——
      上一节的内容若正好排满整页，照样再撕出一张**空白页**。
      实测 规范 H 第 13、28 页两张，而关 7「空白页」看不见它：页上有页眉页脚，
      `get_text()` 非空。⇒ 自己按 `CondPageBreak` 的路子写一个。

    ⚠ 还要配 `_nodup` 把紧挨在它前面的 Spacer 丢掉 —— 表格后的那点间距若被
      带到新页顶上，`frame._atTop` 就成了 False，本类照断不误，空白页照旧。
    """

    def __init__(self):
        Flowable.__init__(self)
        self.width = self.height = 0

    def wrap(self, aw, ah):
        f = self._doctemplateAttr("frame")
        if f is not None and not getattr(f, "_atTop", True):
            from reportlab.platypus.doctemplate import PageBreak as _PB
            f.add_generated_content(_PB())
        return 0, 0

    def draw(self):
        pass
