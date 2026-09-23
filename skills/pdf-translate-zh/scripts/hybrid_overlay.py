# -*- coding: utf-8 -*-
"""混合叠印：表格区走**行级**、其余走**段级**。

这是长篇手册（手册 A 118p、马达手册族、规范 F 92p、规范 G 43p、手册 I 20p）
的装配路线。两种粒度必须分区，理由已实测：

  · 段级用在表格上会毁掉列对齐 —— MuPDF 的文本块把表格**一整行的各列并成
    一个块**（实测 手册 I 第 20 页：`2-7/8"- 3 ½" 100 100 90 80 60 50 0-30 NA`
    是一个块），按块 redaction 再写中文，列就全乱了。
  · 行级用在散文上会把一段英文拆成若干条中文碎片，读起来不成句。

分区判据：先用 `find_tables` 圈出表格 bbox，再对每个文本块判「是否落在某个
表格 bbox 内」。落在表内 → 该区域交给行级；否则 → 段级。
`find_tables` 的伪表要滤掉（SKILL 避坑 ③：插图里的矩形线框常被误判为表格，
一旦误判，该区域的图元会被当成表格线剔除）—— 判据沿用 extract.py：
有效单元格 < 4 或填充率 < 15% 判为非表。
"""
import math
import re

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

import dwg_overlay as dov
import text_overlay as tov


def table_rects_grid(page, min_rows=3, tol=2.5, min_w=40.0):
    """**按线框几何自求表格区** —— 不依赖 `find_tables`。

    为什么必须自求：`find_tables` 在工程文档上已三次不可信 ——
      · 图纸族 J 图纸：把整张图纸判成一个大表，顺带丢掉 NOTES 列；
      · 服务报告：把整页并成一格；
      · 马达手册族：**严重漏检**（实测第 33 页有 178 条水平线却
        一张表都没认出，第 2/34/35 页同为 0，第 6 页有 127 条垂直线只认 1 张）。
    漏检的后果最隐蔽：表格行会被送进段级通道，各列并成一条，
    译文键全错（如 `240 11, 12 7,750 ft-lbs (10,510 Nm) 250` 并成一串）。

    办法沿用 `dwg_bom.py` 那套（已在 图纸族 J 图纸 12 页 148 行零误差验证）：
    下潜到路径 item 取线段 → 合并共线相接的短段 → 按 x 跨度把水平线聚成族 →
    每族 ≥ min_rows 条即认定为一个表格区。
    """
    from dwg_bom import segments
    H, _V = segments(page, min_h=min_w, min_v=6.0)
    # 注意：这里**保留**图框线。图纸整页因此落进「表格区」、全部走行级通道 ——
    # 这正是图纸需要的（段级通道会把相隔 300pt 的「6-5/8 REG PIN」「… BOX」并成
    # 一条）。只有 tablefix.regions() 需要剔除图框线（避坑 118）。
    if not H:
        return []
    # 按 x 区间重叠把水平线聚族（同一张表的各行线 x 跨度基本一致）
    lines = sorted(H, key=lambda h: h[0])          # 按 y
    groups = []
    for y, x0, x1 in lines:
        for g in groups:
            gx0, gx1 = g["x0"], g["x1"]
            ov = min(gx1, x1) - max(gx0, x0)
            if ov > 0.55 * min(gx1 - gx0, x1 - x0):
                g["x0"], g["x1"] = min(gx0, x0), max(gx1, x1)
                g["ys"].append(y)
                break
        else:
            groups.append(dict(x0=x0, x1=x1, ys=[y]))
    out = []
    for g in groups:
        if len(g["ys"]) < min_rows:
            continue
        out.append(fitz.Rect(g["x0"] - tol, min(g["ys"]) - tol,
                             g["x1"] + tol, max(g["ys"]) + tol))
    # 合并相交的表格区
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if out[i].intersects(out[j]):
                    out[i] |= out[j]
                    out.pop(j)
                    changed = True
                    break
            if changed:
                break
    return out


def table_rects_ft(page, min_cells=4, min_fill=0.15):
    """真表格的 bbox 列表。伪表按「单元格数 + 填充率」滤除。"""
    out = []
    try:
        tabs = page.find_tables(strategy="lines_strict").tables
    except Exception:
        return out
    for t in tabs:
        try:
            data = t.extract()
        except Exception:
            continue
        cells = sum(len(r) for r in data)
        full = sum(1 for r in data for c in r if (c or "").strip())
        if full < min_cells or full / max(cells, 1) < min_fill:
            continue
        out.append(fitz.Rect(t.bbox))
    return out


def table_rects(page, **kw):
    """表格区 = 线框几何自求 ∪ find_tables 认出的（取并集，宁多勿漏）。

    漏检的代价（表格行并成一条、译文键全错）远大于多划一块的代价
    （多划只是让该块走行级，行级对散文只是分得细些，不会毁版式）。
    """
    out = table_rects_grid(page, **kw)
    for r in table_rects_ft(page):
        if not any(r.intersects(o) for o in out):
            out.append(r)
    return out


def _inside(r, rects, frac=0.6):
    for t in rects:
        inter = r & t
        if inter.get_area() >= frac * max(r.get_area(), 0.01):
            return True
        # 零面积（单行）用坐标含于判断（避坑 ④）
        if (r.x0 >= t.x0 - 2 and r.x1 <= t.x1 + 2
                and r.y0 >= t.y0 - 2 and r.y1 <= t.y1 + 2):
            return True
    return False


class derotated:
    """临时把页面 `/Rotate` 归零，在**同一坐标系**内完成提取与写入。

    这是 `/Rotate≠0` 页面唯一可靠的处理办法，实测教训如下：
    手册 C 第 31/37 页 `/Rotate=90`（存储为纵开、显示为横开）。MuPDF 的
    `ln["dir"]` 报的是**未旋转空间**的方向，于是：

      · 显示为水平的文字 → 报 dir=(0,-1)
      · 显示为竖排的文字 → 报 dir=(1,0)

    **与直觉完全相反。** 我据 dir 判断转角，结果把本已水平的中文又转了 90°，
    又把真正竖排的中文写成了水平 —— 渲染出来满页倒字（且四道关全绿，
    因为文字确实写进去了、字号也够，只是方向错）。

    归零后读写同处一个空间，全部水平逻辑原样可用；退出时恢复 `/Rotate`，
    显示效果与原版一致。**凡按 dir 判方向的代码都必须在本上下文内运行。**
    """

    def __init__(self, page):
        self.page = page
        self.rot = 0

    def __enter__(self):
        self.rot = self.page.rotation
        if self.rot:
            self.page.set_rotation(0)
        return self.page

    def __exit__(self, *exc):
        if self.rot:
            self.page.set_rotation(self.rot)
        return False


# ── 排版记号（写入前解释，不进词表键）─────────────────────────────
# 词表的值里可以带两个控制字符，用来表达叠印路线本来做不到的排版：
#   `` 打头  → 该条**居中**（原版的居中标题：中文更短，
#                   左对齐写出来会整体左偏，与原版不同源）
#   `` 分隔  → **点引线右对齐**：左段贴左、右段贴右，中间用点填满
#                   （目录条目 `标题 …… 文件编号` 的原版做法）
# 两者都要在**字号定下来之后**才能算，故只能在写入循环里解释。
CENTER = ""
LEADER = ""
RALIGN = '\x03'
RIGHT = '\x04'   # 整条右对齐（目录页码列）
LEFT = '\x05'    # 强制左对齐（压过居中／右对齐的几何判据）


def _leader_fill(text, size, avail):
    """把每一行的 `左段右段` 展开成用点填满该行宽度的一条。

    **逐行处理**：目录常是一整块多行文本（源文档把整列目录合并成一个
    提取单元），每行各自要把页码顶到右边界。只处理第一处 LEADER
    就只有首行对齐，其余各行的页码仍散在中间。
    """
    from dwg_overlay import _width
    out = []
    for ln in text.split("\n"):
        mark = LEADER if LEADER in ln else (RALIGN if RALIGN in ln else None)
        if mark is None:
            out.append(ln)
            continue
        left, right = ln.split(mark, 1)
        # LEADER 用点填（目录），RALIGN 用空格填（算式：数值右对齐成列）
        dot = (_width(" .", size) / 2.0 if mark is LEADER
               else _width("  ", size) / 2.0) or 1.0
        room = avail - _width(left, size) - _width(right, size) - dot * 2
        ch = "." if mark is LEADER else " "
        n = max(2, int(room / dot))
        # **按实测收敛**，不能只靠一次估算：点数是整数，且度量与实际渲染
        # 总有偏差，一次估算下来各行落点能差 20pt 以上
        # （用户两次点名「TOC 右侧页码没对齐」）。这里逐步逼近，
        # 直到整行宽度落在右边界内、且距边界不足一个点宽。
        for _ in range(24):
            w = _width(left + " " + ch * n + " " + right, size)
            if w > avail:
                n -= max(1, int((w - avail) / dot))
                if n < 2:
                    n = 2
                    break
                continue
            if avail - w >= dot:
                n += max(1, int((avail - w) / dot))
                continue
            break
        out.append(left + " " + ch * n + " " + right)
    return "\n".join(out)


