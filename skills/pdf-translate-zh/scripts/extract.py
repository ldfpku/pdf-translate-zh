# -*- coding: utf-8 -*-
"""素材提取层（与文档无关，换文档不用改）。

一次跑完：结构勘察 → 逐页渲染 → 表格几何抽取 → 插图纯净剪裁 + 图内英文
redaction → 修订标记提取 → 拼贴核验图。

用法
    python extract.py <input.pdf> <workdir> [--dpi 300]

产出 <workdir>/
    data/page_probe.json   每页尺寸/字数/图数/矢量数
    data/blocks.json       文本块(含字号/粗体/bbox)
    data/text_dump.txt     人读文本转储
    data/prose_dump.txt    剔除表格区域后的纯正文（通读用，体积小很多）
    data/tables_raw.json   表格网格
    data/tables_readable.txt
    data/figures.json      插图清单(bbox / dpi / 被抹除的英文标注及其坐标)
    data/marks.json        修订高亮与页边变更条
    figures/*.png          纯净剪裁的插图
    qa/contact_*.png       拼贴核验图（必须目检一次）

避坑要点全部固化在代码里，逐条见行内注释与 SKILL.md 的「避坑清单」。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse, json, os, re, sys
from collections import Counter

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz
import numpy as np

# ---------------------------------------------------------------- 参数
TOP, BOT = 68.0, 725.0            # 版心上下界（排除页眉页脚），按文档调整
LEFT, RIGHT = 40.0, 580.0
BLOCK_SZ = 9.6                    # ≥此字号视为「真实文本行」
NUMERIC = re.compile(r"^(?:\(?\d{1,2}\)?|[A-K])$")   # 件号气泡 / 尺寸字母：不译
CAPTION_RE = re.compile(r"^(Figure|Table|图|表)\s*\d+[-.]\d+")


# ================================================================ 工具
def merge_runs(vals, tol=3.0):
    out = []
    for v in sorted(vals):
        if out and v - out[-1] <= tol:
            continue
        out.append(v)
    return out


def body_margins(doc, min_hits=20):
    """全书正文/标题的左边界取值集合。
    这些位置固定，而图内标注随图摆放落不到这些值上 ——
    这是区分「正文行」与「图内标注」最稳的信号。"""
    cnt = Counter()
    for page in doc:
        for blk in page.get_text("dict")["blocks"]:
            if blk["type"] != 0:
                continue
            for ln in blk["lines"]:
                if max(s["size"] for s in ln["spans"]) >= BLOCK_SZ:
                    cnt[round(ln["bbox"][0])] += 1
    return {x for x, n in cnt.items() if n >= min_hits}


def detect_revbar_band(doc):
    """自动确定「页边修订变更条」所在的 x 窄带。

    关键：表格右边框几乎贴在版心右界上（实测 539.9 vs 540），
    阈值一旦放宽到版心之内，每张表的右边框都会被当成变更条。
    因此只在【版心右界之外】找候选，并要求其 x 值高度集中。"""
    cnt = Counter()
    for page in doc:
        for d in page.get_drawings():
            r = fitz.Rect(d["rect"])
            if r.width < 3.5 and r.height >= 8 and r.x0 > RIGHT - 38:
                cnt[round(r.x0)] += 1
    if not cnt:
        return None
    xs = [x for x, n in cnt.items() if n >= 2]
    return (min(xs) - 2.0, max(xs) + 2.0) if xs else None


def scan_revbars(page, band):
    """扫出该页的修订变更条并合并相邻段。
    坑：变更条常是零宽描边线 —— Rect.intersects()/get_area() 对零面积矩形
    恒为假，必须纯坐标比较；单段最短实测 11.5pt，高度阈值取 8 才不漏。"""
    if not band:
        return []
    x0, x1 = band
    segs = []
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if not (x0 <= r.x0 <= x1) or r.width > 3.5 or r.height < 8:
            continue
        if not (TOP - 8 < r.y0 and r.y1 < BOT + 8):
            continue
        segs.append([r.y0, r.y1])
    if not segs:
        return []
    segs.sort()
    out = [segs[0]]
    for a, b in segs[1:]:
        if a <= out[-1][1] + 2.0:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[round(x0, 2), round(a, 2), round(x0, 2), round(b, 2)] for a, b in out]


def gfx_above(r, gfx, reach=60.0):
    """文本行上方 reach 内是否有横向重叠的图元。
    下界取到「文本行底部」：图形常与其下方的零件名纵向交叠 2~3pt，
    若只认「图底 ≤ 名顶」，最下一排零件名会被误判为正文而被裁掉。"""
    for g in gfx:
        if min(g.x1, r.x1) - max(g.x0, r.x0) <= 1:
            continue
        if r.y0 - reach <= g.y1 <= r.y1 + 2:
            return True
    return False


def trim_edges(clusters, blocking):
    """只修剪压在上/下边沿的正文行；夹在图形中间的留给 redaction，
    否则会把插图腰斩。"""
    for c in clusters:
        for _ in range(10):
            b = c["bbox"]
            band = max(0.18 * b.height, 14.0)
            hit = False
            for t in blocking:
                if (t & b).get_area() <= 0.4 * max(t.get_area(), 1):
                    continue
                if t.y0 <= b.y0 + band:
                    c["bbox"] = fitz.Rect(b.x0, t.y1 + 1.5, b.x1, b.y1)
                    hit = True
                    break
                if t.y1 >= b.y1 - band:
                    c["bbox"] = fitz.Rect(b.x0, b.y0, b.x1, t.y0 - 1.5)
                    hit = True
                    break
            if not hit or c["bbox"].height < 12:
                break


# ================================================================ 各阶段
def probe(doc, out):
    rows = []
    for i, page in enumerate(doc):
        txt = page.get_text()
        rows.append(dict(page=i + 1, w=round(page.rect.width, 1),
                         h=round(page.rect.height, 1), rot=page.rotation,
                         chars=len(txt.strip()), n_img=len(page.get_images()),
                         n_draw=len(page.get_drawings()),
                         first=(txt.strip().splitlines() or [""])[0][:70]))
    json.dump(rows, open(f"{out}/data/page_probe.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return rows


def render_and_dump(doc, out, dpi=150):
    pages = []
    for i, page in enumerate(doc):
        page.get_pixmap(dpi=dpi).save(f"{out}/render/p{i+1:03d}.png")
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                blocks.append(dict(kind="image",
                                   bbox=[round(v, 1) for v in b["bbox"]]))
                continue
            lines = []
            for ln in b["lines"]:
                spans = [dict(t=s["text"], sz=round(s["size"], 1), f=s["font"],
                              c=s["color"], bbox=[round(v, 1) for v in s["bbox"]])
                         for s in ln["spans"] if s["text"].strip()]
                if spans:
                    lines.append(dict(bbox=[round(v, 1) for v in ln["bbox"]],
                                      spans=spans))
            if lines:
                blocks.append(dict(kind="text",
                                   bbox=[round(v, 1) for v in b["bbox"]],
                                   lines=lines))
        pages.append(dict(page=i + 1, blocks=blocks))
    json.dump(pages, open(f"{out}/data/blocks.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(f"{out}/data/text_dump.txt", "w", encoding="utf-8") as f:
        for p in pages:
            f.write(f"\n{'='*78}\n### PAGE {p['page']}\n{'='*78}\n")
            for b in p["blocks"]:
                if b["kind"] == "image":
                    f.write(f"[IMAGE {b['bbox']}]\n")
                    continue
                for ln in b["lines"]:
                    t = "".join(s["t"] for s in ln["spans"])
                    sz = ln["spans"][0]["sz"]
                    bold = "B" if any("Bold" in s["f"] for s in ln["spans"]) else " "
                    f.write(f"  [{sz:>4} {bold}] {t}\n")
    return pages


def extract_tables(doc, out):
    """几何法抽表 + 剔除表格区域后的纯正文转储。

    伪表过滤：插图里的矩形线框常被 find_tables 误判为表格，一旦误判，
    该区域的矢量图元会被当成表格线剔除，**整幅插图静默消失**。
    真表格的单元格填充率显著更高。"""
    all_t, prose = [], []
    for i, page in enumerate(doc):
        pno = i + 1
        rects = []
        try:
            tabs = page.find_tables(strategy="lines_strict").tables
        except Exception:
            tabs = []
        for ti, t in enumerate(tabs):
            clean = [[(c or "").replace("\n", " ").strip() for c in row]
                     for row in t.extract()]
            n_cells = sum(len(r) for r in clean)
            n_full = sum(1 for r in clean for c in r if c)
            if n_full < 4 or n_full / max(n_cells, 1) < 0.15:
                continue
            r = fitz.Rect(t.bbox)
            rects.append(r)
            all_t.append(dict(page=pno, idx=ti, bbox=[round(v, 1) for v in r],
                              rows=len(clean),
                              cols=max(len(x) for x in clean), data=clean))
        lines_out = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                lr = fitz.Rect(ln["bbox"])
                if any(lr.intersects(tr)
                       and (lr & tr).get_area() > 0.5 * lr.get_area()
                       for tr in rects):
                    continue
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if txt:
                    lines_out.append((round(ln["spans"][0]["size"], 1),
                                      "B" if any("Bold" in s["font"]
                                                 for s in ln["spans"]) else " ",
                                      txt))
        prose.append((pno, len(rects), lines_out))

    json.dump(all_t, open(f"{out}/data/tables_raw.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(f"{out}/data/prose_dump.txt", "w", encoding="utf-8") as f:
        for pno, nt, lines in prose:
            f.write(f"\n### PAGE {pno}   (tables on page: {nt})\n")
            for sz, bold, txt in lines:
                f.write(f"  [{sz:>4}{bold}] {txt}\n")
    with open(f"{out}/data/tables_readable.txt", "w", encoding="utf-8") as f:
        for t in all_t:
            f.write(f"\n{'='*100}\n@@ PAGE {t['page']}  table#{t['idx']}  "
                    f"{t['rows']}x{t['cols']}  bbox={t['bbox']}\n")
            for ri, row in enumerate(t["data"]):
                f.write(f"  r{ri:02d} | " +
                        " | ".join(c if c else "·" for c in row) + "\n")
    return all_t


def extract_figures(doc, out, tables, base_dpi=300):
    """插图纯净剪裁 + 图内矢量英文 redaction。"""
    # 重新裁图后，figlabel.apply_figures_json 的干净底图备份即作废
    import shutil
    shutil.rmtree(os.path.join(out, "figures", "_clean"), ignore_errors=True)
    tbl_by_page = {}
    for t in tables:
        tbl_by_page.setdefault(t["page"], []).append(fitz.Rect(t["bbox"]))

    BODY_X = body_margins(doc)
    band = detect_revbar_band(doc)
    manifest, hl_all, rev_all = [], {}, {}
    clip_area = fitz.Rect(LEFT, TOP, RIGHT, BOT)
    CLIP_AREA = clip_area.get_area()

    # 页序号变量刻意起名 PAGE_IDX：曾两次被内层 `for i, ...` 覆盖，
    # 导致 insert_pdf 取到错误页面，产出「图张冠李戴」且尺寸完全正常。
    for PAGE_IDX, page in enumerate(doc):
        pno = PAGE_IDX + 1
        tbls = tbl_by_page.get(pno, [])
        gfx, hilites = [], []
        revbars = scan_revbars(page, band)

        def is_white(c):
            return c is not None and min(c) > 0.95

        for d in page.get_drawings():
            r = fitz.Rect(d["rect"])
            # 纯坐标比较：零面积线段用 intersects() 会被整条丢掉
            if not (r.x1 > LEFT and r.x0 < RIGHT and r.y1 > TOP and r.y0 < BOT):
                continue
            f = d.get("fill")
            if f is not None and f[0] > 0.85 and f[1] > 0.7 and f[2] < 0.35:
                hilites.append([round(v, 2) for v in r])       # 修订高亮
                continue
            # Word/Visio 画布：纯白填充且无可见描边的巨型不可见矩形
            if is_white(f) and (d.get("color") is None or is_white(d.get("color"))):
                continue
            if band and band[0] <= r.x0 <= band[1] and r.width < 3.5:
                continue
            r = r & clip_area
            if r.width < 0.4 and r.height < 0.4:
                continue
            if r.get_area() < 1:
                # 零面积线段：矢量图的**引线**正是这一类。旧版一律丢弃，引线不进
                # 图元簇 → 引线末端的标注吸附不到 → 裁框腰斩标签、标注滞留正文
                # （避坑 112）。保留 ≥ 6pt 的短线段并加 0.5pt 厚度；跨版心的
                # 长横线是分隔线，照旧丢弃。
                if max(r.width, r.height) < 6 or r.width > 0.6 * clip_area.width:
                    continue
                r = r + (-0.5, -0.5, 0.5, 0.5)
            if r.get_area() > 0.35 * CLIP_AREA:
                continue
            gfx.append(r)
        if hilites:
            hl_all[pno] = hilites
        if revbars:
            rev_all[pno] = revbars
        for blk in page.get_text("dict")["blocks"]:
            if blk["type"] == 1:
                r = fitz.Rect(blk["bbox"]) & clip_area
                if r.get_area() > 4:
                    gfx.append(r)

        # 单元格分隔线是零面积矩形，必须用「含于」而非面积比判断
        def inside_table(r, pad=2.0):
            return any(r.x0 >= tb.x0 - pad and r.x1 <= tb.x1 + pad and
                       r.y0 >= tb.y0 - pad and r.y1 <= tb.y1 + pad for tb in tbls)

        gfx = [r for r in gfx if not inside_table(r)]
        if not gfx:
            continue

        # ---- 文本行分类 ----
        raw_lines = []
        for blk in page.get_text("dict")["blocks"]:
            if blk["type"] != 0:
                continue
            for ln in blk["lines"]:
                r = fitz.Rect(ln["bbox"])
                if not r.intersects(clip_area):
                    continue
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if not txt:
                    continue
                raw_lines.append(dict(
                    r=r, txt=txt, sz=max(s["size"] for s in ln["spans"])))
        raw_lines.sort(key=lambda it: (it["r"].y0, it["r"].x0))

        cap_idx = set()
        for li, it in enumerate(raw_lines):
            if CAPTION_RE.match(it["txt"]):
                cap_idx.add(li)
                for j in range(li + 1, len(raw_lines)):
                    nx = raw_lines[j]
                    if (abs(nx["sz"] - it["sz"]) < 0.6
                            and 0 <= nx["r"].y0 - raw_lines[j - 1]["r"].y1 < 6):
                        cap_idx.add(j)
                    else:
                        break

        blocking, small, big = [], [], []
        for li, it in enumerate(raw_lines):
            r, sz = it["r"], it["sz"]
            # 图内标注三条同时成立：非图题、左界不在正文固定左界、上方近处有图元。
            # 不能要求「上下都有图元」——最下一排零件名下方本就没有图形。
            in_fig = (sz >= BLOCK_SZ and not inside_table(r)
                      and li not in cap_idx
                      and round(r.x0) not in BODY_X
                      and gfx_above(r, gfx))
            if (sz >= BLOCK_SZ or inside_table(r)) and not in_fig:
                blocking.append(r)
                big.append(it)
            else:
                small.append(it)

        def on_body_text(r):
            if r.get_area() > 900:
                return False
            return any((r & b).get_area() > 0.55 * r.get_area() for b in blocking
                       if r.get_area() > 0)

        gfx = [r for r in gfx if not on_body_text(r)]
        if not gfx:
            continue

        # ---- 纵向聚类（禁止跨越真实文本行）----
        gfx.sort(key=lambda r: (r.y0, r.x0))
        clusters = []
        for r in gfx:
            for c in clusters:
                cb = c["bbox"]
                if r.y0 <= cb.y1 + 26:
                    g0, g1 = min(cb.y1, r.y0), max(cb.y1, r.y0)
                    if not any(b.y0 > g0 - 1.5 and b.y1 < g1 + 1.5 and g1 - g0 > 3
                               for b in blocking):
                        c["bbox"] |= r
                        break
            else:
                clusters.append(dict(bbox=fitz.Rect(r)))
        changed = True
        while changed:
            changed, out_c = False, []
            for c in clusters:
                for o in out_c:
                    if c["bbox"].intersects(o["bbox"]) or \
                            abs(c["bbox"].y0 - o["bbox"].y1) < 4:
                        o["bbox"] |= c["bbox"]
                        changed = True
                        break
                else:
                    out_c.append(dict(bbox=fitz.Rect(c["bbox"])))
            clusters = out_c
        clusters = [c for c in clusters
                    if c["bbox"].width > 24 and c["bbox"].height > 14]

        for c in clusters:                       # 吸附图内小号标注
            for _ in range(3):
                b = c["bbox"]
                # 纵向 24pt：图下方无引线的注记（「Flow direction →」「Max. OD」）
                # 常离图形 17~20pt，旧值 16pt 够不着，注记滞留正文（避坑 112）
                probe_r = fitz.Rect(b.x0 - 60, b.y0 - 24, b.x1 + 60, b.y1 + 24)
                for s in small:
                    if s["r"].intersects(probe_r) and not any(
                            s["r"].intersects(o["bbox"]) and o is not c
                            for o in clusters):
                        c["bbox"] |= s["r"]
        for c in clusters:
            c["bbox"] &= clip_area
            for tb in tbls:                       # 与表格重叠部分纵向裁掉
                b = c["bbox"]
                if not b.intersects(tb) or (b & tb).height < 1:
                    continue
                if b.y0 >= tb.y0 - 1 and b.y1 > tb.y1:
                    c["bbox"] = fitz.Rect(b.x0, tb.y1 + 1.0, b.x1, b.y1)
                elif b.y1 <= tb.y1 + 1 and b.y0 < tb.y0:
                    c["bbox"] = fitz.Rect(b.x0, b.y0, b.x1, tb.y0 - 1.0)

        # 顺序要点：先修边、后拼接、再复修边。反过来会因簇框里残留正文
        # 而使「合并后不吞文本」判据永远失败，同一幅图始终被拆成两半。
        trim_edges(clusters, blocking)
        changed = True
        while changed:
            changed = False
            clusters.sort(key=lambda c: c["bbox"].y0)
            for k in range(len(clusters) - 1):
                ra, rb = clusters[k]["bbox"], clusters[k + 1]["bbox"]
                if rb.y0 - ra.y1 > 120:
                    continue
                box = ra | rb
                lo, hi = ra.y1 - 1, rb.y0 + 1
                if any(t.y1 > lo and t.y0 < hi for t in blocking):
                    continue
                if any(box.intersects(t)
                       and (box & t).get_area() > 0.4 * max(t.get_area(), 1)
                       for t in blocking):
                    continue
                clusters[k]["bbox"] = box
                clusters.pop(k + 1)
                changed = True
                break
        trim_edges(clusters, blocking)

        # 离图 ≤ 40pt 却没被吸附的小号文字：多半是图注/图内说明，提醒人工归属
        for s_ in small:
            if any(s_["r"].intersects(fitz.Rect(c["bbox"]) + (-40, -40, 40, 40))
                   and not s_["r"].intersects(c["bbox"]) for c in clusters) \
                    and not CAPTION_RE.match(s_["txt"]):
                print(f"  注意 p{pno} 图旁小号文字未并入插图（译文须另行安置）："
                      f"{s_['txt'][:40]!r}")

        # ---- redaction + 渲染 ----
        for idx, c in enumerate(clusters, 1):
            b = c["bbox"]
            if b.width < 30 or b.height < 20:
                continue
            keep = [s for s in small
                    if (s["r"] & b).get_area() >= 0.55 * s["r"].get_area()
                    and NUMERIC.match(s["txt"])]
            redact = [s for s in small
                      if (s["r"] & b).get_area() >= 0.55 * s["r"].get_area()
                      and not NUMERIC.match(s["txt"])]
            redact += [s for s in big
                       if (s["r"] & b).get_area() >= 0.4 * max(s["r"].get_area(), 1)]

            work = fitz.open()
            work.insert_pdf(doc, from_page=PAGE_IDX, to_page=PAGE_IDX)
            wp = work[0]
            # 去重：原版常把同一标注按不同字号叠印数份，英文完全重合看不出，
            # 换成中文后宽度不同即露出双影。判据：文本相同且位置相差 < 3pt。
            best = {}
            for s in redact:
                wp.add_redact_annot(fitz.Rect(s["r"]) + (-0.6, -0.6, 0.6, 0.6))
                key = (" ".join(s["txt"].split()),
                       round(s["r"].x0 / 3.0), round(s["r"].y0 / 3.0))
                if key not in best or s["sz"] > best[key]["sz"]:
                    best[key] = s
            labels = [dict(text=s["txt"], size=round(s["sz"], 2),
                           x=round(s["r"].x0 - b.x0, 2),
                           y=round(s["r"].y0 - b.y0, 2),
                           w=round(s["r"].width, 2), h=round(s["r"].height, 2))
                      for s in sorted(best.values(),
                                      key=lambda s: (s["r"].y0, s["r"].x0))]
            if redact:
                wp.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                    graphics=fitz.PDF_REDACT_LINE_ART_NONE)
            # 自适应分辨率：工程图常见 0.12pt 发丝线，小图按 300dpi 渲染时
            # 线宽不足 1 像素会被抗锯齿糊成浅灰（目检表现为「发虚」）
            dpi = base_dpi if b.width >= 250 else (450 if b.width >= 120 else 600)
            z = dpi / 72.0
            name = f"fig_p{pno:03d}_{idx}.png"
            wp.get_pixmap(clip=b, matrix=fitz.Matrix(z, z), alpha=False)\
              .save(f"{out}/figures/{name}")
            work.close()
            manifest.append(dict(page=pno, idx=idx, file=name,
                                 bbox=[round(v, 2) for v in b],
                                 w_pt=round(b.width, 2), h_pt=round(b.height, 2),
                                 dpi=dpi, labels=labels,
                                 kept_numbers=[s["txt"] for s in keep]))

    json.dump(manifest, open(f"{out}/data/figures.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(dict(highlights=hl_all, revbars=rev_all, revbar_band=band),
              open(f"{out}/data/marks.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return manifest


def contact_sheets(out, manifest, cols=10, cell=300):
    from PIL import Image, ImageDraw, ImageFont
    import math
    import fontkit
    f = fontkit.pil("mono", 14)

    def sheet(items, path):
        rows = math.ceil(len(items) / cols)
        sh = Image.new("RGB", (cols * (cell + 8) + 8, rows * (cell + 30) + 8),
                       "white")
        d = ImageDraw.Draw(sh)
        for k, m in enumerate(items):
            r, c = divmod(k, cols)
            x, y = 8 + c * (cell + 8), 8 + r * (cell + 30)
            im = Image.open(f"{out}/figures/{m['file']}").convert("RGB")
            im.thumbnail((cell, cell), Image.LANCZOS)
            d.rectangle([x, y + 22, x + cell, y + 22 + cell],
                        outline=(200, 200, 200))
            sh.paste(im, (x + (cell - im.width) // 2,
                          y + 22 + (cell - im.height) // 2))
            d.text((x + 2, y + 3),
                   f"p{m['page']}#{m['idx']} L{len(m['labels'])}"
                   f" N{len(m['kept_numbers'])}", fill=(180, 0, 0), font=f)
        sh.save(path)
        return path

    # 每张至多 40 幅（旧版固定对半分：只有 1 幅图时 contact_B 是一张 3088×8 的空白条）
    import glob as _g
    for old in _g.glob(f"{out}/qa/contact_*.png"):
        os.remove(old)
    per = 40
    out_paths = []
    for k in range(0, len(manifest), per):
        tag = chr(ord("A") + k // per) if k // per < 26 else str(k // per)
        out_paths.append(sheet(manifest[k:k + per], f"{out}/qa/contact_{tag}.png"))
    return out_paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("workdir")
    ap.add_argument("--dpi", type=int, default=300)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for sub in ("data", "figures", "render", "qa"):
        os.makedirs(os.path.join(a.workdir, sub), exist_ok=True)

    doc = fitz.open(a.pdf)
    print(f"页数 {doc.page_count}  TOC 书签 {len(doc.get_toc())} 条")
    probe(doc, a.workdir)
    render_and_dump(doc, a.workdir)
    tables = extract_tables(doc, a.workdir)
    print(f"表格 {len(tables)} 张")
    figs = extract_figures(doc, a.workdir, tables, a.dpi)
    print(f"插图 {len(figs)} 幅")
    for p in contact_sheets(a.workdir, figs):
        print("拼贴核验图:", p)
    print("\n下一步：目检 qa/contact_*.png，再通读 data/prose_dump.txt 与 "
          "data/tables_readable.txt 编写内容层。")


if __name__ == "__main__":
    main()
