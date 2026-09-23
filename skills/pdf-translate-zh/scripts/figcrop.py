# -*- coding: utf-8 -*-
"""**标注图的真实视觉范围**：不能只用嵌入位图自身的 bbox 去裁。

实测教训（手册 I V2 试点，图 3.0「马达总成与分总成」）：
带引线标注的爆炸图，标签文字与引线常是**页面上独立的矢量/文本对象**，
画在嵌入位图的 bbox **之外**（标签框在图的左右两侧，引线从框内指向图）。
只按 `get_image_info()` 的位图 bbox 裁，会把标签整行切掉一半——
裁图上留下断头的方括号引线、半个字的标签残影，肉眼一晃而过很容易放过，
交付后读者才发现某几个部件标签缺字甚至整条消失。

⇒ 裁图前必须先求**真实视觉范围** = 位图 bbox ∪ 关联的标注文字 ∪ 关联的
引线/括号矢量元素；裁完还要**核验边界上没有被腰斩的文本行**——
一行文字要么整体在裁框内，要么整体在裁框外，绝不能被边界切成两截。

这两步（求范围 + 核验不腰斩）适用于任何「位图 + 独立标注」的技术图，
不针对特定文档；调用方只需给出该图的位图 bbox。
"""
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

# 图题行："Figure 3.4 – …" / "Fig. 2" / "Table 6.1"。图题不随位图一起裁
# （中文图题由内容层 caption 承担），必须**整块**排除——见 _lines()。
_CAP_RE = re.compile(r"(?i)^\s*(figure|fig\.?|table)\s*\d")

# 孤立列表记号：邻栏列表的圆点/破折号。文字部分按正文排除在裁框外，
# 记号却可能落在裁框**物理范围内**——不吸附只保证不为它扩框，
# 已在框内的还得铺白（见 stray_markers）。
_MARKS = {"•", "◦", "·", "‣", "-", "–", "—"}


def _lines(page):
    """页面全部非空文本行：
    [(rect, 文本, 字号, 所属块行数, 是否粗体, 块最左x, 是否图题)]。

    块最左 x 取该行所属**整个块**里所有行的最小 x0——用来判断"这一行
    是不是顶格标题/正文段落的换行续行"：续行本身未必顶格（居中标题换行、
    悬挂缩进段落都会有非顶格的行），但只要同块里**有任意一行**顶格，
    整块就该判定为正文/标题，不是图内独立标注。

    图题判定同样**按块**而非按行，且要向下"传染"：图题折行后的续行
    往往是独立的行甚至独立的块（实测「Figure 3.4 – Clawshaft, CV /
    Joint, & Flexshaft」两行），只按 startswith("figure") 排除首行，
    续行就会被当成标注吸进裁框——成品图里残留半截英文图题。
    判据：块首行命中图题模式 ⇒ 整块是图题；紧贴在图题块正下方
    （间隙 ≤ 6pt）且横向重叠的块也是图题，迭代到不再扩散。
    """
    blks = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        blines = [ln for ln in b["lines"]
                  if "".join(s["text"] for s in ln["spans"]).strip()]
        if not blines:
            continue
        first = "".join(s["text"] for s in blines[0]["spans"]).strip()
        r = fitz.Rect(blines[0]["bbox"])
        for ln in blines[1:]:
            r |= fitz.Rect(ln["bbox"])
        blks.append({"lines": blines, "rect": r,
                     "left": min(ln["bbox"][0] for ln in blines),
                     "cap": bool(_CAP_RE.match(first))})
    changed = True
    while changed:
        changed = False
        for blk in blks:
            if blk["cap"]:
                continue
            r = blk["rect"]
            for cb in blks:
                if not cb["cap"]:
                    continue
                cr = cb["rect"]
                below = 0.0 <= r.y0 - cr.y1 <= 6.0
                overlap = min(r.x1, cr.x1) - max(r.x0, cr.x0)
                if below and overlap > 0.4 * min(r.width, cr.width):
                    blk["cap"] = True
                    changed = True
                    break
    out = []
    for blk in blks:
        n = len(blk["lines"])
        for ln in blk["lines"]:
            t = "".join(s["text"] for s in ln["spans"])
            sz = max((s["size"] for s in ln["spans"]), default=0)
            bold = any(bool(s["flags"] & 16) or "bold" in s["font"].lower()
                      for s in ln["spans"])
            out.append((fitz.Rect(ln["bbox"]), t, sz, n, bold,
                        blk["left"], blk["cap"]))
    return out