def _nlines(text, size, avail):
    """估算行数 —— **显式换行也要算**，否则多行文本按一行估、字号定过大。"""
    from dwg_overlay import _width
    return sum(max(1, math.ceil(_width(ln, size) / max(avail, 1.0)))
               for ln in text.split("\n")) or 1


_CJK = "⺀-鿿豈-﫿　-〿＀-￯"
# 不能出现在行首 / 行尾。⚠ **中文弯引号与省略号必须收进来**（避坑 92）：
# 译文里「称为“海滩状纹”的波纹」正会把 ” 甩到行首，而 `check_line_start`
# 报得出来、折行时却拦不住 —— 判据与折行用的是两张表，漏一张就白报。
_NOHEAD = "、。，．；：）〕］｝」』】》〉！？%‰°″′”’…‥〞々"
_NOTAIL = "（〔［｛「『【《〈“‘〝"


def _cjkwrap(text, size, avail, slack=0.985):
    """按中文断行规则**预折行**（写入前插入显式换行）。

    `insert_textbox` 只在**空格**处断行。中文串里没有空格，于是
    「除装配与拆卸程序外，本手册还给出 API」之后那一长串中文被当成
    **一个词**：放不下就整块挪到下一行，首行只剩三分之一（实测 手册 A
    第 6 页最后一段，首行到 x=216、次行排满到 x=552，看着像断了句）。
    这里自己按「中日韩字符之间可断、拉丁词只在空格处断」折好行再写。

    同时遵守两条最基本的禁则：行首不出现收尾标点、行尾不出现起首标点。
    """
    from dwg_overlay import _width
    if avail <= 1 or not text:
        return text
    out = []
    for para in text.split("\n"):
        toks, cur = [], ""
        for ch in para:
            if re.match("[" + _CJK + "]", ch):
                if cur:
                    toks.append(cur)
                    cur = ""
                toks.append(ch)
            elif ch == " ":
                if cur:
                    toks.append(cur)
                cur = ""
                toks.append(" ")
            else:
                cur += ch
        if cur:
            toks.append(cur)
        lim = avail * slack
        line, buf = "", []
        for i, tk in enumerate(toks):
            cand = line + tk
            if line and _width(cand.rstrip(), size) > lim:
                # 禁则回退：本行末不留起首标点，下一行首不放收尾标点
                k = len(buf)
                if tk in _NOHEAD:
                    k -= 1                     # 把上一个字一并带到下一行
                while k > 1 and buf[k - 1] in _NOTAIL:
                    k -= 1
                if k < 1:
                    k = len(buf)
                out.append("".join(buf[:k]).rstrip())
                buf = buf[k:] + [tk]
                line = "".join(buf)
            else:
                buf.append(tk)
                line = cand
        if buf:
            out.append("".join(buf).rstrip())
    return "\n".join(out)



def centered_units(page, units, tol=12.0, max_frac=0.80):
    """判定哪些单元是**原版的居中标题**，返回下标集合。

    为什么要自动判：中文比英文短 30%，把居中标题按左对齐写进原矩形，
    整块就会左偏 —— 与原版「同源感」立刻破掉（目测清单点名 手册 B 第 2 页
    与 手册 C 第 2 页的多层标题）。词表里逐条打记号也行，但四册各有一套
    标题文字（Doc. 390 Rev A / Doc. 354 Rev C…），逐条列必漏。

    判据三条同时成立：
      ① 单元水平中心与**页面中心**相差 < tol；
      ② 宽度 < 页宽 × max_frac（整幅正文段落不算）；
      ③ 同一基线上**没有别的单元**（排除表格行 —— 表格中间那一列
         也可能恰好居中）。
    """
    pc = (page.rect.x0 + page.rect.x1) / 2.0
    pw = page.rect.width
    # 源页各文本行的墨迹框，供多行单元判对齐用（整页取一次，不要逐单元取）
    lines = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            if "".join(s["text"] for s in ln["spans"]).strip():
                lines.append(fitz.Rect(ln["bbox"]))
    out = set()
    for i, (r, _t, _s, k) in enumerate(units):
        if k > 0:
            continue
        if abs((r.x0 + r.x1) / 2.0 - pc) > tol or r.width > pw * max_frac:
            continue
        if r.height > 1.8 * max(_s, 6.0):
            # 多行单元。曾一律否掉（理由：版权声明这类多行段落的框也可能
            # 恰好居中，居中写出来整段变成「居中体」）。但**封面的副标题
            # 堆叠正是多行居中块** —— 一律否掉，中文就按左对齐落进原框，
            # 主标题居中、副标题左对齐参差，整块歪掉。实测 手册 B／手册 C／
            # 手册 K／手册 A／规范 F 五册封面全中，且六道关一处不报。
            #
            # 行数不是判据，**墨迹**才是：居中块各行中线取齐而左右不齐，
            # 两端对齐段落则左右都齐 —— `block_align` 正是按这个分的。
            own = [q for q in lines
                   if (q & r).get_area() > 0.5 * max(q.get_area(), 0.01)]
            if dov.block_align(own) != 1:
                continue
        if any(j != i and min(r.y1, q.y1) - max(r.y0, q.y0) > 0.5 * min(
                r.height, q.height) for j, (q, _a, _b, _c) in enumerate(units)):
            continue
        out.add(i)
    return out


def bold_units(page, units, min_frac=0.6):
    """判定哪些单元在原版里是**粗体**，返回下标集合。

    中文若一律用常规字重，原版的标题层次就全丢了（目测清单：
    「全文文本层次标题没有加黑、字体过小」）。原版的粗细信息在
    span 的 flags 第 4 位（或字体名含 Bold），按单元内粗体字符占比判。
    """
    spans = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            for sp in ln["spans"]:
                t = sp["text"].strip()
                if t:
                    spans.append((fitz.Rect(sp["bbox"]), len(t),
                                  bool(sp["flags"] & 16)
                                  or "bold" in sp["font"].lower()))
    out = set()
    for i, (r, _t, _s, _k) in enumerate(units):
        tot = hit = 0
        for sr, n, bd in spans:
            if (sr & r).get_area() >= 0.5 * max(sr.get_area(), 0.01):
                tot += n
                hit += n if bd else 0
        if tot and hit / tot >= min_frac:
            out.add(i)
    return out


