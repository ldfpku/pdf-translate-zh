# -*- coding: utf-8 -*-
"""**幻灯片/演示文稿**（PowerPoint 导出 PDF）的内容层与重排通道。

幻灯片是一类独立的版面：照片位置、引出箭头、引注落点本身即内容 ⇒ 走**叠印
保位**；但正文列表**必须整列重排**，不能逐条钉回原坐标 —— 原版的条目间距是
按**英文行数**排的，不是内容的一部分。详见 `references/slides.md`。

本模块只做与文档无关的部分：语义单元识别 + 列表重排 + 项目符号重绘 +
真下标。词表与逐条译文仍属内容层，换文档只换那一层。

已在 79 页某客户培训讲义上全量验证（六道关全绿 + 逐页目检）。
"""
import re
try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz
import keyclean
import hybrid_overlay as hy
from dwg_overlay import _width, ZH_FONT, ZH_FONT_B

FOOT_Y = 535.0          # 页脚带上沿（792×612 横开母版实测）
TITLE_Y = 105.0         # 标题带下沿
FLOOR = 6.5             # 中文字号硬下限
SIZE_K = 0.92           # 中文起排字号 = 原字号 × 此系数（见 §字号）
BULLET_CH = "–•"


def norm(s):
    """归一空白 **并归一造字区码位**。导键与装配必须共用本函数（避坑 83）。"""
    return keyclean.norm_pua(" ".join(str(s or "").split()))


# ════════════════════════════════════════════════ 一、语义单元
def units(page):
    """本页的语义单元：标题 / 项目符号条（含续行合并）/ 图内引注 / 页脚。

    返回 [{role, text, size, color, bold, align, bullet, brect, ink, tx0, nlines}]
    role ∈ {title, bullet, text, foot}；ink 为源墨迹框，tx0 为正文起排 x。
    """
    lines = _lines(page)
    _adopt_standalone_markers(lines)
    groups = _cluster(lines)
    return _emit(groups, lines)


def _lines(page):
    """逐行解析。**必须用 rawdict 取逐字符包围盒**（避坑 88）。

    项目符号有两种形态，只有拿到符号自身的精确框才能一视同仁：
      ① 自成一行（符号 x=96.1、正文 x=122.8 分属两行）；
      ② **行内首字符**（符号与正文同属一个 span）。
    按 span 框取起点对形态 ② 是错的 —— tx0 落在符号自己身上，抹除框从那里
    起算就把符号一并抹掉，实测整页项目符号消失。
    """
    out = []
    for blk in page.get_text("rawdict")["blocks"]:
        if blk["type"] != 0:
            continue
        for ln in blk["lines"]:
            ch = [(c["c"], fitz.Rect(c["bbox"]), s)
                  for s in ln["spans"] for c in s["chars"]]
            while ch and not ch[0][0].strip():
                ch.pop(0)
            while ch and not ch[-1][0].strip():
                ch.pop()
            if not ch:
                continue
            t = "".join(c[0] for c in ch)
            bul, brect, tx0 = "", None, ch[0][1].x0
            c0 = keyclean.norm_pua(ch[0][0], report=False)
            if c0 in "▪●◆" + BULLET_CH:
                bul, brect = c0, fitz.Rect(ch[0][1])
                k = 1
                while k < len(ch) and not ch[k][0].strip():
                    k += 1
                t = "".join(c[0] for c in ch[k:]) if k < len(ch) else ""
                tx0 = ch[k][1].x0 if k < len(ch) else ch[0][1].x1
            # 字号/字色/粗细取**主导 span**，不取 max（避坑 89）：行尾常挂一个
            # 更大字号的段落标记空 span，取 max 会让该行与本组「跨字号」不符
            # 而接不上，一句话被切成两条。
            cnt = {}
            for _c, _r, s in ch:
                cnt[id(s)] = (cnt.get(id(s), (0, s))[0] + 1, s)
            dom = max(cnt.values(), key=lambda z: z[0])[1]
            out.append({"r": fitz.Rect(ln["bbox"]), "t": t, "bul": bul,
                        "tx0": tx0, "sz": dom["size"], "brect": brect,
                        "bold": bool(dom["flags"] & 16),
                        "color": int(dom.get("color", 0))})
    out.sort(key=lambda z: (round(z["r"].y0, 0), z["r"].x0))
    return out


