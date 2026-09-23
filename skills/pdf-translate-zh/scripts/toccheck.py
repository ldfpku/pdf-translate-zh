# -*- coding: utf-8 -*-
"""**封面与目录的机器判据**（排版规范 §5）。

前六道关（未命中／溢出／残留英文／缺字／重叠／保留项失踪）看的是**全书**，
且从不看「位置对不对」。封面与目录恰恰是**位置**决定成败的两页，
而且是用户一眼就能挑出毛病的两页 —— 本项目为「TOC 页码没对齐」被点名两次。

八道判据：

    A 数量一致    目录条目数 = 跳转链接数 = 书签数
    B 链接矩形    同页两两不重叠；每条矩形内确有文字
    C 落点回验    每条链接的目标页文本含该条目标题的关键词
    D 页码右端    同页所有页码的右端 x 离散 ≤ 一个点宽
    E 同级左界    左界相近（< 一个缩进步长）的条目必须**完全**对齐
    F 保留项      封面与目录页的型号/商标/地址/编号在成品上仍在
    G 残留英文    这两页白名单外的英文行 = 0；文字不越出页面
    H 封面对齐    成品标题块的对齐方式与源页一致（居中的别排成左对齐）

为什么要 H：叠印按原坐标写回，一旦原块是**居中**的，中文变短后左边界就
往右缩、右边界往左缩，看着仍"在原位"，实则整块偏了；若中文还折了行，
第二行会顶到写入框左边缘 —— 表现为「主标题居中、副标题左对齐参差」。
实测 手册 B／手册 C／手册 D／手册 E 四册封面全中，六道关一处不报。

为什么 E 这样写：不能拿"第 n 级 = 版心左界 + n × 步长"去核对（那是把
实现当判据）。改为**先聚类后判齐**：左界相差不到一个步长的条目，本就意在
同级，那它们必须严丝合缝地对齐。聚类容差取步长的 0.4 倍，判齐容差 0.6pt。
"""
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

_PGNUM = re.compile(r"^(?:\d{1,4}|[ivxlIVXL]{1,6}|\d+-\d+(?:-\d+)?|[A-Z]-\d+)$")
_CJK = re.compile(r"[一-鿿]")
_ENG = re.compile(r"[A-Za-z]{4,}")
# 目录行末尾的**文件编号**（`DM6754`／`675G2R PL`／`G2R w/ CLAW INSP`）：
# 手册 B 一族的索引右列不是页码，是编号。
_CODE = re.compile(r"[.·…]{2,}\s*([A-Za-z0-9][A-Za-z0-9 /\-]{2,})\s*$")


# ── 取数 ──────────────────────────────────────────────────────────
def _lines(page):
    """[(bbox, 文本, [span…])]，按阅读序。"""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            sp = [s for s in ln["spans"] if s["text"].strip()]
            if not sp:
                continue
            out.append((fitz.Rect(ln["bbox"]),
                        "".join(s["text"] for s in sp).strip(), sp))
    out.sort(key=lambda r: (round(r[0].y0, 1), r[0].x0))
    return out


def _toc_lines(page):
    """目录条目行：末尾是页码、且含至少两个可读字。"""
    out = []
    for r, t, sp in _lines(page):
        tail = sp[-1]["text"].strip()
        if not _PGNUM.match(tail):
            continue
        body = t[:len(t) - len(tail)].strip(" .…")
        if len(re.sub(r"[\s.…]", "", body)) < 2:
            continue
        out.append((r, body, tail, fitz.Rect(sp[-1]["bbox"])))
    return out


def _kw(title):
    """条目标题里最长的一段可比对关键词（去掉编号与点引线）。"""
    t = re.sub(r"[.…]{2,}", " ", title)
    t = re.sub(r"^[\d.]+\s*", "", t).strip()
    runs = re.findall(r"[一-鿿]{2,}|[A-Za-z][A-Za-z\-]{3,}", t)
    return max(runs, key=len) if runs else ""


# ── 八道判据 ──────────────────────────────────────────────────────
def gate_a(doc, toc_pages, n_entries=None):
    """条目数以**页面上实际认得出的条目**为准，不能拿链接数当条目数 ——
    那样「有目录、一条链接都没建」会 0=0=0 报绿，正是最该抓的情形。
    页码栏不是数字（如 手册 B 用文件编号索引）时认不出条目，退回链接数。
    """
    links = [l for p in toc_pages for l in doc[p - 1].get_links()
             if l.get("kind") == fitz.LINK_GOTO]
    bms = doc.get_toc() or []
    det = sum(len(_toc_lines(doc[p - 1])) for p in toc_pages)
    n = n_entries if n_entries is not None else (det or len(links))
    bad = []
    if not (n == len(links) == len(bms)):
        bad.append(f"条目 {n} / 链接 {len(links)} / 书签 {len(bms)} 三者不等")
    return bad, links, bms


