# -*- coding: utf-8 -*-
"""**段级**叠印汉化：按段落块 redaction 英文、把整段中文写回同一矩形。

为何要有这一路线
  前 17 份里，短文档走「从零重建」（版式可控、质量最好），
  D 号图纸走「行级叠印」（线框必须原样保留）。
  但对 手册 A（118p）、马达手册族（160p）、规范 F（92p）、规范 G（43p）
  这类**长篇手册**，从零重建要把每页版式重新量一遍，工作量与页数成正比；
  而行级叠印会把一段英文拆成若干条中文碎片，读起来不成句。

  段级叠印取两者之长：**以 MuPDF 的文本块为单位**，
  把整段英文抹掉、再把整段中文按 CJK 折行写回同一矩形 ——
  版式（页眉页脚、分栏、图文位置、表格线）全部原样不动，
  中文又是通顺的整段。中文比英文紧凑约 30~40%，故原框必然放得下。

  剩下的成本只有一项：**译文本身**。这是不可压缩的。

约束
  · redaction 必须带 LINE_ART_NONE 与 IMAGE_NONE，否则与文字框相交的
    表格线、插图会被抹出缺口；
  · 段落框要按「同块内各行的并集」取，且左右按版心收敛 ——
    MuPDF 的块 bbox 有时会把行末空白也算进去；
  · 字号自适配：先按原字号试排，放不下再逐档缩小（下限 6pt），
    仍放不下才允许溢出到框外并记入报告（须人工过一遍）。
"""
import os
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

import fontkit

ZH_FONT = fontkit.find("zh")


def _norm(s):
    return " ".join(str(s or "").split())


def blocks_of(page, clip=None, min_chars=1, drop_font=None):
    """页面文本块：[(bbox, 文本, 主字号, 行数)]，按阅读顺序。

    `drop_font` 给字体名子串时，该字体的 span **在聚块前剔除** ——
    用于挡掉页面水印／徽标。与 `dwg_overlay.lines_of` 的同名参数共用
    `font_rects()` 判据，两处不要各写一套。

    为何段级也必须挡：手册 B 的徽标是真文字且与正文同 y，行级挡住后
    仍有 10 条怪键从段级漏过（`Torquing, untorquing DRILLING of`、
    `Heat internal connections to 375° DRILLING F (191° C).`）。
    """
    out = []
    d = page.get_text("dict", clip=clip)
    wm = wtok = None
    if drop_font:
        # 与行级共用 font_spans（含自校准字号闸门），不要各写一套判据
        from dwg_overlay import font_spans
        wm, wtok = font_spans(page, drop_font)
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        lines, sizes = [], []
        lboxes, lsizes = [], []          # 逐行框与逐行主字号（供跨级断开）
        x0 = y0 = 1e9
        x1 = y1 = -1e9
        for ln in b["lines"]:
            spans = ln["spans"]
            if wm:
                # **词形约束不能只加在行级**。此处原先只按位置判，
                # 33.9pt 大水印的框覆盖大半页，于是压在它上面的**整段正文**
                # 被当成水印剔掉 —— 实测剔掉了
                # 'multi-lingual due to their limited use of text.'、
                # 'When using the instructions the user should follow…' 等整段。
                # 与行级同一判据：位置命中**且**该 span 的词全是水印自身的词。
                def _hit(sp):
                    ws = sp["text"].split()
                    if not ws or any(w not in wtok for w in ws):
                        return False
                    b0 = sp["bbox"]
                    c = fitz.Point((b0[0] + b0[2]) / 2, (b0[1] + b0[3]) / 2)
                    return any(c in r for r in wm)
                keepers = [s for s in spans if not _hit(s)]
                if len(keepers) < len(spans):
                    from dwg_overlay import _WM_DROPPED
                    _WM_DROPPED.extend(s["text"].strip() for s in spans
                                       if _hit(s) and s["text"].strip())
                spans = keepers
                if not spans:
                    continue
            t = "".join(s["text"] for s in spans)
            if not t.strip():
                continue
            lines.append(t.strip())
            sizes += [s["size"] for s in spans if s["text"].strip()]
            # 剔了水印 span 就**不能再用 ln["bbox"]** —— 它仍覆盖水印区域，
            # 段框会连带把徽标一起 redaction 掉。按保留下来的 span 重算。
            if wm:
                sb = [s["bbox"] for s in spans if s["text"].strip()]
                lx0 = min(b0[0] for b0 in sb)
                ly0 = min(b0[1] for b0 in sb)
                lx1 = max(b0[2] for b0 in sb)
                ly1 = max(b0[3] for b0 in sb)
            else:
                lx0, ly0, lx1, ly1 = ln["bbox"]
            x0, y0 = min(x0, lx0), min(y0, ly0)
            x1, y1 = max(x1, lx1), max(y1, ly1)
            _ls = [s["size"] for s in spans if s["text"].strip()]
            lboxes.append((lx0, ly0, lx1, ly1))
            lsizes.append(max(set(_ls), key=_ls.count) if _ls else 10.0)
        if not lines:
            continue
        # ── 块内**字号跨级**处断开 ─────────────────────────────────
        # MuPDF 会把「表格最后一行的单元格」与其下方**字号大得多的脚注**
        # 归进同一个 block（实测 规范 F 表 7-2：8pt 单元格 `20,000` +
        # 12pt 脚注 `*When assembling…`）。合并后：
        #   · 写入框从单元格那一行起算，12pt 中文压住整行数据；
        #   · 更糟的是 redaction 按合并框执行，**整行 13 列扭矩值被抹掉**
        #     —— 五道关全绿（未命中 0／不溢出／无残留／不缺字／不重叠），
        #     只有出图目检才看得见，属「数据静默丢失」。
        # 判据用**字号比**而非绝对差：正文与其小注差 1.2 倍属正常排版，
        # 1.4 倍以上才是两类内容被误并。
        runs, cur = [], None
        for t, lb, ls in zip(lines, lboxes, lsizes):
            if cur and max(ls, cur[2]) / max(1e-6, min(ls, cur[2])) >= 1.4:
                runs.append(cur)
                cur = None
            if cur is None:
                cur = [[t], fitz.Rect(lb), ls, [ls]]
            else:
                cur[0].append(t)
                cur[1] |= fitz.Rect(lb)
                cur[3].append(ls)

        if cur:
            runs.append(cur)

        for ts, rc, _s, zs in runs:
            txt = _norm(" ".join(ts))
            if len(txt) < min_chars:
                continue
            out.append((rc, txt, max(set(zs), key=zs.count), len(ts)))
    return _join_wordblocks(out)