def _adopt_standalone_markers(lines):
    """只含符号的行不是单元，是**右邻同基线那一行的符号**（避坑 88 形态 ①）。

    不认这一条，那一页的子条目一条都认不出，整段正文并成一块散文写出去 ——
    溢出图区，还剩下没人认领的裸符号。认领后符号原样留在页上。
    """
    marks = [z for z in lines if z["bul"] and not z["t"].strip()]
    mset = {id(z) for z in marks}
    for m in marks:
        best = None
        for z in lines:
            if id(z) in mset:
                continue
            if (abs(z["r"].y0 - m["r"].y0) <= 3.0
                    and 0 < z["r"].x0 - m["r"].x1 < 60.0
                    and (best is None or z["r"].x0 < best["r"].x0)):
                best = z
        if best is not None:
            best["bul"], best["brect"] = m["bul"], fitz.Rect(m["r"])
            best["tx0"] = best["r"].x0
    lines[:] = [z for z in lines if id(z) not in mset]


def _cluster(lines):
    """**先按列聚类，再按纵向邻接**成组（避坑 90）。

    沿 y 序贪心吞并会把并排的几条引注串成一条 —— 它们 y 交错、只在 x 上
    分得开。续行两种形态，命中其一即可：
      ① **缩进续行**（项目符号条）：起点不浅于本条正文起点。判据不能写成
         `> tx0 + 6` —— 续行与本条正文**恰好齐平**（实测同为 162.2），
         那样写一条也接不上，物理断行就成了翻译单元边界（V2 公理禁止）。
      ② **居中块续行**（避坑 ㊿）：多行居中块各行中线取齐而左右不齐。
    """
    groups = []
    for L in lines:
        y0 = L["r"].y0
        role = ("foot" if y0 > FOOT_Y else
                "title" if y0 < TITLE_Y and L["sz"] >= 24 else
                "bullet" if L["bul"] else "text")
        if role in ("bullet", "text") and not L["bul"]:
            for g in reversed(groups):
                if g["role"] not in ("bullet", "text"):
                    continue
                gr = g["ink"]
                lc, nc = (gr.x0 + gr.x1) / 2, (L["r"].x0 + L["r"].x1) / 2
                if (min(gr.x1, L["r"].x1) - max(gr.x0, L["r"].x0) <= 0
                        or L["r"].y0 - g["ylast"] > 0.75 * L["sz"]
                        or abs(L["sz"] - g["sz"]) > 0.6):
                    continue
                if not (L["tx0"] >= g["tx0"] - 2 or abs(nc - lc) <= 8):
                    continue
                g["lines"].append(L)
                g["ink"] |= L["r"]
                g["ylast"] = L["r"].y1
                break
            else:
                groups.append(_newgrp("text", L))
            continue
        groups.append(_newgrp(role, L))
    return groups


def _newgrp(role, L):
    return {"role": role, "lines": [L], "ink": fitz.Rect(L["r"]),
            "ylast": L["r"].y1, "sz": L["sz"], "tx0": L["tx0"], "L": L}


def _emit(groups, lines):
    # 本页**正文色**＝出现最多的字色（常见母版是深藏青 #003366，不是黑）
    cc = {}
    for z in lines:
        cc[z["color"]] = cc.get(z["color"], 0) + len(z["t"])
    body = max(cc, key=cc.get) if cc else 0
    out = []
    for g in sorted(groups, key=lambda z: (round(z["ink"].y0, 0), z["ink"].x0)):
        grp, L = g["lines"], g["L"]
        ink = fitz.Rect(grp[0]["r"])
        for z in grp[1:]:
            ink |= z["r"]
        text = norm(" ".join(z["t"] for z in grp))
        if not text:
            continue
        # 原版字色是**内容**（避坑 91）：作者常用红/绿标注重点结论。
        # 强调色可能只落在折行条目的**第二行**上，按首行取色会丢掉 ⇒
        # 一组之内只要出现非正文色，整条取该色（中文一句话是一个单元）。
        col = next((z["color"] for z in grp if z["color"] != body), L["color"])
        align = "left"
        if len(grp) > 1:
            cs = [(z["r"].x0 + z["r"].x1) / 2 for z in grp]
            ls = [z["r"].x0 for z in grp]
            cd, ld = max(cs) - min(cs), max(ls) - min(ls)
            # 主判据是**比值**不是绝对容差（避坑 51）
            if cd < 0.5 * ld and cd <= max(4.0, 0.06 * ink.width):
                align = "center"
        out.append({"role": g["role"], "bullet": L["bul"], "align": align,
                    "text": text, "size": round(L["sz"], 2), "color": col,
                    "ink": [round(v, 1) for v in ink], "tx0": round(L["tx0"], 1),
                    "brect": [round(v, 1) for v in L["brect"]] if L["brect"] else None,
                    "nlines": len(grp), "bold": L["bold"]})
    return out