def gate_b(doc, toc_pages):
    bad = []
    for p in toc_pages:
        pg = doc[p - 1]
        rs = [fitz.Rect(l["from"]) for l in pg.get_links()
              if l.get("kind") == fitz.LINK_GOTO]
        for i in range(len(rs)):
            if not pg.get_textbox(rs[i]).strip():
                bad.append((p, f"第 {i+1} 条链接矩形内无文字"))
            for j in range(i + 1, len(rs)):
                ov = (rs[i] & rs[j]).get_area()
                if ov > 0.05 * min(rs[i].get_area(), rs[j].get_area()):
                    bad.append((p, f"链接 {i+1} 与 {j+1} 重叠 {ov:.0f}pt²"))
    return bad


def gate_c(doc, toc_pages, titles=None):
    """链接目标页要含条目标题的关键词。titles 缺省时就地从页面读。"""
    bad = []
    k = 0
    for p in toc_pages:
        pg = doc[p - 1]
        rows = _toc_lines(pg)
        alln = _lines(pg)
        for l in sorted((x for x in pg.get_links()
                         if x.get("kind") == fitz.LINK_GOTO),
                        key=lambda x: (round(x["from"].y0, 1), x["from"].x0)):
            if titles is not None:
                title = titles[k] if k < len(titles) else ""
            else:
                r = fitz.Rect(l["from"])
                hit = [t for rr, t, _n, _nb in rows
                       if (rr & r).get_area() > 0.3 * rr.get_area()]
                if hit:
                    title = hit[0]
                else:
                    # 不能用 get_textbox 兜底：它把**与矩形相交的一切**都
                    # 返回，包括邻行的版次字母与下一条的尾巴 —— 抽出来的
                    # 编号于是来自下一条，判据自己造出 off-by-one 的假阳。
                    # 改取「行中心落在矩形内」的那一行，中心唯一属于一行。
                    cen = [(abs((rr.y0 + rr.y1) / 2 - (r.y0 + r.y1) / 2), t)
                           for rr, t, _s in alln
                           if r.y0 <= (rr.y0 + rr.y1) / 2 <= r.y1
                           and rr.x0 < r.x1 and rr.x1 > r.x0]
                    title = min(cen)[1] if cen else ""
            k += 1
            tgt = l.get("page", -1)
            if tgt < 0 or tgt >= len(doc):
                bad.append((p, f"「{title[:22]}」目标页 {tgt+1} 越界"))
                continue
            # **索引键是什么就验什么**。文件编号索引（手册 B 一族）的条目文字
            # 是一段描述，不是会原样出现在落点页上的标题 —— 拿标题关键词去
            # 验必然全军覆没。这类条目末尾是编号，就验编号印在落点页上。
            m = _CODE.search(" ".join(title.split()))
            # 页码（`26`／`7-3-1`／`iv`）也长得像编号，但它该走标题回验 ——
            # 尤其是**页码经过勘正**的条目：原版写 7-3-1、正文实际在 7-3-2，
            # 拿原版页码去验落点，正确的链接反而报错。
            if m and _PGNUM.match(m.group(1).strip()):
                m = None
            if m:
                code = m.group(1).strip()
                if code not in " ".join(doc[tgt].get_text().split()):
                    bad.append((p, f"「{title[:22]}」→ 第 {tgt+1} 页无编号"
                                   f"「{code}」"))
                continue
            w = _kw(title)
            if not w:
                # 「第 1 节」这类标题没有连续两字的可比对片段 —— 抽不出
                # 关键词就只验页号在界内，不能报错（否则判据自己造假阳）。
                continue
            txt = "".join(doc[tgt].get_text().split())
            if w.replace(" ", "") not in txt:
                bad.append((p, f"「{title[:22]}」→ 第 {tgt+1} 页无「{w}」"))
    return bad


def gate_d(doc, toc_pages, tol=None, colgap=60.0):
    """页码右端离散。**先按栏聚类，再逐栏判齐** ——

    双栏目录天然有两个右界（实测 手册 I 左栏 x≈300、右栏 x≈545，
    整页一起量得 245.6pt，判据会把一页排得很好的目录判死）。
    栏与栏的间隔远大于「一个点宽」，取 colgap 一刀切开即可。
    """
    bad = []
    for p in toc_pages:
        rows = _toc_lines(doc[p - 1])
        if len(rows) < 3:
            continue
        sz = max(nb.height for _r, _t, _n, nb in rows)
        lim = tol if tol is not None else sz * 0.55      # 约一个点宽
        rows = sorted(rows, key=lambda r: r[3].x1)
        cols, cur = [], [rows[0]]
        for r in rows[1:]:
            if r[3].x1 - cur[-1][3].x1 > colgap:
                cols.append(cur)
                cur = []
            cur.append(r)
        cols.append(cur)
        for c in cols:
            if len(c) < 3:
                continue
            d = c[-1][3].x1 - c[0][3].x1
            if d > lim:
                bad.append((p, f"页码右端离散 {d:.1f}pt > {lim:.1f}pt"
                               f"（最远：「{c[-1][1][:20]}」）"))
    return bad