def body_size(page, region=None, sample_min=5, min_chars=15):
    """**该图附近**的正文基准字号：非粗体、够长的行里出现次数最多的字号。

    ⚠ 不能按字符数加权，也不能整页统计。两个坑都实测踩过：
      · 按字符数加权——密集参数表的数字单元格字符多但每格只三五个字符，
        全页字符总数能压过真正的正文；
      · 按整页统计——同一页如果**同时**有一张大参数表和一小段正文
        （本册 6.2 节：表 6.4 的十几行扭矩数据 vs 数得出来的几行
        某型号的调整步骤），表格行数量上就能反超正文，5.5pt 的表格数字
        被判成"正文基准"，于是真正 9pt 的正文整页被当成"图内标注"，
        裁框失控膨胀到原图的 11 倍。
    ⇒ 统计范围限定在**该图周边** `region`（调用方传该图的搜索窗口）——
    局部统计不受远处大表干扰；`region=None` 时才退化为全页（供独立调用）。
    行长过滤（≥min_chars）仍保留，进一步排掉短促的表格单元格。
    """
    from collections import Counter
    c = Counter()
    n = 0
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            r = fitz.Rect(ln["bbox"])
            if region is not None and not r.intersects(region):
                continue
            t = "".join(s["text"] for s in ln["spans"])
            if len(t.strip()) < min_chars:
                continue
            bold = any(bool(s["flags"] & 16) or "bold" in s["font"].lower()
                      for s in ln["spans"])
            if bold:
                continue
            sz = max((s["size"] for s in ln["spans"]), default=0)
            c[round(sz * 2) / 2] += 1
            n += 1
    if n < sample_min or not c:
        return body_size(page, region=None) if region is not None else 9.0
    return c.most_common(1)[0][0]


def column_lefts(page, region=None, top_n=3, min_count=6, tol=1.2):
    """**该图附近**正文栏的左边界 x（同一局部性考量，见 `body_size`）。

    只取出现次数最多的少数几个左边界值，且要求命中行数够多——图内一个
    标签块偶然落在栏左边界附近 ±3pt 内不该被判成"顶格标题"（实测
    「Top Sub & Rotor Catch」x0=311、真栏左边界 x0=315，只差 4pt 却被
    宽容差误伤）；真栏左边界必然是命中次数最多的那一档，偶然接近的
    标注块次数不会跟正文抗衡。
    """
    from collections import Counter
    c = Counter()
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            r = fitz.Rect(ln["bbox"])
            if region is not None and not r.intersects(region):
                continue
            if "".join(s["text"] for s in ln["spans"]).strip():
                c[round(r.x0 / tol) * tol] += 1
    top = [x for x, n in c.most_common(top_n) if n >= min_count]
    if not top and region is not None:
        return column_lefts(page, region=None)
    return set(top)


def _is_prose(rect, nlines, sz, bold, blk_left, base, lefts, frac=0.75,
             col_w=260.0, min_lines=2):
    """该行是否该被排除在"候选标注"之外（正文段落 或 标题，含其换行续行）。

    三条独立的排除判据，任一命中即排除：
      · 正文段落：字号贴近页面正文基准字号（±0.75pt）——不论是否加粗
        （小标题常用「加粗引导词 + 同号正文」，仅凭粗体分不出）；
      · 顶格标题：**本行所属整块**里有任意一行的左边界落在某一栏的
        整体左边界上（容差 3pt）——标题换行后的续行本身未必顶格
        （居中标题、悬挂缩进都会有非顶格续行），必须按块而非按行判；
      · 图内标注不可能是顶格判据误伤的——真正独立于正文流的标注，
        左边界几乎不会恰好落在栏左边界上。
    """
    if abs(sz - base) <= 0.75:
        return True
    if any(abs(blk_left - L) <= 1.5 for L in lefts):
        return True
    return False