# ════════════════════════════════════════════════ 二、列表整体重排
def flow_items(us):
    """挑出参与重排的列表条目，其余（图内引注／标题）原位处置。

    ⚠ **带项目符号的条目无条件入流**（避坑 93）。按「最左符号 +40pt」筛，
    会把第三级条目（缩进比一级深 72pt）踢出流外，它们随即被当成图内引注
    居中排、还反过来充当流的右界障碍 —— 实测整页排成一字竖排。
    层级深浅是**缩进**，不是「是不是列表」。
    """
    buls = [u for u in us if u["role"] == "bullet"]
    if not buls:
        return [], list(us)
    lim = max(fitz.Rect(u["ink"]).x0 for u in buls) + 40
    lo = min(fitz.Rect(u["ink"]).y0 for u in buls) - 40
    hi = max(fitz.Rect(u["ink"]).y1 for u in buls) + 40
    flow, rest = [], []
    for u in us:
        r = fitz.Rect(u["ink"])
        if u["role"] == "bullet" or (u["role"] == "text"
                                     and r.x0 <= lim and lo <= r.y0 <= hi):
            flow.append(u)
        else:
            rest.append(u)
    flow.sort(key=lambda u: (u["ink"][1], u["ink"][0]))
    return flow, rest


def right_at(spage, x0, y0, y1, rest):
    """给定纵向区间内的可用右界（避开照片与图内引注）。"""
    lim = spage.rect.x1 - 36.0
    for b in spage.get_text("dict")["blocks"]:
        if b["type"] != 1:
            continue
        r = fitz.Rect(b["bbox"])
        if r.width > 0.85 * spage.rect.width:        # 母版通栏图不算障碍
            continue
        if r.x0 > x0 + 4 and r.y1 > y0 + 2 and r.y0 < y1 - 2:
            lim = min(lim, r.x0 - 5)
    for v in rest:
        r = fitz.Rect(v["ink"])
        if r.x0 > x0 + 4 and r.y1 > y0 + 2 and r.y0 < y1 - 2:
            lim = min(lim, r.x0 - 5)
    return lim


def _try_flow(spage, flow, texts, rest, k, gap, lead, top, bottom):
    out, y = [], top
    for u, zh in zip(flow, texts):
        s = max(FLOOR, u["size"] * k)
        x0 = u["tx0"]
        # 右界与高度互相依赖：先按单行估，排完再按实际高度复核一次
        xr = right_at(spage, x0, y, y + s * lead * 1.2, rest)
        wrapped = hy._cjkwrap(zh, s, xr - x0 - 1.0)
        h = (wrapped.count("\n") + 1) * s * lead
        xr2 = right_at(spage, x0, y, y + h, rest)
        if xr2 < xr - 1:
            xr = xr2
            wrapped = hy._cjkwrap(zh, s, xr - x0 - 1.0)
            h = (wrapped.count("\n") + 1) * s * lead
        if y + h > bottom:
            return None
        out.append((u, zh, fitz.Rect(x0, y, xr, y + h + 1.5), s))
        y += h + gap
    return out