def _join_wordblocks(out, gapf=0.5):
    """把 MuPDF 拆成**逐词**的单行块接回整行。

    手册 A 第 6 页的正文段是**逐词定位**排出来的（两端对齐由显式坐标
    实现），MuPDF 于是把一行拆成 12 个 block —— `The` / `disassembly` /
    `and` / `assembly` / `instructions`…。每个词各自成为待译单元、
    各自查词表、各自写进自己那只窄框里，渲染出来就是
    「该　拆卸　　与　总成　　说明　　提供　详细的　维修　说明」：
    词序照抄英文、词间空得老远，一眼就是机翻。

    判据：**同基线、同字号、且词间空隙小于半个字号**（实测这里空隙
    只有 1.0pt ≈ 0.1 字号）。空隙门槛不能放宽 —— 页脚左右两端的文字
    也同基线同字号，放宽就会被接成一条。
    """
    single = [i for i, (_r, _t, _s, n) in enumerate(out) if n == 1]
    used, merged = set(), []
    for i in single:
        if i in used:
            continue
        r0, t0, s0, _n = out[i]
        grp = [(r0.x0, i)]
        for j in single:
            if j == i or j in used:
                continue
            rj, _tj, sj, _nj = out[j]
            if (abs(rj.y0 - r0.y0) <= 1.2 and abs(rj.y1 - r0.y1) <= 1.2
                    and abs(sj - s0) <= 0.3):
                grp.append((rj.x0, j))
        if len(grp) < 2:
            continue
        grp.sort()
        run, prev = [grp[0]], out[grp[0][1]][0].x1
        for x0, j in grp[1:]:
            if x0 - prev <= gapf * s0:
                run.append((x0, j))
            elif len(run) > 1:
                break
            else:
                run, = [[(x0, j)]]
            prev = out[j][0].x1
        if len(run) < 2:
            continue
        rc = fitz.Rect(out[run[0][1]][0])
        for _x, j in run[1:]:
            rc |= out[j][0]
        txt = " ".join(out[j][1] for _x, j in run)
        used |= {j for _x, j in run}
        merged.append((min(j for _x, j in run), (rc, txt, s0, 1)))
    if not merged:
        return out
    res = [b for i, b in enumerate(out) if i not in used]
    res += [b for _i, b in merged]
    return res