def figure_extent(page, img_bbox, col_w=260.0, search_margin=140.0,
                  vec_max_area=2500.0, drop_caption=True, region=None):
    """给定嵌入位图的原始 bbox，求该图**含标注**的真实视觉范围。

    col_w         版心栏宽（双栏排版传单栏宽，单栏传版心宽）——用来判断
                  一行是"贴栏宽的正文"还是"窄短的标注"。
    search_margin 在位图 bbox 外扩多少范围内找候选标注（pt）。
    vec_max_area  候选引线/括号矢量元素的面积上限——大过这个多半是
                  图内的实际线框/剖面线，不是标注引线。
    drop_caption  是否把 "Figure N.M …" 图题行排除在范围外（图题另行
                  译成中文写进 caption，不随位图一起裁）。
    region        `body_size`/`column_lefts` 的统计范围——缺省时取
                  位图 bbox 外扩 `search_margin` 的窗口（局部统计，
                  不受全页远处的大表干扰，见 body_size 文档）。

    返回 (范围矩形, 命中的标注行列表)。命中列表供上层核对/生成标签坐标。
    """
    img = fitz.Rect(img_bbox)
    search = img + (-search_margin, -search_margin, search_margin, search_margin)
    region = region if region is not None else search
    base = body_size(page, region=region)
    lefts = column_lefts(page, region=region)

    # 候选标注：先按判据筛一遍，**不急着并进裁框**
    cands = []
    for rect, text, sz, nlines, bold, blk_left, cap in _lines(page):
        if not rect.intersects(search):
            continue
        if _is_prose(rect, nlines, sz, bold, blk_left, base, lefts, col_w=col_w):
            continue
        if drop_caption and cap:      # 图题整块排除，含折行续行（见 _lines）
            continue
        # 孤立的项目符号是邻栏列表的记号，不是图内标注——吸进来后
        # 成品图角上会多出几颗无主的圆点（实测某总览图左上角三颗）
        if text.strip() in _MARKS:
            continue
        cands.append((rect, text))

    # **从图心向外逐个吸附**，而不是一次性求并集。
    # 为什么：一次性求并集时，任何一个被误判的远处候选（邻栏的表头、
    # 另一节的小标题）都会把裁框一次性拉穿整页，且无从分辨是哪一个。
    # 逐个吸附则天然有序——按到图的距离从近到远，一旦某个候选距当前
    # 裁框已超过 `gap_max`，说明它与这张图之间隔着空白，不属于本图，
    # 后面更远的更不属于，直接停手。真正的引线标注一定紧贴图排布，
    # 中间不会有大段空白；邻栏内容则必然隔着栏间距。
    def _gap(r, box):
        dx = max(0.0, max(box.x0 - r.x1, r.x0 - box.x1))
        dy = max(0.0, max(box.y0 - r.y1, r.y0 - box.y1))
        return max(dx, dy)

    gap_max = 26.0
    ext = fitz.Rect(img)
    hits = []
    pool = list(cands)
    while pool:
        pool.sort(key=lambda rt: _gap(rt[0], ext))
        r, t = pool[0]
        if _gap(r, ext) > gap_max:
            break
        ext |= r
        hits.append((r, t))
        pool.pop(0)

    # 引线/括号等小矢量元素：同样只吸附紧贴裁框的。
    # 图题外面常套着线框（矢量矩形）——凡与图题行相交的矢量元素一并
    # 排除，否则图题文字排掉了、空框却被吸进裁框（成品图底一个空壳）。
    draws = [fitz.Rect(dr["rect"]) for dr in page.get_drawings()]
    cap_near = ([r for r, *_rest, c in _lines(page)
                 if c and r.intersects(search)] if drop_caption else [])
    for r in draws:
        if r.get_area() > vec_max_area or _gap(r, ext) > 6.0:
            continue
        if any(r.intersects(cr) for cr in cap_near):
            continue
        ext |= r

    # 图题禁区钳位：图题文字虽已排除，其**外框线**离位图常只有几 pt，
    # 裁框加 pad 后仍会带进一条黑杠（实测三幅图的成品底边都是图题框的
    # 上沿线）。凡图题行或与其相交的矢量框进入裁框边缘 margin 带内，
    # 按其相对位图的方位把对应边收回。margin 必须大于 safe_extent 的
    # pad，否则钳完一加 pad 又够着了。
    if cap_near:
        frames = [r for r in draws
                  if any(r.intersects(cr) for cr in cap_near)]
        margin = 4.5
        for r in cap_near + frames:
            if not r.intersects(ext + (-margin, -margin, margin, margin)):
                continue
            if r.y0 >= img.y1 - 1:        # 图题在位图下方（最常见）
                ext.y1 = min(ext.y1, r.y0 - margin)
            elif r.y1 <= img.y0 + 1:      # 图题在位图上方
                ext.y0 = max(ext.y0, r.y1 + margin)
    return ext, hits