def gate_e(doc, toc_pages, step=None, tol=0.6):
    bad = []
    for p in toc_pages:
        rows = _toc_lines(doc[p - 1])
        if len(rows) < 3:
            continue
        sz = max(r.height for r, _t, _n, _nb in rows)
        st = step if step is not None else sz * 1.60
        xs = sorted((r.x0, t) for r, t, _n, _nb in rows)
        grp, cur = [], [xs[0]]
        for x, t in xs[1:]:
            if x - cur[0][0] <= st * 0.40:
                cur.append((x, t))
            else:
                grp.append(cur)
                cur = [(x, t)]
        grp.append(cur)
        for g in grp:
            if len(g) < 2:
                continue
            d = g[-1][0] - g[0][0]
            if d > tol:
                bad.append((p, f"同级左界离散 {d:.1f}pt："
                               f"「{g[0][1][:16]}」x={g[0][0]:.1f} vs "
                               f"「{g[-1][1][:16]}」x={g[-1][0]:.1f}"))
    return bad


def gate_f(src, doc, pages, min_len=3):
    """这些页上「源有、成品无」的保留项。封面保留项密度最高，最危险。

    两条防假阳：
      · 比对**去掉全部空白后的整页串**，不是按空格分出的词集合 ——
        源上 `(281) 590-2280,` 与成品上的分词方式不同，按词比必然误报；
      · 目录行的点引线在源里与代号粘成一体（`CLAW......DM6754`），
        先按点引线切开再取词，否则整条都被当成"失踪的保留项"。
    """
    _k = re.compile(r"^(?=[A-Za-z0-9\-.,/]*\d)[A-Za-z0-9\-.,/()]{3,}$")
    bad = []
    with fitz.open(src) as a:
        for p in pages:
            if p > len(a) or p > len(doc):
                continue
            have = "".join(doc[p - 1].get_text().split())
            txt = re.sub(r"[.·…]{2,}", " ", a[p - 1].get_text())
            # 尾随标点要剥掉：译文把半角 `,` `.` 换成了全角 `，` `。`，
            # 连标点一起比，`590-2280,` 这类号码每册都会误报一次。
            want = [w.rstrip(".,;:)") for w in txt.split()]
            want = [w for w in want if len(w) >= min_len and _k.match(w)]
            for w in list(dict.fromkeys(want)):
                if w not in have:
                    bad.append((p, w))
    return bad


def gate_g(doc, pages, whitelist=None):
    wl = re.compile(whitelist, re.I) if whitelist else None
    bad = []
    for p in pages:
        pg = doc[p - 1]
        box = pg.rect + (12, 12, -12, -12)
        for r, t, _sp in _lines(pg):
            if not box.contains(r) and (r & box).get_area() < 0.9 * r.get_area():
                bad.append((p, f"文字越出页面：「{t[:24]}」"))
            s = " ".join(t.split())
            if _ENG.search(s) and not _CJK.search(s) \
                    and not re.search(r"[　-〿＀-￯]", s) \
                    and not (wl and wl.search(s)):
                bad.append((p, f"残留英文：「{s[:40]}」"))
    return bad


def _align(rows, box=None, tol=2.5, rel=0.03):
    """块内各行的对齐方式 —— 与装配引擎**共用同一判据**。

    判据放在 `dwg_overlay` 里：装配时靠它决定「这块要不要居中写」，
    验收时靠它检查「写出来还是不是那个对齐」。两边必须是同一套 ——
    各写一套的话，闸门只会认同自己那一套的错。
    """
    from dwg_overlay import block_align
    return block_align(rows, tol, rel)


_ANAME = {0: "左对齐", 1: "居中", 2: "右对齐", -1: "无定形"}