class BlockOverlay:
    """收集「段落矩形 → 中文段」，最后一次性落到页面上。"""

    def __init__(self, page, font="zh", fontfile=ZH_FONT):
        self.page, self.font, self.fontfile = page, font, fontfile
        self.items = []
        self.overflow = []

    def add(self, rect, text, size, align=0, leading=1.28):
        self.items.append((fitz.Rect(rect), text, size, align, leading))

    def apply(self, pad=0.6, floor=6.0):
        pg = self.page
        if not self.items:
            return 0
        for rect, *_ in self.items:
            pg.add_redact_annot(rect + (-pad, -pad, pad, pad))
        pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                            graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        pg.insert_font(fontname=self.font, fontfile=self.fontfile)
        n = 0
        from dwg_overlay import _width          # 与写入端同源的度量
        for rect, text, size, align, leading in self.items:
            if not text:
                continue
            # 允许向下多用 2pt：中文行高比英文略高，末行常差一点点
            box = fitz.Rect(rect.x0 - 0.4, rect.y0 - 1.0,
                            rect.x1 + 0.4, rect.y1 + 2.0)
            # **先量后画，只画一次。** 与 dwg_overlay 同一个坑：
            # insert_textbox 放不下时一字不写、也不报错；原先「画一次、rc<0
            # 再缩号画第二次」会把第二次叠在第一次的残迹上。
            # 段落是多行，故按「所需行数 × 行高」估高度：
            #   行数 ≈ ceil(串宽 / 框宽)，单行占用 ≈ 1.58 × 字号。
            s = size
            while s > floor:
                w = _width(text, s)
                lines = max(1, int(w / max(box.width - 1.0, 1.0)) + 1)
                if lines * s * 1.60 <= box.height - 0.3:
                    break
                s -= 0.3
            rc = pg.insert_textbox(box, text, fontname=self.font,
                                   fontsize=s, align=align,
                                   lineheight=leading, color=(0, 0, 0))
            if rc < 0:
                self.overflow.append((_norm(text)[:60], round(s, 1)))
            n += 1
        return n


def translate_page(page, lookup, keep=None, clip=None, align=0):
    """按 lookup(英文段) → 中文段 逐段叠印。

    lookup 返回 None 表示未命中（记入报告）、"" 表示显式保留原文。
    返回 (已译段数, 未命中清单, 溢出清单)。
    """
    ov = BlockOverlay(page)
    miss = []
    for rect, txt, sz, nline in blocks_of(page, clip):
        if keep and keep(txt):
            continue
        zh = lookup(txt)
        if zh is None:
            miss.append(txt)
            continue
        if zh == "":
            continue
        ov.add(rect, zh, sz, align=align)
    n = ov.apply()
    return n, miss, ov.overflow


def build(src, dst, lookup, keep=None, clip=None, verbose=True):
    doc = fitz.open(src)
    tot, allmiss, allover = 0, [], []
    for i, page in enumerate(doc, 1):
        n, miss, over = translate_page(page, lookup, keep, clip)
        tot += n
        allmiss += [(i, m) for m in miss]
        allover += [(i,) + o for o in over]
        if verbose:
            print(f"   页 {i}: 叠印 {n} 段，未命中 {len(miss)}，溢出 {len(over)}")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    doc.save(dst, garbage=3, deflate=True)
    doc.close()
    return tot, allmiss, allover


def dump_blocks(src, out_txt, clip=None):
    """把全书段落导出为可翻译清单：每段一条，带页号与字号。

    这是段级叠印的**唯一人工输入**：照此清单逐段给中文即可，
    版式一概不用管。
    """
    doc = fitz.open(src)
    n = 0
    with open(out_txt, "w", encoding="utf-8") as f:
        for i, page in enumerate(doc, 1):
            f.write(f"\n### PAGE {i}\n")
            for rect, txt, sz, nl in blocks_of(page, clip):
                n += 1
                f.write(f"[{sz:>4.1f} x{nl}] {txt}\n")
    doc.close()
    return n