def stray_markers(page, rect):
    """裁框内孤立的列表记号行（•、– 等）。

    候选筛选只保证**不为它们扩框**；若记号物理上就落在裁框范围内
    （常见：图占半栏、旁边一列项目列表，记号紧贴图左缘），成品图上
    仍会多出几颗无主圆点。调用方应在渲染前把返回的矩形铺白
    （与 safe_extent 的 warn 同样处理）。
    """
    return [r for r, t, *_rest in _lines(page)
            if t.strip() in _MARKS and rect.contains(r)]


def verify_no_truncation(page, rect, col_w=260.0, region=None):
    """裁框边界核验：不得有文本行被边界腰斩。

    「腰斩」＝该行与裁框相交、但既不完全在框内也不完全在框外
    （框边正好切过行内部）。正文段落行允许贴边（本就该被排除在图外），
    只警示非正文的短行——那正是标注文字被切一半的信号。
    返回违规行列表 [(rect, text)]；非空即表示裁框仍需扩大。
    """
    region = region if region is not None else rect + (-140, -140, 140, 140)
    base = body_size(page, region=region)
    lefts = column_lefts(page, region=region)
    bad = []
    for rect_ln, text, sz, nlines, bold, blk_left, cap in _lines(page):
        if cap:     # 图题本就该在裁框外，贴边不算腰斩（由 prose_bleed 管）
            continue
        if _is_prose(rect_ln, nlines, sz, bold, blk_left, base, lefts, col_w=col_w):
            continue
        inter = rect_ln & rect
        if inter.is_empty:
            continue
        fully_in = rect.contains(rect_ln)
        fully_out = inter.get_area() < 0.02 * max(rect_ln.get_area(), 0.01)
        if not fully_in and not fully_out:
            bad.append((rect_ln, text))
    return bad


def prose_bleed(page, rect, col_w=260.0, region=None):
    """裁框是否吃进了正文/标题的地盘（哪怕只沾了一角）。

    `verify_no_truncation` 只管"标注被腰斩"，管不到"正文被沾了一条边"——
    `_is_prose()` 直接把正文整体跳过，沾边的正文行既不算"腰斩"也不算
    "完整在框内"，两头都漏。而正文沾边正是実测踩过的另一类真事故：
    图 3.1 的裁框上沿多吃了 4pt，把上一段末尾"…float valve."的行尾
    刮进了裁图，成品上图片正上方露出一截无关英文。
    返回沾边的正文行列表；非空说明裁框需要在对应方向收窄。
    """
    region = region if region is not None else rect + (-140, -140, 140, 140)
    base = body_size(page, region=region)
    lefts = column_lefts(page, region=region)
    bad = []
    for rect_ln, text, sz, nlines, bold, blk_left, cap in _lines(page):
        # 图题与正文同等对待：裁框沾到英文图题也是事故（成品图里
        # 会露出半截 "Figure N.M –…"，中文图题另由 caption 承担）
        if not cap and not _is_prose(rect_ln, nlines, sz, bold, blk_left,
                                     base, lefts, col_w=col_w):
            continue
        if rect_ln.intersects(rect):
            bad.append((rect_ln, text))
    return bad