def right_units(page, units, tol=2.5, need=3):
    """判定哪些单元属**右对齐的一列**，返回下标集合。

    中文比英文短，右对齐的行按左对齐写进原矩形后右端参差不齐，
    与原版立刻不同源（实测 规范 F 封面标题、手册 B 第 43 页首列零件名）。
    判据：同一页上右边界 x1 相同（容差 tol）的单元 ≥ need 条，
    且它们不是整幅正文段（宽度 < 页宽 80%）—— 那就是一列右对齐。
    """
    from collections import defaultdict
    cols = defaultdict(list)
    pw = page.rect.width
    trs = table_rects(page)
    ink = {}
    for i, (r, _t, _s, k) in enumerate(units):
        if k > 0 or r.width > pw * 0.80:
            continue
        ink[i] = dov.INK_X1.get((round(r.x0, 1), round(r.y0, 1)), r.x1)
        # 聚类要**限定在同一张表内**：不限的话，页顶体系文件头的标签
        # 与页中消耗品清单的项目符号（写入框都被放宽到各自单元格的
        # 右边界、x1 恰好同值）会凑成一「列」，整片文字贴到中缝上
        # （实测 手册 A 第 9 页 3 条项目符号 + 4 个表头标签共 8 条）。
        ti = next((j for j, t in enumerate(trs) if _inside(r, [t])), -1)
        # 聚类按**墨迹右界**：行级通道会把写入框放宽到单元格右边界，按框聚类
        # 等于把「同一列的每一格」都算成右对齐 —— 实测 手册 C 第 13 页
        # `wear in minor`（墨迹止于 x=491.6、框放宽到 589）因此被右对齐，
        # 直接压在右邻格的 `crack / galled` 上。
        # 纵开页上真正右对齐的一列（手册 B 第 43 页零件名）走的是**旋转通道**，
        # 本函数根本不参与 —— 它们的框就是英文墨迹框，中文照原位落下即齐。
        cols[(ti, round(ink[i] / tol))].append(i)
    out = set()
    runs = []
    for ids in cols.values():
        # 一「列」必须在纵向**连成一片**。手册 A 的表格区是整页边框，
        # 全页单元都落在同一个 rect 里，光按表分组分不开 —— 页顶文件头的
        # 标签与页中清单的项目符号仍会凑成一列。按 y 断成连续段再判。
        ids.sort(key=lambda i: units[i][0].y0)
        cur = [ids[0]]
        for i in ids[1:]:
            h = max(units[cur[-1]][0].height, units[i][0].height, 6.0)
            if units[i][0].y0 - units[cur[-1]][0].y1 <= 3.0 * h:
                cur.append(i)
            else:
                runs.append(cur)
                cur = [i]
        runs.append(cur)
    for ids in runs:
        if len(ids) < need:
            continue
        # 写入框**被放宽过**的那些条，还要求「格子明显比文字宽」：
        # 短标签靠右就贴到了右邻格的数值旁，读起来是一对；而整格排满的
        # 散文一旦右对齐只是把参差从右端搬到左端（手册 A 第 9 页消耗品清单）。
        # 判据只对放宽过的条生效 —— 段级单元的框就是墨迹框，比值恒为 1，
        # 一律套用会把**真正右对齐的一列**（规范 F 封面、手册 B 汇总表首列）
        # 全部否掉（实测 手册 B 第 43 页首列因此左对齐，整列被推出页面左界）。
        x0s = [units[i][0].x0 for i in ids]
        _spread = max(x0s) - min(x0s)
        wid = [i for i in ids if ink[i] < units[i][0].x1 - 2.0]
        # 填充率这一条防的是「整格排满的散文」—— 那种情形各行都贴着单元格
        # 左边，**x0 几乎相同**。x0 铺开这么大（> 20pt）就不可能是它，
        # 而正是右对齐列的定义（实测 规范 G 封面三行标题 x0 = 209/347/359、
        # 墨迹右端同为 523，填充率 0.97 被这条一票否决，中文右端塌了 140pt）。
        if len(wid) >= max(2, len(ids) // 2) and _spread < 20.0:
            fr = sorted((ink[i] - units[i][0].x0)
                        / max(units[i][0].width, 0.01) for i in wid)
            if fr[len(fr) // 2] > 0.55:
                continue
        # **x0 也齐 ⇒ 这是一列单元格，不是右对齐的文字。**
        # 行级通道会把写入框扩到单元格右边界，于是同一列各格的 x1 天然相同；
        # 只看 x1 会把表格的标签列判成右对齐，中文被顶到格子右边、
        # 与右邻格的内容连成一串（实测 手册 A 体系文件头出现「体系维护」）。
        # 真正右对齐的一列，各行**起点不同**（规范 F 封面标题即如此）。
        if _spread < 4.0:
            continue
        out |= set(ids)

    # ── 单个**多行**单元本身就是右对齐的一块 ──────────────────
    # 上面的聚类要 `need` 个单元才成一列，而封面的标题堆叠常被 MuPDF
    # 归成**一个**多行块（规范 G／规范 F 皆如此：三行右端都落在 x≈523，
    # 却只有一个单元）—— 凑不够数，整块按左对齐写回去，中文变短后右端
    # 塌掉 100pt 以上。行数不是判据，**行的墨迹**才是。
    lines = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            if "".join(s["text"] for s in ln["spans"]).strip():
                lines.append(fitz.Rect(ln["bbox"]))
    for i, (r, _t, _s, k) in enumerate(units):
        if k > 0 or i in out or r.height <= 1.8 * max(_s, 6.0):
            continue
        own = [q for q in lines
               if (q & r).get_area() > 0.5 * max(q.get_area(), 0.01)]
        if len(own) >= 2 and dov.block_align(own) == 2:
            out.add(i)
    return out


def rot_lines(page, tol=0.2, drop_font=None):
    """**旋转文本行**：[(rect, 文本, 字号, 转角)]，转角取 90/180/270。

    `drop_font` 与另两条通道同义 —— **必须传**，否则倾斜的大水印会被
    当成一条旋转单元。后果不是「多译一条」而是**整片内容消失**：
    `_claimed()` 会把落在旋转框内的水平单元统统剔除（本意是避免重影），
    33.9pt × 19 字的水印框覆盖大半页 ⇒ 该页正文既不进词表、也不报未命中；
    随后水印整块抹除又把它们擦掉。实测 手册 B 全书 **175 行**如此消失，
    而五道关一处都没报（它们只看写进去的东西）。

    为什么必须单列一路：`lines_of()` 与 `blocks_of()` 都按**水平行**聚组，
    对旋转文本毫无意义 —— 于是这些串既不计入未命中、也不会被译，
    成品上**静默留英文**（实测 手册 C 第 31 页全部 96 行都是 dir=(0,-1) 的
    横排汇总表印在纵开页上，残留 `END RACES`/`OD WORN` 等 13 行）。

    这是「待译单元不可信」的第五类，且比前四类更隐蔽 ——
    前四类至少会报未命中，这一类连报告都没有。

    好在 MuPDF 的 `get_text("dict")` **已按书写方向正确聚行**
    （`DISASSEMBLY  SUMMARY` 原样返回为一行），故无须自行重组，
    直接取其 line bbox 即可。
    """
    wm = wtok = None
    if drop_font:
        from dwg_overlay import font_spans
        wm, wtok = font_spans(page, drop_font)
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            dx, dy = ln["dir"]
            if abs(dx - 1.0) < tol and abs(dy) < tol:
                continue                      # 水平，走常规两路
            spans = ln["spans"]
            if wm:
                # 与另两条通道同一判据：位置命中**且**该 span 的词全是水印词
                def _hit(sp):
                    ws = sp["text"].split()
                    if not ws or any(w not in wtok for w in ws):
                        return False
                    b0 = sp["bbox"]
                    c = fitz.Point((b0[0] + b0[2]) / 2, (b0[1] + b0[3]) / 2)
                    return any(c in r for r in wm)
                spans = [s for s in spans if not _hit(s)]
                if not spans:
                    continue
            t = tov._norm("".join(s["text"] for s in spans))
            if not t:
                continue
            sizes = [s["size"] for s in spans if s["text"].strip()]
            sz = max(set(sizes), key=sizes.count) if sizes else 8.0
            if abs(dy + 1.0) < tol:
                rot = 90                      # 自下而上
            elif abs(dy - 1.0) < tol:
                rot = 270
            else:
                rot = 180
            if wm:
                sb = [x["bbox"] for x in spans if x["text"].strip()]
                rc = fitz.Rect(min(b0[0] for b0 in sb), min(b0[1] for b0 in sb),
                               max(b0[2] for b0 in sb), max(b0[3] for b0 in sb))
            else:
                rc = fitz.Rect(ln["bbox"])
            out.append((rc, t, sz, rot))
    return out


def wm_snapshot(page, pat, size_mul=2.0, abs_min=20.0):
    """抓取水印 span 的重建信息：[(文本, 起点, 字号, 颜色, 转角度数)]。

    为何要重建而不是「避开」：水印与正文空间重叠时，正文的 redaction 框会
    连带抹掉压在下面的水印字形，成品上留下 `RILLING TOOLS`／`ILLING TO`
    这类半截残字。两条路只有重建可行 ——
    若把水印区从 redaction 列表里扣除，压在水印上的**英文正文**就抹不干净，
    那比留下水印残迹严重得多。

    水印是纯装饰，重画不损信息；实测 手册 B 是 45° 斜置蓝色
    `ACME DRILLING TOOLS`（33.9pt MicrosoftSansSerif，color 0x0070c0），
    全书 45 页同一位置。
    """
    import math
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            dx, dy = ln["dir"]
            deg = math.degrees(math.atan2(-dy, dx))
            for sp in ln["spans"]:
                if not sp["text"].strip() or sp["size"] < abs_min:
                    continue
                if not re.search(pat, sp["font"], re.I):
                    continue
                c = sp["color"]
                out.append((sp["text"], fitz.Point(sp["origin"]), sp["size"],
                            (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0,
                             (c & 255) / 255.0), deg))
    return out


def _wm_quad(text, org, size, deg, font="helv", pad=1.12):
    """水印一条快照的**旋转占位四边形**，供精确抹除用。

    与 `wm_restore` 用同一组变换（绕 org 旋转 deg），故抹除范围与实际
    绘出的字形严格对应。`pad` 是长度余量 —— 度量按内置 helv 近似，
    真字体略宽，不留余量会剩半截残字。
    """
    tl = fitz.Font(font).text_length(text, size) * pad
    up, dn = size * 0.95, size * 0.35
    pts = [fitz.Point(org.x - size * 0.15, org.y - up),
           fitz.Point(org.x + tl, org.y - up),
           fitz.Point(org.x - size * 0.15, org.y + dn),
           fitz.Point(org.x + tl, org.y + dn)]
    if abs(deg) >= 0.5:
        m = fitz.Matrix(deg)
        pts = [org + (p - org) * m for p in pts]
    return fitz.Quad(pts[0], pts[1], pts[2], pts[3])


def wm_restore(page, snap, font="helv"):
    """按快照把水印重画回去。45° 之类的任意角度用 `morph` 绕起点旋转。

    字体用内置 `helv` 近似 MicrosoftSansSerif —— 装饰层无须字形精确，
    且内置字体不必嵌入、不增体积。
    """
    for text, org, size, color, deg in snap:
        try:
            if abs(deg) < 0.5:
                page.insert_text(org, text, fontname=font, fontsize=size,
                                 color=color)
            else:
                m = fitz.Matrix(deg)
                page.insert_text(org, text, fontname=font, fontsize=size,
                                 color=color, morph=(org, m))
        except Exception:
            pass
    return len(snap)


# 写入字号来源。"bbox"（历史缺省）：取自行级通道的字形框高 —— 8pt Helvetica
# 量成 ~9.0pt，再 ×1.05 写入，中文比原文大约 18%，同一注记块里还参差不齐
# （实测 8.66 / 8.76 / 9.46）。"span"：取与单元交叠最大的**源 span 真字号**，
# 图纸/表单（P 级）推荐。只影响写入字号，不影响键与抹除框。
SIZE_FROM = "bbox"


def units_of(page, split_gap=1, clean=True, rot=True, drop_font=None,
             col_split=False):
    """待译单元（见 `_units_of_raw`）；SIZE_FROM="span" 时字号换成源 span 真字号。"""
    units = _units_of_raw(page, split_gap, clean, rot, drop_font, col_split)
    if SIZE_FROM != "span":
        return units
    spans = [(fitz.Rect(sp["bbox"]), sp["size"])
             for b in page.get_text("dict")["blocks"] if b.get("type") == 0
             for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()]
    out = []
    for r, t, sz, k in units:
        ov = [((rb & r).get_area(), z) for rb, z in spans if rb.intersects(r)]
        out.append((r, t, max(ov)[1] if ov else sz, k))
    return out


def _units_of_raw(page, split_gap=1, clean=True, rot=True, drop_font=None,
                  col_split=False):
    """本页的**待译单元**：[(rect, 英文, 字号, 转角)]，转角 0 = 段级、-1 = 行级。

    导键与装配**必须共用本函数** —— 键的产生方式一旦两边不同，
    词表就永远命中不了（清理后的键 `CATCH` 去查未清理的 `CATCH CATCH`）。
    这是词表白写的最直接死法，故合并到一处。

    **必须在 `derotated` 上下文内调用**（`translate_page` 已代劳）；
    单独用于导键时也要自己包一层，否则 `/Rotate≠0` 的页面取到的方向是反的。
    """
    # ── `/Rotate≠0` 页面：**全部改用 MuPDF 原生行**，不自行聚组 ────
    # `lines_of()` 按水平行装桶，在旋转页上等于**跨列合并** —— 视觉上分属
    # 不同列的文字被并进一个框（实测 `CONN.` 出现 4 份、宽度各异；
    # `ROTOR BODY` 框成 98.5×29.6，w/h=3.33）。框一旦变「宽×矮」，
    # 写入端的 `avail_len = box.height` 就取到短边，每行只放一字 ⇒ 看着竖排。
    # MuPDF 的 `get_text("dict")` 已按**书写方向**正确聚行，直接用即可 ——
    # `rot_lines()` 一直正确正是这个原因。
    if page.rotation:
        out = [(r, t, s, page.rotation) for r, t, s, _ in rot_lines(page)]
        if clean:
            import keyclean
            cl = keyclean.clean([(r, t, s) for r, t, s, _ in out])
            out = [(r, t, s, page.rotation) for r, t, s in cl]
        # 旋转页这条提前 return 也必须过几何去重 —— 漏掉它的后果实测可见：
        # 三份 马达手册 末页（皆 /Rotate=90）的 `马达序列号／造斜：`
        # 各写两遍、重叠 100%，而四道关全绿。
        return _dedupe_geom(out)

    trs = table_rects(page)

    # ── 三条通道必须**互斥分区** ─────────────────────────────────
    # 竖排文字（`rot_lines` 认领的）也会被水平通道按行装桶抓到，
    # 但装出来的是碎片：实测 手册 I 第 14 页左列同一处既有旋转通道给的
    # `Rotary Drilling`（完整），又有行级给的 `Drilling` + `Rotary`（碎片），
    # 两者都写入 → **页面上中文重叠**。
    # 四道关全部看不见重叠（字写进去了、未命中 0、不溢出、不缺字），
    # 唯有出图目检才发现 —— 与「旋转页朝向错」同一类教训。
    # ⇒ 先让旋转通道认领，再把其占据的矩形从水平通道里扣掉。
    rots = rot_lines(page, drop_font=drop_font) if rot else []
    rot_rects = [r for r, _t, _s, _k in rots]

    def _claimed(r, t=None):
        """该矩形／文本是否已被旋转通道认领。

        两条判据，命中其一即认领：
        ① **面积**重叠 ≥ 0.3（阈值低于 `_inside` 默认的 0.6 —— 竖排文字的
           水平碎片框往往比旋转框更宽，实测碎片 (60,338,74,361) vs 旋转框
           (60,336,68,383) 只重叠 57%，卡在 0.6 门下）；
        ② **相交 + 文本为子串** —— 更精确的一条：`Drilling` 与 `Slide` 都是
           `Slide Drilling (No Rotary)` 的子串，且矩形相交，
           说明是同一内容的两种分组（旋转通道那份才是对的）。
           实测这两处重叠仅 28% 与 20%，纯靠面积阈值抓不到，
           再降阈值又会误伤竖排旁边正常的水平文字。

        认领宁松勿紧：多认领只是让该串走旋转通道（本来就该走），
        少认领则在页面上留下可见的中文重影 —— 而四道关看不见重影。
        """
        if not rots:
            return False
        if _inside(r, rot_rects, frac=0.3):
            return True
        if t:
            for rr, rt, _s, _k in rots:
                if (r & rr).get_area() > 0 and t in rt and t != rt:
                    return True
        return False

    # **认领过滤必须在 `keyclean.clean()` 之后**：clean 里的 `join_wrapped`
    # 要靠相邻行拼回被框宽截断的长句，提前摘掉行会让它少拼接材料，
    # 拼出截断版（实测 手册 B 第 3 页长段变成
    # `The disassembly, inspection and assembly instructions provide detailed`
    # 就此断在这里，而完整段的译文在词表里，于是报未命中）。
    # 只取**落在表格区内**的竖线做列切分（见 dwg_overlay.vrules 的注释）
    # 列切分**按文档开关**（默认关）。它解决的是「记录列与备注列跨列」
    # 那一类，只在 马达手册族的检验表上被点名；对别的文档，
    # 标题块／修订栏这类真表格里也排着散文，切开反而把整句劈成半句
    # （实测 规范 F 一开就多出 81 条半句键，且页面上并无跨列问题）。
    # 能力保留、影响面收窄 —— 谁需要谁打开。
    # `col_split` 可给 True（全页）或一个**矩形**（只在该区域内切列）。
    # 全页开的话，步骤表单元格里的散文也会被列线切成半句
    # （实测 手册 A 一开就多出 168 条半句键）；而该册真正需要切列的
    # 只有页顶的体系文件头（标签格与数值格被并成「体系维护」）。
    _zone = col_split if isinstance(col_split, fitz.Rect) else None
    _tvx = ([(x, y0, y1) for x, y0, y1 in dov.vrules(page)
             if any(t.x0 - 1 <= x <= t.x1 + 1 for t in trs)
             and (_zone is None
                  or (y0 >= _zone.y0 - 2 and y1 <= _zone.y1 + 2
                      and _zone.x0 - 2 <= x <= _zone.x1 + 2))]
            if (trs and col_split) else [])
    blk = [(r, t, s) for r, t, s, n in tov.blocks_of(page, drop_font=drop_font)
           if not _inside(r, trs)]
    lin = [x for x in dov.dedupe(dov.lines_of(page, split_gap=split_gap, vxs=_tvx,
                                              drop_font=drop_font))
           if _inside(x[0], trs)]
    if clean:
        import keyclean
        blk, lin = keyclean.clean(blk), keyclean.clean(lin)
    blk = [(r, t, s) for r, t, s in blk if not _claimed(r, t)]
    lin = [(r, t, s) for r, t, s in lin if not _claimed(r, t)]
    out = ([(r, t, s, 0) for r, t, s in blk]
           + [(r, t, s, -1) for r, t, s in lin])

    # ── 分区必须**按构造穷尽**：两条通道用的是同一文本的不同矩形 ──────
    # 段级按**块 bbox** 取 `not _inside`，行级按**词组 rect** 取 `_inside`。
    # 同一串在两套矩形下的判定可以**都为假** —— 块框判在表内（被段级排除）、
    # 词组框判在表外（被行级排除），于是从两个筛子中间漏掉。
    #
    # 实测 手册 I 第 19 页：`Torque` 在 `blocks_of` 与 `lines_of` 里都在，
    # 分区后两边都没有；同一个 `Torque` 在第 14 页却正常。
    # 后果最隐蔽 —— **既不计入未命中、也不会被译**，
    # 成品上静默留英文，而「未命中 0」照报（本册 5 行残留全是这么来的）。
    #
    # 兜底判据必须用**几何包含**，不能用文本相等：段级的串是「块内多行合并」，
    # 行级给的是单行，两者文本天然不等 —— 按文本比会把已被段级覆盖的行
    # 全部误判为漏网（实测误捞 808 条 / 46K 字符，覆盖率假跌到 45.6%）。
    # 正确判据：该行既不在任何表格区内（否则行级本就该收），
    # 又不被任何**已采纳的段级块框**几何包含（否则段级已连带译掉）。
    kept_blocks = [r for r, _t, _s in blk]
    orphan = [(r, t, s) for r, t, s in
              dov.dedupe(dov.lines_of(page, split_gap=split_gap, vxs=_tvx,
                                      drop_font=drop_font))
              if not _inside(r, trs) and not _inside(r, kept_blocks)]
    if orphan:
        if clean:
            import keyclean
            orphan = keyclean.clean(orphan)
        out += [(r, t, s, -1) for r, t, s in orphan]
    # ── 旋转通道：`/Rotate≠0` 页面的水平文字走这里 ─────────────────
    # 判定实验已做（四转角各写一份、出图目检）：`/Rotate=90` 页上
    # **rotate=90 才与相邻英文同向**，0/180/270 分别是竖排、镜像、倒置。
    # 故 `rot_lines()` 给出的 90 是对的。
    #
    # 曾一度渲染出镜像中文，真因不是这里，而是我给 `build()` 套了
    # `derotated`：`set_rotation(0)` 只改 `/Rotate` 属性、**不改存储中的
    # 字形方向**，写入时的 rotate=90 于是与事后恢复的 /Rotate=90 相加
    # 变成 180° —— 正是「镜像」的来历。**该上下文对写入端有害无益，已撤。**
    # 旋转通道的条目直接并入（水平通道已在上面把其矩形扣掉，不会重复）。
    # 原先在此按**文本**去重是错的：碎片文本（`Drilling`）与完整文本
    # （`Rotary Drilling`）不相等，去重根本不生效，重叠照旧发生。
    if rot:
        out += rots

    return _dedupe_geom(out)


def _dedupe_geom(units, frac=0.35):
    """**几何去重：矩形大面积重叠时，只保留分组更完整（文本更长）的那个。**

    这是根治「同一段源文本经多条通道以不同分组各被写一次」的通用办法。
    此前靠逐条打补丁（文本去重、矩形认领、阈值调参）总有漏网 ——
    因为重叠有太多来源：
      · 段级长段 vs 窄栏单词碎片（`在万一发生…` vs `的`／`马达`／`连接`）；
      · 旋转通道完整串 vs 行级碎片（`Rotary Drilling` vs `Drilling`+`Rotary`）；
      · 带编号／带符号形态 vs 裸形态（`4.3 预测造斜率` vs `预测造斜率`）；
      · 兜底通道捞回的串与原通道重复。
    实测 手册 I 未去重时 27 处重叠，而**前四道关一处都看不见**
    （字写进去了、不溢出、无残留英文、不缺字）。

    规则：两矩形交集 ≥ frac × 较小者面积时，丢掉文本较短的那条。
    阈值 0.35 而非 0.5 —— 判据看的是**源矩形**，而写入的中文更窄、
    框还带 padding，故渲染后的重叠比源矩形重叠更大：实测 0.5 时
    仍余 3 处（源重叠 41%，渲染后 97%~100%）。
    文本更长意味着分组更完整、更接近原文的语义单元；
    保留它同时也保住了正确的行内折行。

    丢弃时必须把被丢者的矩形**并入**保留者 —— 否则被丢者的矩形不会进入
    redaction 列表，它那段英文就留在页面上（实测 手册 I 第 8 页残留
    `al Play`：`Axial Play` 的前半被保留者抹掉、后半无人认领）。
    并入后写入框略微变大，对中文只是更宽松，无副作用。
    """
    order = sorted(range(len(units)),
                   key=lambda i: -len(units[i][1]))      # 长文本优先
    keep = []
    for i in order:
        r = units[i][0]
        a = r.get_area() or 1
        t = units[i][1]
        hit = None
        for k, ku in enumerate(keep):
            kr, kt = ku[0], ku[1]
            inter = (r & kr).get_area()
            # **互覆盖**判据：交集须同时占两者各 frac 以上（等价于占较大者
            # frac 以上）。原先按**较小者**判，等于「小框套进大框即合并」——
            # 而零件表里一个窄标签格（`Roll Pin, DRR`）天然套在整行件号框内，
            # 两者内容毫不相干。合并后短文本被丢弃、只剩件号串，而件号串又被
            # `keep()` 当作图形语言跳过 ⇒ 标签**既不译也不抹**，
            # 且未命中报 0（它从未作为待译单元出现）。实测 规范 F p87/p88
            # 零件表 30 余条标签全军覆没。
            # 「同一内容不同分组」那四类（长段 vs 碎片、旋转 vs 行级、
            # 带编号 vs 裸形态、兜底重复）本就都是**文本同源**，由下一条
            # 判据兜住，不依赖这条。
            if inter >= frac * max(a, kr.get_area() or 1):
                hit = k
                break
            # 面积不足但**文本同源**时也合并：只要矩形相交即判为同一内容
            # 的两种分组。三类实测都属此列：
            #   · 文本完全相同 —— 原版叠印两份、副本相距 >3pt（避坑 ⑳），
            #     位置去重漏过（`马达序列号／造斜：` 在三份 马达手册 上各写两遍）；
            #   · 一方为另一方子串 —— 带符号形态 vs 裸形态
            #     （`• 上接头与转子打捞头　• 转子与定子` vs `上接头与转子打捞头`）；
            #   · 窄栏单字碎片落在长段之内（长注释 vs `的`）。
            if inter > 0 and (t == kt or t in kt or kt in t):
                hit = k
                break
            # 文本**完全相同**且位置相近时也合并，即便矩形不相交 ——
            # 原版把同一标注叠印两份、副本可相距十几 pt（避坑 ⑳ 的位置去重
            # 只容差 3pt，漏过），源矩形因此不相交；但中文写入框带 padding、
            # 且中文比英文窄，渲染后两份几乎完全重合（实测三份 马达手册
            # 末页的 `马达序列号／造斜：` 皆如此，重叠 100%）。
            if t == kt and abs((r.y0 + r.y1) / 2 - (kr.y0 + kr.y1) / 2) < 12                     and abs(r.x0 - kr.x0) < 24:
                hit = k
                break
        if hit is None:
            keep.append(list(units[i]))
        else:
            keep[hit][0] = fitz.Rect(keep[hit][0]) | r     # 并入，保证被抹除
    return [tuple(u) for u in keep]


def write_rects(units, frac=0.8, edge=2.2):
    """**大框让位**：算出每个单元的**写入框**（抹除框仍用原矩形）。

    去重只处理「同一内容的不同分组」。另有一类不能去重也不能放任：
    **大框的首/末行被切成了独立单元**，文本不含于大框、必须各自译出，
    可大框的矩形仍覆盖那一行 —— 中文写满大框就压到小单元上。
    实测 手册 I p5：段落单元 (28.8, 97.4, 294.1, 172.8) 的英文止于
    `…in the unlikely event`，而同段最后一行的 `failure,` / `thus`
    是两个独立单元（y 162.2~172.8）；两者都写 ⇒ 页面上叠字。
    合并会**丢掉**小单元的文本（规范 F 零件表的教训），故只能让位。

    只在小单元贴着大框的上沿或下沿（`edge` 倍行高内）时裁 ——
    夹在中间的不动，宁可留一处重叠也不把大框腰斩。

    **让位只能改写入框。** 抹除框一旦跟着缩小，被让出的那一带英文就抹不掉
    （实测 手册 I 立刻冒出 21 行残留英文）。故本函数只返回写入框，
    `build()` 里 items 的第一元素仍是原矩形，用于 redaction。
    """
    out = []
    for k, ku in enumerate(units):
        kr, kt = fitz.Rect(ku[0]), ku[1]
        h = max(ku[2], 6.0)
        # **旋转单元一律用原框。** 让位与借空白都只动 y 方向；对 rotate=
        # 的单元，y 方向正是**行长**方向，改它等于挪动整条文字的起点 ——
        # 实测 手册 B 第 43 页拆卸汇总表（/Rotate=90）的 21 条零件名因此
        # 被推到页面外，页上只剩 4 条完整、4 条被左边界切掉。
        if len(ku) > 3 and ku[3] > 0:
            out.append(kr)
            continue
        for j, u in enumerate(units):
            if j == k:
                continue
            r, t = fitz.Rect(u[0]), u[1]
            if r.get_area() >= kr.get_area():
                continue
            if (r & kr).get_area() < frac * max(r.get_area(), 0.01):
                continue
            if t in kt or kt in t:
                continue
            if r.y1 >= kr.y1 - edge * h:              # 贴下沿 → 抬高大框底
                kr.y1 = min(kr.y1, r.y0 - 0.3)
            elif r.y0 <= kr.y0 + edge * h:            # 贴上沿 → 压低大框顶
                kr.y0 = max(kr.y0, r.y1 + 0.3)
        # ── 向下**借用空白**，而不是一味缩字号 ────────────────────
        # 中文常比英文占更多行，写入框按英文墨迹框算就偏矮，只能缩号。
        # 同一页里有的条目缩、有的不缩，字号就忽大忽小
        # （目测清单点名「第 14 页两条项目符号字体本应一致」）。
        # 做法：把框向下延到**正下方最近一个单元**之前，最多借 1.6 倍自身高。
        # 借的是空白，不会压到别人；真压到了第五关（重叠自检）会报。
        if kr.y1 - kr.y0 <= 3.0:
            out.append(fitz.Rect(ku[0]))
            continue
        below = [fitz.Rect(u[0]).y0 for j, u in enumerate(units)
                 if j != k and fitz.Rect(u[0]).y0 > kr.y1 - 0.5
                 and min(kr.x1, u[0].x1) - max(kr.x0, u[0].x0) > 0.25
                 * min(kr.width, max(u[0].width, 0.01))]
        lim = min(below) - 1.2 if below else kr.y1 + 1.6 * kr.height
        kr.y1 = max(kr.y1, min(lim, kr.y1 + 1.6 * kr.height))
        out.append(kr)
    return out


def translate_page(page, lookup, keep=None, split_gap=1, clean=True,
                   drop_font=None, wm_rebuild=True, wm_keep=True,
                   auto_center=False, col_split=False):
    """返回 (段级写入数, 行级写入数, 未命中清单, 溢出清单)。

    两级共用一个 lookup：键既有整段英文、也有表内短语，互不冲突。
    """
    # 快照必须在 redaction **之前**取 —— 抹完就读不到了
    snap = (wm_snapshot(page, drop_font)
            if drop_font and wm_rebuild else [])
    _wmr = []
    bov = tov.BlockOverlay(page)
    lov = dov.Overlay(page)
    miss = []
    rots = []
    units = units_of(page, split_gap, clean, drop_font=drop_font,
                     col_split=col_split)
    # 写入框 ≠ 抹除框：写入让位给落在框内的独立小单元，抹除仍用原矩形
    wrs = write_rects(units)
    # **右对齐优先于居中**：右对齐成列的行往往同时满足「居中」判据
    # （整列居中于版心时，单行的中心也落在页心附近）。让居中抢走的话，
    # 该列右端就参差不齐 —— 实测 规范 F 封面第二行标题
    # `Double-Acting Hydraulic Drilling Jar` 正是如此。
    rgt = right_units(page, units) if auto_center else set()
    ctr = (centered_units(page, units) - rgt) if auto_center else set()
    bld = bold_units(page, units) if auto_center else set()
    # 原版用下划线表达的标题：改为加粗，线在写完后抹掉（见 underlines）
    _uidx, _urect = underlines(page, units)
    bld |= _uidx
    # 表单标签右对齐贴线（见 fillin_align）
    _fill = fillin_align(page, units) if auto_center else {}
    bov_rd, lov_rd = [], []
    _lov_left = set()          # 带 LEFT 记号的行级条目下标（供左界取齐）
    for idx, ((rect, txt, sz, kind), wr) in enumerate(zip(units, wrs)):
        # `keep` 同样可以选择接收上下文 —— 单字母表头（W/V/R）默认会被
        # 「无 2 连字母即保留」这一条拦在 lookup **之前**，词表再全也没用。
        if keep:
            try:
                _k = keep(txt, (page.number + 1, rect))
            except TypeError:
                _k = keep(txt)
            if _k:
                continue
        # 词表可以选择接收**页面上下文**：`lookup(text, ctx)`，
        # ctx = (页号, 矩形)。单字母表头（W/V/R = Witness/Verify/Record）
        # 必须靠页号区分 —— 同一个 `R` 在检验表里是「记录」列，
        # 在别的页上却是「R 型轴承」的代号，全局替换必错。
        try:
            zh = lookup(txt, (page.number + 1, rect))
        except TypeError:
            zh = lookup(txt)
        if zh is None:
            miss.append(txt)
            continue
        if not zh:
            continue
        bd = idx in bld
        # **带排版记号的条目自己管对齐**：目录行的右端由点引线顶到位，
        # 若再叠一层「整行右对齐」，填充算得略短就会把整行往右推，
        # 左边缘随之参差（实测 规范 F 目录被 right_units 认领后即如此）。
        if zh.startswith(RIGHT) or zh.startswith(LEFT):
            ctr.discard(idx)
            rgt.discard(idx)
        if LEADER in zh or RALIGN in zh:
            ctr.discard(idx)
            rgt.discard(idx)
        # 右对齐的条目要**贴回原文的右端**，不能贴写入框的右端 ——
        # 写入框已被放宽（放宽到单元格边界或下一段之前），贴框会把整条
        # 往右推出原位（实测 手册 B 第 37 页四行引出注解的框放宽到 x=589.7，
        # 中文被顶到 512，压在旁边的「3 处」上）。右对齐文字向左生长，
        # 故只需把框的右界收回墨迹右界，左界不动。
        if idx in rgt:
            _ix = dov.INK_X1.get((round(rect.x0, 1), round(rect.y0, 1)))
            if _ix and _ix < wr.x1 - 2.0:
                wr = fitz.Rect(wr.x0, wr.y0, _ix + 1.5, wr.y1)
        elif idx in _fill and not (zh.startswith(RIGHT)
                                   or zh.startswith(LEFT)
                                   or LEADER in zh or RALIGN in zh):
            wr = fitz.Rect(wr.x0, wr.y0, _fill[idx], wr.y1)
            rgt.add(idx)
            ctr.discard(idx)
        if kind > 0:
            rots.append((rect, wr, zh, sz, kind, bd))
        elif kind < 0:
            _al = 1 if idx in ctr else (2 if idx in rgt else 0)
            lov.add(wr, zh, size=sz * 1.05, align=_al)
            if zh.startswith(LEFT):
                _lov_left.add(len(lov.items) - 1)
            lov_rd.append((rect, bd))
        else:
            bov.add(wr, zh, sz,
                    align=1 if idx in ctr else (2 if idx in rgt else 0))
            bov_rd.append((rect, bd))

    # ── 强制左对齐的**兄弟条目**要左界取齐 ───────────────────────
    # `LEFT` 记号压过几何判据、按写入框左界排。但写入框继承自原版 ——
    # 原版若是**居中**的多行块，各行 x0 本就不同（行长不等），中文照着排
    # 就成了「左对齐但左界参差」。实测 手册 A 封面两条项目符号差 4.2pt。
    # 规则：纵向相邻（间距 ≤ 3 倍行高）且都带 LEFT 记号的条目视为同级，
    # 左界一律取齐到其中最左的一个（只收紧不放宽，不会挤出新的溢出）。
    _lf = sorted(_lov_left, key=lambda i: lov.items[i][0].y0)
    _grp, _cur = [], []
    for i in _lf:
        r = lov.items[i][0]
        if _cur and r.y0 - lov.items[_cur[-1]][0].y1 > 3.0 * max(r.height, 6.0):
            _grp.append(_cur)
            _cur = []
        _cur.append(i)
    if _cur:
        _grp.append(_cur)
    for g in _grp:
        if len(g) < 2:
            continue
        x = min(lov.items[i][0].x0 for i in g)
        for i in g:
            r, t, s, a = lov.items[i]
            lov.items[i] = (fitz.Rect(x, r.y0, r.x1, r.y1), t, s, a)

    # 两级的 redaction 必须**合并成一趟**：分两趟做，第二趟的
    # apply_redactions 会把第一趟刚写进去的中文一并抹掉。
    items = [(rd, r, t, s, a, l, 0, bd)
             for (rd, bd), (r, t, s, a, l) in zip(bov_rd, bov.items)]
    for (rd, bd), (r, t, s, a) in zip(lov_rd, lov.items):
        items.append((rd, r, t, s, a, 1.28, 0, bd))
    for rd, r, t, s, rot, bd in rots:
        items.append((rd, r, t, s, 0, 1.28, rot, bd))

    # ── `/Rotate≠0` 页面：矩形原样不动，**全页统一 rotate=页面转角** ──
    #
    # 本批最难查的一处 —— 四道关**全部拦不住**（字写进去了、rc 非负、
    # 字号够、残留英文 0），唯有逐页出图目检才看得见方向错。
    #
    # 关键事实：`get_text()` 的 bbox 与 `insert_textbox` / `add_redact_annot`
    # **同用未旋转空间**，故矩形一律原样传，不要乘 `rotation_matrix`。
    # （p31 的 `DISASSEMBLY SUMMARY` bbox 报 11 宽 × 119 高，看着「不合理」，
    #  但那正是未旋转空间里的真实形状，换算反而会错。）
    #
    # 六轮实测，每轮都出图目检：
    #   ① 原矩形 + rotate=0              位置对、竖排
    #   ② 原矩形 + 混排（部分 90、余 0）  位置对、看着镜像 —— **混排才是乱源**
    #   ③ ×rotation_matrix + rotate=90   每行一字的竖排
    #   ④ ×rotation_matrix + rotate=0    整体转 90°
    #   ⑤ ×rotation_matrix 仅用于写入    中文对、抹除偏位（残留 `G TOOLS`）
    #   ⑥ 原矩形 + rotate=90 全页统一    上半页对了，下半页反而竖排
    #
    #   ⑦ 原矩形 + 逐条按自身 dir 定转角  上半页又变镜像 —— **比⑥更差**
    #
    # ⑥是目前最好的已知状态：上半页（拆卸汇总／客户工单号／工具序列号／
    # 技师／客户／钻机／扶正器外径…）**全部正确**；
    # 残留缺陷是下半表约 6 条标签仍竖排：转子本体、定子芯、磨损长度、
    # 连接、滚道平均值、内外推力。
    #
    # 待查（下一步）：这 6 条在⑥里与其余条目**转角相同**却朝向不同，
    # 差异只能出在**框的形状**上 —— `rot` 分支按 `avail_len = box.height`
    # 估算，若这几条的存储 bbox 是「宽×矮」而非「窄×长」，avail_len 就取到了
    # 短边，于是每行只放一字、看着像竖排。
    # 判定办法：把这 6 条的存储 bbox 打出来，与正确的那批对比宽高比。
    # **不要再盲试转角组合** —— 七轮已证明转角不是剩下的变量。
    #
    # 顺带否掉两条歧路：`set_rotation(0)`（只改属性、不改字形方向，反而多转
    # 90°，②那轮的「镜像」正是它造成的）；`apply_redactions` 与转角无关
    # （redaction 前后各做一次四转角探针，结论一致）。
    # ── 带 RIGHT 记号的一列，右边界**取齐到同一 x** ────────────────
    # 只在各自单元格里右对齐是不够的：目录各级条目的格宽不同
    # （行级通道把写入框扩到「下一段左界」或固定余量），
    # 于是 `1-1` 与 `6-3-9` 的右端仍差十几 pt，看着还是参差。
    # 取本页所有 RIGHT 条目写入框的**最大 x1** 作为公共右边界。
    # 带**点引线**的整行同理：点只能填满各自的写入框，而各级条目的框
    # 右端相差可达 20pt（框是源墨迹框加放宽量），于是页码列仍参差。
    # 两类一起取齐到本页的公共右边界。
    _ridx = [i for i, it in enumerate(items)
             if it[2].startswith(RIGHT) or LEADER in it[2]]
    if len(_ridx) > 1:
        _xmax = max(items[i][1].x1 for i in _ridx)
        for i in _ridx:
            rd, r, t, sz, al, ld, rot, bd = items[i]
            items[i] = (rd, fitz.Rect(r.x0, r.y0, _xmax, r.y1),
                        t, sz, al, ld, rot, bd)

    if page.rotation:
        R = page.rotation
        items = [(rd, r, t, s, a, l, R, bd)
                 for rd, r, t, s, a, l, _, bd in items]
    if not items:
        return 0, 0, miss, []
    for r, *_ in items:
        page.add_redact_annot(fitz.Rect(r) + (-0.5, -0.5, 0.5, 0.5))
    # 水印要**整块抹干净再重画**。原先它只被正文的 redaction 框
    # 蹭掉一部分，成品上留下 `RILLING TOOLS`／`ILLING TO` 半截残字；
    # 既然已有快照可重建，就索性把整个水印区一并抹掉，抹后按快照重绘。
    if snap:
        # **抹除范围必须是旋转四边形（Quad），不能是矩形。**
        #
        # 手册 B 的水印是 45° 斜置的 33.9pt 大字，三版都错过：
        #   ① `size × len × 0.75` 的正方形 —— 966×966 pt，几乎整页；
        #   ② `font_spans` 给的 span 矩形 —— 那是斜排文本的**轴对齐包围盒**
        #      (158.8, 249.5, 451.8, 542.5)，293×293 pt 的方块，其中大半是
        #      空白，压在下面的表格数值照样被抹（p4 `5,500`／`8,600` 消失）；
        #   ③ 按 helv 度量算的紧**矩形** —— 覆盖不足，留下 `RILLING TOOLS`
        #      这类半截残字（实测 27 行）。
        # 斜排文本的真实占位是一条**斜的窄带**，只有 Quad 能表达。
        # 长度用 helv 近似（真字体是 MicrosoftSansSerif），故留 12% 余量。
        #
        # 三版全部是「五道关全绿、页面上东西没了」—— 交付前必须跑
        # `_engine/sweep.py`（保留项失踪 / 重叠 / 缺字）。
        from dwg_overlay import font_char_rects as _fcr
        _wmr = [fitz.Rect(_r) & page.rect for _r in _fcr(page, drop_font)]
        for _r in _wmr:
            page.add_redact_annot(_r)
    # 抹除会连带删掉**仅仅触碰**到写入框的邻行字形（数值、代号等保留项
    # 尤其吃亏 —— 它们不进词表、不报未命中，五道关全看不见）。
    # 先快照会被误伤的字形，抹完原样补回。判据见 dwg_overlay.rescue_snapshot。
    # 抢救判据要看**全部**抹除框（正文 + 水印）。只传正文框的话，
    # 水印字形会被判成「误伤」又画回去 —— 实测 `wm_keep=False`（去水印）
    # 时页面上仍剩 `DRILL`／`RILLI`／`OOLS` 三段 helv 残字。
    _rs = dov.rescue_snapshot(
        page, [fitz.Rect(r) + (-0.5, -0.5, 0.5, 0.5) for r, *_ in items],
        wm_rects=_wmr, drop_font=drop_font)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    dov.rescue_restore(page, _rs)
    bov.items, lov.items = [], []
    page.insert_font(fontname="zh", fontfile=dov.ZH_FONT)
    page.insert_font(fontname="zhb", fontfile=dov.ZH_FONT_B)

    # 抹完再统一写：段级用 BlockOverlay 的多行估高，行级用单行估高
    nb = nl_ = 0
    over = []
    from dwg_overlay import _width
    # ── 同一行的字号先**向下取齐** ───────────────────────────────
    # 逐条各自缩号会让同一行里字号忽大忽小（目测清单多处点名：
    # 「字体明显存在差异」「字号不一致」「插图/文本间隔类页面应统一字号」）。
    # 办法：先算出每条**放得下的最大字号**，同一行取中位数作目标，
    # 再令每条取 `min(自身上限, 目标)` —— **只向下取齐**，故恒能放下，
    # 不会引入新的溢出。
    _fit = []
    for _rd, r, text, size, align, lead, rot, bold in items:
        if rot:
            al = fitz.Rect(r).height - 1.0
            ad = fitz.Rect(r).width + 2.4
        else:
            al = fitz.Rect(r).width - 1.0
            ad = fitz.Rect(r).height + 3.0
        s0 = size
        while s0 > 3.6:
            probe = (_leader_fill(text, s0, al)
                     if (LEADER in text or RALIGN in text)
                     else text.lstrip(CENTER))
            _ln = _nlines(probe, s0, al)
            # 行高系数：**发生折行**时留 1.90 的安全余量（估算不准，宁小勿溢）；
            # 文本自带换行、且各行都不折时，真实需求只有 ~1.3 ——
            # 一律用 1.90 会把多行算式压到 6pt（实测 规范 G 第 9 页下击段）。
            _f = 1.90 if _ln > probe.count(chr(10)) + 1 else 1.34
            if _ln * s0 * _f <= ad - 0.3:
                break
            s0 -= 0.3
        _fit.append(s0)
    _rows = {}
    for i, (_rd, r, _t, _s, _a, _l, _rot, _b) in enumerate(items):
        # **旋转单元不参与同行取齐**：纵开页上「同一视觉行」在去旋坐标系里
        # 是同一**列**，按 y 中点分组会把整列零件名归成一「行」
        # （实测 手册 B 第 43 页拆卸汇总表 21 条零件名的 y 中点全是 715），
        # 取到的中位字号来自那一堆里最窄的一条，整列被压没。
        if _rot:
            _rows.setdefault(("r", i), []).append(i)
            continue
        key = round((r.y0 + r.y1) / 2.0 / 4.0)
        _rows.setdefault(key, []).append(i)
    _tgt = {}
    for ids in _rows.values():
        vs = sorted(_fit[i] for i in ids)
        med = vs[len(vs) // 2]
        for i in ids:
            _tgt[i] = min(_fit[i], med)

    for _i, (_rd, r, text, size, align, lead, rot, bold) in enumerate(items):
        size = max(_tgt.get(_i, size), 3.6)
        fnt = "zhb" if bold else "zh"
        if rot:
            # 旋转文本：字沿框的**高**方向排列，故可用行长是 height、
            # 可用堆叠深度是 width —— 估算时两者互换，写入交给 rotate=。
            box = fitz.Rect(r.x0 - 1.0, r.y0 - 0.4, r.x1 + 2.0, r.y1 + 0.4)
            avail_len, avail_depth = box.height, box.width
        else:
            box = fitz.Rect(r.x0 - 0.4, r.y0 - 1.0, r.x1 + 0.4, r.y1 + 2.0)
            avail_len, avail_depth = box.width, box.height
        # 行数估算必须**向上取整**、行高取 1.70 而非 1.60：
        # 原先 `int(w/W)+1` 在 w 恰为 W 整数倍时少算一行，1.60 又贴着
        # insert_textbox 的真实需求（≈1.58），估算「刚好放下」而实际放不下时
        # **一字不写也不报错**（避坑 ⑳ 同源）。下限降到 3.6 与 dwg_overlay 一致 ——
        # 窄格里的中文标签（如「方法：」比 `Method:` 宽）只能靠缩号求生。
        # 先按估算取一个起点（省掉大部分重试），再**实写重试**收敛。
        if text.startswith(CENTER):
            text, align = text[1:], 1
        elif text.startswith(LEFT):
            text, align = text[1:], 0
        elif text.startswith(RIGHT):
            # 目录的**页码列**是独立单元，且多为纯数字（被 keep 规则跳过、
            # 原样留着），于是左对齐参差。改写为同样内容但右对齐 ——
            # 纯版式动作，不改内容。
            text, align = text[1:], 2
        s = size
        while s > 3.6:
            probe = (_leader_fill(text, s, avail_len - 1.0)
                     if (LEADER in text or RALIGN in text) else text)
            lines = _nlines(probe, s, avail_len - 1.0)
            _f = 1.90 if lines > probe.count(chr(10)) + 1 else 1.34
            if lines * s * _f <= avail_depth - 0.3:
                break
            s -= 0.3
        # **实写重试是唯一可靠的收敛办法。** 已实测证清：`insert_textbox`
        # 返回负值时**一字未写**（三组对照实验：宽高都不足 rc=-359 落 0 字、
        # 仅高不足 rc=-28.8 落 0 字、充裕 rc=+15.2 落 27 字）。
        # 故重试不会叠在残迹上 —— `text_overlay` 里「rc<0 重画会叠残迹」的
        # 旧注记不成立（那条针对的是先铺白底再写字的另一种画法）。
        # 有了这一条，行高系数就只是**起点估算**，不必再靠收紧系数硬猜：
        # 此前 1.60→1.70→1.90 三轮只把溢出压到 4 处，实写重试可归零。
        # 中文没有空格，`insert_textbox` 断不开 —— 先自己按中文断行规则折好
        # （引线／算式类记号自带排布，不能再折）。
        # **旋转单元不折**：它们是纵开页上的短标签，写入框的「行长」是框高，
        # 预折出的换行在 rotate= 下按框宽堆叠，实测 手册 B 第 43 页汇总表
        # 首列 21 条零件名有 14 条因此被挤出页面或截断。
        out = (_leader_fill(text, s, avail_len - 1.0)
               if (LEADER in text or RALIGN in text)
               else (text if rot else _cjkwrap(text, s, avail_len - 1.0)))
        rc = page.insert_textbox(box, out, fontname=fnt, fontsize=s,
                                 align=align, lineheight=lead,
                                 rotate=rot, color=(0, 0, 0))
        while rc < 0 and s > 3.0:
            s -= 0.4
            out = (_leader_fill(text, s, avail_len - 1.0)
                   if (LEADER in text or RALIGN in text)
                   else (text if rot else _cjkwrap(text, s, avail_len - 1.0)))
            rc = page.insert_textbox(box, out, fontname=fnt, fontsize=s,
                                     align=align, lineheight=lead,
                                     rotate=rot, color=(0, 0, 0))
        if rc < 0:
            over.append((text[:50], round(s, 1)))
        if rot or (lead == 1.28 and align == 0):
            nl_ += 1
        else:
            nb += 1
    # 抹掉下划线 —— **必须在写完之后**，且只在那几条细带上放开 line art，
    # 否则会把同页的表格框一起抹了。
    if _urect:
        for _r in _urect:
            page.add_redact_annot(_r)
        # **文字必须豁免**（`PDF_REDACT_TEXT_NONE`）—— 抹除带正压在刚写好的
        # 中文标题上，不豁免就把标题一起抹了（实测「文件」「螺纹连接检验」消失）。
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=fitz.PDF_REDACT_TEXT_NONE)
    if snap:
        if wm_keep:
            wm_restore(page, snap)
        # `wm_keep=False` 时只抹不画 —— 交付要求「全文去水印」时用。
        # 注意仍要走快照那条路：不取快照就不会整块抹除，
        # 水印只会被正文写入框蹭掉一部分，留下 `RILLING TOOLS` 半截残字。
    return nb, nl_, miss, over


def underlines(page, units, tol_lo=1.0, tol_hi=3.5, min_frac=0.5,
               max_wfrac=0.62):
    """原版给标题加的**下划线**：返回 (需加粗的单元下标集合, 待抹的线矩形)。

    下划线是**线条**（line art），而抹除一律带 `PDF_REDACT_LINE_ART_NONE`
    以保住表格框，于是它原样留着 —— 中文比英文短，线就从字尾伸出去一截
    （实测 手册 C 第 6 页「文件————」「螺纹连接检验————」，目测清单点名）。
    下划线在中文里本不是标题的表达方式，改用**加粗**，线抹掉。

    判据（四条同时成立，宁漏勿误 —— 抹错线会在表格上留缺口）：
      · 线在该单元墨迹的**正下方** 1.0~3.5pt；
      · 线的 x 跨度**完全含于**该单元（±2pt）—— 表单的填写横线一律
        伸到标签右侧很远，据此排除；
      · 线长 ≥ 单元宽的一半（短装饰段不算）；
      · 该单元本身是**标题级**的短行（宽 < 页宽 62%）。
    """
    from dwg_bom import segments
    H, _V = segments(page, min_h=12.0, min_v=3.0)
    pw = page.rect.width
    idx, rects = set(), []
    for i, (r, t, _s, k) in enumerate(units):
        if k > 0 or r.width > pw * max_wfrac:
            continue
        for y, x0, x1 in H:
            # 下划线常落在单元框**内**（框底含下伸部留白）——
            # 实测 `CONNECTION INSPECTIONS` 框底 673.1、线在 671.5，
            # 只往框外找一律找不到。故上界按框高的一成半往里收。
            if not (r.y1 - max(tol_lo, 0.35 * r.height)
                    <= y <= r.y1 + tol_hi):
                continue
            if x0 < r.x0 - 2.0 or x1 > r.x1 + 2.0:
                continue
            if x1 - x0 < min_frac * r.width:
                continue
            idx.add(i)
            # `REMOVE_IF_COVERED` 要求线**整条**落在抹除框内才删，
            # 故带子要略宽于线本身（线宽 0.5~1pt，端点还有取整误差）。
            rects.append(fitz.Rect(x0 - 1.5, y - 2.0, x1 + 1.5, y + 2.0))
    return idx, rects


def fillin_align(page, units, tol_hi=3.5, min_len=18.0, gap=26.0):
    """表单里「标签 + 填写横线」的标签一律**右对齐**贴到横线前。

    原版这些标签是左对齐的，英文短、中文长短不一，照原位写出来右端参差，
    与紧随其后的填写横线之间空隙忽大忽小（目测清单：「文本一律右对齐，
    保持美观。该问题存在类似的文档中」）。右对齐后每个标签都紧贴自己那条线，
    读起来才是一对。

    返回 {单元下标: 写入框右界}。判据：同一基线带内、**紧接其右**
    (≤ gap) 有一条 ≥ min_len 的横线。
    """
    from dwg_bom import segments
    H, _V = segments(page, min_h=min_len, min_v=3.0)
    out = {}
    for i, (r, t, _s, k) in enumerate(units):
        if k > 0 or not t:
            continue
        ix = dov.INK_X1.get((round(r.x0, 1), round(r.y0, 1)), r.x1)
        best = None
        for y, x0, x1 in H:
            if not (r.y1 - max(1.0, 0.35 * r.height) <= y <= r.y1 + tol_hi):
                continue
            if not (ix - 1.0 <= x0 <= ix + gap):
                continue
            if best is None or x0 < best:
                best = x0
        if best is not None and best - 2.0 > r.x0 + 4.0:
            out[i] = min(best - 2.0, r.x1)
    return out


def build(src, dst, lookup, keep=None, verbose=True, drop_font=None,
          wm_keep=True, auto_center=False, col_split=False, size_from=None):
    """整册叠印。size_from="span" 时写入字号取源 span 真字号（P 级图纸/表单推荐）。"""
    import os
    global SIZE_FROM
    if size_from:
        SIZE_FROM = size_from
    doc = fitz.open(src)
    tb = tl = 0
    allmiss, allover = [], []
    # `auto_center` 可以是 True（全书）或**页号集合**（仅这些页）。
    # 为什么要能按页开：封面往往是全书唯一需要几何对齐判据的一页
    # （原版标题块右对齐、中文变短后右端塌掉），而整册打开这组判据
    # 会连带改动其余几十页的对齐 —— 那是拿一页的收益去赌整册的回归。
    _pgs = auto_center if isinstance(auto_center, (set, frozenset,
                                                  list, tuple)) else None
    for i, page in enumerate(doc, 1):
        _ac = (i in _pgs) if _pgs is not None else bool(auto_center)
        nb, nl_, miss, over = translate_page(page, lookup, keep,
                                            drop_font=drop_font,
                                            wm_keep=wm_keep,
                                            auto_center=_ac,
                                            col_split=col_split)
        tb += nb
        tl += nl_
        allmiss += [(i, m) for m in miss]
        allover += [(i,) + o for o in over]
        if verbose and (miss or over or i % 10 == 0):
            print(f"   页 {i}: 段 {nb} 行 {nl_} 未命中 {len(miss)} 溢出 {len(over)}")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    doc.save(dst, garbage=3, deflate=True)
    doc.close()
    return tb, tl, allmiss, allover