def _bands(page, gap=2.2):
    """按纵向邻接把文本行切成块，返回 [(y0, y1, [行框…])]。

    **不按字号切**。曾按「字号 ≥ 中位 ×1.35」取标题块，结果 手册 B 源封面
    只有一行过线（中位 20pt、副标题 24pt 不到 27pt），`_align` 因不足两行
    直接跳过 —— 封面歪成那样judge 却报绿。字号阈值是脆的，纵向邻接不是。
    """
    rows = [(r, t) for r, t, _sp in _lines(page)]
    if not rows:
        return []
    hs = sorted(r.height for r, _t in rows)
    h = hs[len(hs) // 2] or 10.0
    out, cur = [], [rows[0]]
    for r, t in rows[1:]:
        if r.y0 - cur[-1][0].y1 <= h * gap:
            cur.append((r, t))
        else:
            out.append(cur)
            cur = [(r, t)]
    out.append(cur)
    return [(min(x[0].y0 for x in g), max(x[0].y1 for x in g),
             [x[0] for x in g]) for g in out]


def gate_h(src, doc, pages, tol=2.5):
    """成品各块的对齐方式必须与源页一致。

    块**由源页划定**（叠印保 y 坐标），成品取落在同一纵向区间的行 ——
    这样才是在比"同一块"，不用去配对两边各自切出来的块。
    整页再比一次：源封面通篇居中、成品混进一个左对齐块时，
    逐块比可能各自成立，整页比才露出来。
    """
    bad = []
    with fitz.open(src) as a:
        for p in pages:
            if p > len(a) or p > len(doc):
                continue
            sp, dp = a[p - 1], doc[p - 1]
            drows = [r for r, _t, _s in _lines(dp)]
            todo = [(None, [r for r, _t, _s in _lines(sp)], drows)]
            for y0, y1, rs in _bands(sp):
                hit = [r for r in drows if r.y0 >= y0 - 4 and r.y1 <= y1 + 4]
                todo.append((round(y0), rs, hit))
            for tag, rs, hit in todo:
                if len(rs) < 2 or len(hit) < 2:
                    continue
                # 容差以**源块宽**为准，两边同一把尺。若各按自己的块宽算，
                # 中文更紧凑 ⇒ 成品块更窄 ⇒ 容差更小 ⇒ 同样的物理离散在
                # 成品这边反而判不过 —— 判据会因为「译得好」而报错
                # （实测 规范 F 封面：源块宽 447pt 容差 13.4，成品块宽 252pt
                #  容差降到 7.6，实际离散 7.9 就此翻车）。
                ref_lim = max(tol, 0.03 * (max(r.x1 for r in rs)
                                           - min(r.x0 for r in rs)))
                wa = _align(rs, None, ref_lim, rel=0.0)
                wb = _align(hit, None, ref_lim, rel=0.0)
                if wa != -1 and wa != wb:
                    where = "整页" if tag is None else f"y≈{tag} 处的块"
                    bad.append((p, f"{where} 源={_ANAME[wa]} → "
                                   f"成品={_ANAME[wb]}"))
    return bad


# ── 汇总 ──────────────────────────────────────────────────────────
def check(out, toc_pages=(), cover_pages=(), src=None, n_entries=None,
          titles=None, whitelist=None, step=None, verbose=True, name="",
          rebuilt=False):
    """`rebuilt=True` 跳过 F、H 两关 —— 它们的前提都是**叠印**：

    · F 关（保留项失踪）针对 redaction 连坐，重建路线没有这个失效模式；
      而重建把图表画成图元／位图，源页文本层里的刻度值在成品文本层里
      本就不存在，拿它比会满屏假阳（实测 Derating Chart 报 29 条，
      图其实完好无损）。
    · H 关（封面对齐）比的是「叠印是否保住了原位」。重建路线的封面是
      **另行编排**的，与源页逐块比对齐没有意义 —— 那是设计选择，
      该由目检判断，不该由这道关判死。
    """
    """返回 {关名: [问题…]}；全绿则每项为空表。"""
    doc = out if isinstance(out, fitz.Document) else fitz.open(out)
    toc_pages = list(toc_pages)
    cover_pages = list(cover_pages)
    res = {}
    if toc_pages:
        res["A 数量一致"], _lk, _bm = gate_a(doc, toc_pages, n_entries)
        res["B 链接矩形"] = gate_b(doc, toc_pages)
        res["C 落点回验"] = gate_c(doc, toc_pages, titles)
        res["D 页码右端"] = gate_d(doc, toc_pages)
        res["E 同级左界"] = gate_e(doc, toc_pages, step)
    pages = sorted(set(cover_pages) | set(toc_pages))
    if pages:
        res["G 残留英文"] = gate_g(doc, pages, whitelist)
        if src and not rebuilt:
            res["F 保留项"] = gate_f(src, doc, pages)
    if src and cover_pages and not rebuilt:
        res["H 封面对齐"] = gate_h(src, doc, cover_pages)
    if verbose:
        tot = sum(len(v) for v in res.values())
        print(f"  toccheck {name}: " +
              ("全绿" if not tot else f"{tot} 处"))
        for k in sorted(res):
            for x in res[k][:6]:
                print(f"     {k}  {x}")
    if not isinstance(out, fitz.Document):
        doc.close()
    return res