def layout_flow(spage, flow, texts, rest, lead=1.32, bottom=None):
    """列表**整体重排**：条目依次紧排，间距取原版条目间距的中位值。

    为什么必须重排而不能逐条回原位（用户点名，避坑 94）：英文两三行的条目
    译成中文往往只剩一行，若各自钉在原 y 上，条目之间就留下一个个空洞；
    反之长条目折行后又压到下一条上。**原版的行距是按英文行数排的，不是
    内容的一部分** —— 内容是「条目的次序与层级」。故整列抹掉、按原起点
    自上而下重排。排不下时**先缩间距、再降字号**。

    返回 [(unit, zh, box, size)]；调用方按 `box.y0 - unit.ink[1]` 平移符号。
    """
    gaps = [b["ink"][1] - a["ink"][3] for a, b in zip(flow, flow[1:])]
    gaps = [g for g in gaps if 0 <= g < 60]
    g0 = sorted(gaps)[len(gaps) // 2] if gaps else 8.0
    top = flow[0]["ink"][1]
    bot = bottom if bottom is not None else FOOT_Y - 8
    for k in (SIZE_K, SIZE_K * .97, SIZE_K * .94, SIZE_K * .90,
              SIZE_K * .86, SIZE_K * .82, SIZE_K * .78):
        for gk in (1.0, 0.85, 0.7, 0.55, 0.42):
            plan = _try_flow(spage, flow, texts, rest, k, g0 * gk, lead, top, bot)
            if plan:
                return plan
    return _try_flow(spage, flow, texts, rest, SIZE_K * .78, g0 * .42, lead,
                     top, 1e6)


# ════════════════════════════════════════════════ 三、项目符号重绘
def bullet_ink(spage, brect, dpi=400, thr=205):
    """在**源页**上量项目符号的墨迹框与颜色，返回 (Rect, (r,g,b))。

    重排后条目上移，原版 Wingdings 字形留在原处就成了孤儿符号，只能连同
    正文一起移动。字形没法搬，但这些符号本就是**实心方块／短横** ——
    量出墨迹框与颜色后用 `draw_rect` 原样重绘，位置、大小、颜色全部照旧
    （避坑 94 之二）。⚠ 必须在**源页**上量（避坑 ㉚）。
    """
    import numpy as np
    R = (fitz.Rect(brect) + (-1, -1, 1, 1)) & spage.rect
    if R.is_empty:
        return None, None
    pm = spage.get_pixmap(dpi=dpi, clip=R)
    a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(
        pm.height, pm.width, pm.n)[:, :, :3].astype(int)
    m = a.mean(axis=2) < thr
    if not m.any():
        return None, None
    ys, xs = np.nonzero(m)
    z = dpi / 72.0
    box = fitz.Rect(R.x0 + xs.min() / z, R.y0 + ys.min() / z,
                    R.x0 + (xs.max() + 1) / z, R.y0 + (ys.max() + 1) / z)
    return box, tuple(float(v) / 255.0 for v in a[m].mean(axis=0))


# ════════════════════════════════════════════════ 四、真下标
# 化学式下标。⚠ **不能用 U+2082 等 Unicode 下标字符**（避坑 95）：微软雅黑、
# 宋体、黑体、等线**全都没有该字形**（实测 has_glyph=0；只有 Times/Segoe
# Symbol 有，但它们没有汉字）。⇒ 走真正的排版下标。
SUBPAT = re.compile(r"(?<=H)2(?=S)|(?<=CO)2(?![0-9])|(?<=H)2(?=O)|(?<=SO)[24](?![0-9])")


def subscript_pass(page, pat=SUBPAT, font="zh", fontfile=None,
                   size_k=0.70, drop=0.17):
    """把化学式里的数字改排成真下标。返回处理条数。

    做法：先把该位数字**从文本层抹掉**（`fill=None` ⇒ 只删字形、不铺白块，
    底下的版式底色原样保留），再按 0.70 倍字号、下沉 0.17 em 重画。
    ⚠ 抹除框要比字形框内缩一点，免得连带删掉紧邻的字母。
    ⚠ 改排后提取层里 `CO2` 会裂成 `CO` + 独立的 `2`，**保留项判据必须能
    容纳自己做的这个形态变更**（避坑 95 之二）——逐项确认两截都还在，
    而不是一句「豁免 CO2」了事。
    """
    hits = []
    for blk in page.get_text("rawdict")["blocks"]:
        if blk["type"] != 0:
            continue
        for ln in blk["lines"]:
            for sp in ln["spans"]:
                chars = sp.get("chars") or []
                txt = "".join(c["c"] for c in chars)
                for m in pat.finditer(txt):
                    c = chars[m.start()]
                    hits.append((fitz.Rect(c["bbox"]), c["origin"],
                                 sp["size"], sp.get("color", 0), c["c"]))
    if not hits:
        return 0
    for r, _o, _s, _c, _t in hits:
        page.add_redact_annot(r + (0.4, 0.4, -0.4, -0.4), fill=None)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)
    page.insert_font(fontname=font, fontfile=fontfile or ZH_FONT)
    for r, o, s, col, t in hits:
        c = int(col or 0)
        page.insert_text((r.x0, o[1] + drop * s), t, fontname=font,
                         fontsize=s * size_k,
                         color=((c >> 16 & 255) / 255, (c >> 8 & 255) / 255,
                                (c & 255) / 255))
    return len(hits)


# ════════════════════════════════════════════════ 五、断句体检
_TAIL = re.compile(r"\b(and|or|the|a|an|of|to|in|on|for|with|by|that|which|is|"
                   r"are|be|as|at|from|due|than|when|while|because|its|their|"
                   r"this)\s*$", re.I)
_KEEP = re.compile(r"^(\d+|[A-Z]{2,5}\d*|\d[\d,./\"'’” -]*)$")


def orphans(pages):
    """断句体检：物理断行若被当成语义边界，会留下「以小写词起头」
    「以介词/连词结尾」的残条。

    这是 V2 公理的**机器判据** —— 不做这一步，切碎的句子照样能过六道关
    （字写进去了、不缺字、不残留英文），只有读者读到才发现断在半句。
    `pages` = [{page, units:[…]}]，返回 [(页号, 原因, 文本)]。
    """
    bad = []
    for p in pages:
        for u in p["units"]:
            t = (u.get("text") or "").strip()
            if not t or u.get("role") == "foot" or _KEEP.match(t):
                continue
            why = []
            if re.match(r"^[a-z]", t) and not t.startswith(("i.e", "e.g")):
                why.append("小写起头")
            if _TAIL.search(t):
                why.append("虚词收尾")
            if why:
                bad.append((p["page"], "/".join(why), t[:90]))
    return bad