def _shrink_from(rect, bleed):
    """按沾边正文行的位置，把裁框对应的那条边收回到刚好避开它。"""
    r = fitz.Rect(rect)
    for ln, _t in bleed:
        cx, cy = (ln.x0 + ln.x1) / 2.0, (ln.y0 + ln.y1) / 2.0
        # 判断沾边发生在哪条边：正文行中心相对裁框的位置
        if cy < r.y0 + (r.y1 - r.y0) * 0.15 and ln.y1 <= r.y0 + 14:
            r.y0 = max(r.y0, ln.y1 + 1.5)
        elif cy > r.y1 - (r.y1 - r.y0) * 0.15 and ln.y0 >= r.y1 - 14:
            r.y1 = min(r.y1, ln.y0 - 1.5)
        elif cx < r.x0 + (r.x1 - r.x0) * 0.15 and ln.x1 <= r.x0 + 14:
            r.x0 = max(r.x0, ln.x1 + 1.5)
        elif cx > r.x1 - (r.x1 - r.x0) * 0.15 and ln.x0 >= r.x1 - 14:
            r.x1 = min(r.x1, ln.x0 - 1.5)
    return r


def safe_extent(page, img_bbox, col_w=260.0, max_rounds=6, pad=3.0,
                max_area_ratio=4.0, **kw):
    """`figure_extent` 之后自动跑两道核验并按需调整，直到收敛：

      ① 标注被腰斩 → 外扩，把整条命中行并入范围；
      ② 正文/标题被沾边 → 内收，把对应那条边收回到沾边行之外。

    两道核验方向相反（一个要扩、一个要收），交替跑到都不再报为止；
    达到轮次上限时如实返回当前结果，不强行判定"通过"——调用方应检查
    返回的 `warn` 是否为空，非空要么人工看一眼，要么单独处理该图。

    ⚠ `max_area_ratio` 是硬上限，防止判据在个别页面失灵时**跑飞**：
    实测某页因 `body_size()` 一时误判，扩出了原图 11 倍面积的裁框
    （见模块注释）。判据失灵是会发生的，宁可停手报警、退回原始位图
    bbox 交给调用方处理，也不能让一个跑飞的结果悄悄进成品——
    这正是「判据自己造假阳比没有判据更糟」的反面：不设上限的判据，
    错起来比没判据还离谱。
    """
    img = fitz.Rect(img_bbox)
    sm = kw.get("search_margin", 140.0)
    region = img + (-sm, -sm, sm, sm)     # 统计窗口固定，不随裁框每轮漂移
    ext, hits = figure_extent(page, img_bbox, col_w=col_w, region=region, **kw)
    if ext.get_area() > img.get_area() * max_area_ratio:
        return img, [], [(img, "AREA_RATIO_EXCEEDED: 判据跑飞，已退回原始位图 bbox")]
    warn = []
    for _ in range(max_rounds):
        padded = ext + (-pad, -pad, pad, pad)
        trunc = verify_no_truncation(page, padded, col_w=col_w, region=region)
        if trunc:
            for r, _t in trunc:
                ext |= r
            continue
        bleed = prose_bleed(page, padded, col_w=col_w, region=region)
        if bleed:
            shrunk = _shrink_from(padded, bleed)
            shrunk = fitz.Rect(shrunk) + (pad, pad, -pad, -pad)
            if not shrunk.contains(img):
                # 收缩收到了位图本体——两道核验打架，多半是这张图确实
                # 挨得太近，交给调用方人工核实，不再自动调整。
                warn = bleed
                break
            ext = shrunk
            continue
        break
    else:
        warn = verify_no_truncation(page, ext + (-pad, -pad, pad, pad),
                                    col_w=col_w, region=region) or bleed
    return ext + (-pad, -pad, pad, pad), hits, warn
