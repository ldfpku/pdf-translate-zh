# -*- coding: utf-8 -*-
"""**描边化矢量文字**的定位与中文回叠（SKILL §3「图内中文回叠」）。

工程图里的图内标注常被导出成**轮廓路径**而非文字：文本层里根本没有它，
既提取不到、也无法 redaction 抹除。前面几册的处理是「保持英文原样 +
在附录里说明」（规范 G 约 20 处）。本模块把这条路补上：

  1. `runs(page, clip)` —— 按几何把**字母级小路径**聚成文字串矩形；
     判据：路径高度落在字高区间、宽度不超过一个字宽、
     同一基线上水平间距小于一个字宽者并成一串。
  2. `overlay(page, items)` —— 逐串铺白底、写中文。
     白底必不可少：描边文字抹不掉，只能盖住。

**本模块不认字**：它只给出「这里有一串图内文字、框在哪」。
写什么由调用方按串的位置逐条给出（裁图目检一次即可），
这与 SKILL 的做法一致 —— 图内标注数量有限，值得逐条核对。
"""
try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz


def runs(page, clip=None, hmin=3.0, hmax=12.0, wmax=14.0, gap=2.2,
         min_parts=2):
    """把描边化文字聚成串，返回 [(rect, 组成路径数)]，按阅读顺序。"""
    box = fitz.Rect(clip) if clip else page.rect
    parts = []
    for dr in page.get_drawings():
        r = fitz.Rect(dr["rect"])
        if not r.intersects(box):
            continue
        h, w = r.height, r.width
        if not (hmin <= h <= hmax and 0.3 <= w <= wmax):
            continue
        # 纯横线／竖线不是字形
        if h < 0.8 or w < 0.8:
            continue
        parts.append(r)
    parts.sort(key=lambda r: (round(r.y0 / 2.0), r.x0))
    out, cur = [], None
    for r in parts:
        if cur is None:
            cur = [fitz.Rect(r), 1]
            continue
        same_line = (min(cur[0].y1, r.y1) - max(cur[0].y0, r.y0)
                     > 0.45 * min(cur[0].height, r.height))
        if same_line and r.x0 - cur[0].x1 <= gap:
            cur[0] |= r
            cur[1] += 1
        else:
            out.append(tuple(cur))
            cur = [fitz.Rect(r), 1]
    if cur:
        out.append(tuple(cur))
    return [(r, n) for r, n in out if n >= min_parts]


def inkbox(page, rough, dpi=220, thresh=170, pad=0.6):
    """粗框内**全部深色像素的包围盒** —— 比 `snap()` 的连通块分析稳得多。

    `snap()` 走「连通块 + 同行合并」，对**下采样过的位图小字**不稳：
    实测 手册 A 第 11 页 26 条标注里有 24 条只吸附到单个字符（2~3pt 宽）。
    本函数换一条更笨也更可靠的路 —— 粗框内本来只有那一条标注、其余是白底，
    所以「框内所有深像素的包围盒」就是标注框。
    **前提：粗框不能碰到插图本身**（碰到了包围盒会被图元拉大），
    故仍须画框出图目检一次。
    """
    R = fitz.Rect(rough)
    z = dpi / 72.0
    pm = page.get_pixmap(clip=R, matrix=fitz.Matrix(z, z),
                         colorspace=fitz.csGRAY)
    w, h, sm, st = pm.width, pm.height, pm.samples, pm.stride
    xs0, ys0, xs1, ys1 = w, h, -1, -1
    for y in range(h):
        row = sm[y * st:y * st + w]
        for x in range(w):
            if row[x] < thresh:
                if x < xs0:
                    xs0 = x
                if x > xs1:
                    xs1 = x
                if y < ys0:
                    ys0 = y
                if y > ys1:
                    ys1 = y
    if xs1 < 0:
        return None
    return fitz.Rect(R.x0 + xs0 / z - pad, R.y0 + ys0 / z - pad,
                     R.x0 + (xs1 + 1) / z + pad, R.y0 + (ys1 + 1) / z + pad)


def overlay(page, items, font="zh", fontfile=None, pad=0.8, floor=3.6,
            fill=(1, 1, 1), color=(0, 0, 0)):
    """`items` = [(rect, 中文)] 或 [(rect, 中文, 底色, 字色)]；逐条铺底再写字。

    描边／位图里的文字**抹不掉**，只能盖住。底色默认白 —— 但图内标注常
    印在彩色块上（手册 A 第 7 页的七条安全要求是**白字彩底**），
    这时必须按该块的底色铺、并用白字写，否则会在彩带上留下一块白疤。
    底色可逐条给，取自源图上避开文字处的采样值。

    白底必须**先全部铺完再写字**，否则后一条的底会盖掉前一条的字脚
    （SKILL 避坑 ⑮）。
    """
    from dwg_overlay import ZH_FONT, _width
    page.insert_font(fontname=font, fontfile=fontfile or ZH_FONT)
    norm = []
    for it in items:
        r, t = it[0], it[1]
        if not t:
            continue
        f = it[2] if len(it) > 2 and it[2] is not None else fill
        c = it[3] if len(it) > 3 and it[3] is not None else color
        # 第 5 元素 = 转角：图内偶有**竖排**标注（手册 A 第 11 页
        # `Keyed – Double Key and Splined Mandrels`），不给转角就横着写、
        # 出框；给了之后行长取框高、堆叠深度取框宽。
        rot = it[4] if len(it) > 4 and it[4] else 0
        norm.append((fitz.Rect(r) + (-pad, -pad, pad, pad), t, f, c, rot))
    for b, _t, f, _c, _r in norm:
        page.draw_rect(b, color=None, fill=f)
    n = 0
    for b, t, _f, c, rot in norm:
        avail_len = b.height if rot else b.width
        avail_dep = b.width if rot else b.height
        s = min(avail_dep * 0.86, 9.0)
        while s > floor and _width(t, s) > avail_len - 0.6:
            s -= 0.2
        rc = page.insert_textbox(b, t, fontname=font, fontsize=s,
                                 align=1, color=c, rotate=rot)
        while rc < 0 and s > 3.0:
            s -= 0.3
            rc = page.insert_textbox(b, t, fontname=font, fontsize=s,
                                     align=1, color=c, rotate=rot)
        if rc >= 0:
            n += 1
    return n


def raster_runs(page, clip=None, dpi=200, hmin=4, hmax=40, wmax=40,
                gap=14, min_px=8, min_w=12):
    """定位**位图里烧死的文字串**，返回按阅读顺序排好的 PDF 矩形列表。

    位图内的英文既提取不到也抹不掉（SKILL 避坑 ㉑），此前只能「保持英文 +
    附录说明」。这里用像素连通块把字形聚成串：
      · 先按暗度二值化，取 4 邻域连通块；
      · 字形块的尺寸落在 (hmin..hmax) × (..wmax)，且像素数 ≥ min_px；
      · 同一基线上水平间距 ≤ gap 的块并成一串。

    线条画里的引出线与轮廓也会形成连通块，但它们要么过长（超出 wmax／hmax）、
    要么太细（像素数不足），基本不会混进来；**仍须逐条裁图核对**，
    因为本函数只给位置、不认字。
    """
    box = fitz.Rect(clip) if clip else page.rect
    sc = dpi / 72.0
    pm = page.get_pixmap(dpi=dpi, clip=box)
    w, h = pm.width, pm.height
    dark = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = pm.pixel(x, y)[:3]
            if r < 120 and g < 120 and b < 120:
                dark[row + x] = 1
    seen = bytearray(w * h)
    boxes = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not dark[i] or seen[i]:
                continue
            st = [(x, y)]
            seen[i] = 1
            x0 = x1 = x
            y0 = y1 = y
            n = 0
            while st:
                cx, cy = st.pop()
                n += 1
                if cx < x0:
                    x0 = cx
                if cx > x1:
                    x1 = cx
                if cy < y0:
                    y0 = cy
                if cy > y1:
                    y1 = cy
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        j = ny * w + nx
                        if dark[j] and not seen[j]:
                            seen[j] = 1
                            st.append((nx, ny))
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            if hmin <= bh <= hmax and 2 <= bw <= wmax and n >= min_px:
                boxes.append((x0, y0, x1, y1))
    boxes.sort(key=lambda b: (round(b[1] / 8), b[0]))
    runs = []
    for b in boxes:
        if runs:
            rx0, ry0, rx1, ry1 = runs[-1]
            ov = min(ry1, b[3]) - max(ry0, b[1])
            if ov > 0.4 * min(ry1 - ry0 + 1, b[3] - b[1] + 1) \
                    and b[0] - rx1 <= gap:
                runs[-1] = (min(rx0, b[0]), min(ry0, b[1]),
                            max(rx1, b[2]), max(ry1, b[3]))
                continue
        runs.append(b)
    out = []
    for rx0, ry0, rx1, ry1 in runs:
        if rx1 - rx0 < min_w:
            continue
        out.append(fitz.Rect(box.x0 + rx0 / sc, box.y0 + ry0 / sc,
                             box.x0 + rx1 / sc, box.y0 + ry1 / sc))
    return out


def _dark_map(page, box, dpi):
    pm = page.get_pixmap(dpi=dpi, clip=box)
    w, h = pm.width, pm.height
    dk = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = pm.pixel(x, y)[:3]
            if r < 120 and g < 120 and b < 120:
                dk[row + x] = 1
    return dk, w, h


def _density_mask(dk, w, h, rad=4, thresh=0.24):
    """按**局部墨迹密度**把文字从线条里分出来。

    这是把「图内标注」与「引出线／轮廓」分开的关键一步。此前只按连通块
    尺寸过滤不成立：引出线一旦碰到字母，两者成为**同一个连通块**，
    该块因过大被滤掉，标注框就缺字母；放宽合并间距又会把相邻两条标注
    并成一块。文字与线条的本质差别是**局部密度** ——
    9×9 窗口内文字的墨迹占比约 25%~45%，而一条 1~2px 宽的线只有 10% 上下。
    先按密度留下文字像素，再做连通块，引出线自然不参与。
    """
    ii = [0] * ((w + 1) * (h + 1))
    for y in range(h):
        ro, rn = y * (w + 1), (y + 1) * (w + 1)
        srow = y * w
        acc = 0
        for x in range(w):
            acc += dk[srow + x]
            ii[rn + x + 1] = ii[ro + x + 1] + acc
    area = (2 * rad + 1) ** 2
    out = bytearray(w * h)
    for y in range(h):
        y0, y1 = max(0, y - rad), min(h - 1, y + rad)
        for x in range(w):
            if not dk[y * w + x]:
                continue
            x0, x1 = max(0, x - rad), min(w - 1, x + rad)
            n = (ii[(y1 + 1) * (w + 1) + x1 + 1] - ii[y0 * (w + 1) + x1 + 1]
                 - ii[(y1 + 1) * (w + 1) + x0] + ii[y0 * (w + 1) + x0])
            if n >= thresh * area:
                out[y * w + x] = 1
    return out


def label_runs(page, clip=None, dpi=200, rad=4, thresh=0.24,
               gap=9, hmin=4, hmax=18, min_px=10, min_w=10):
    """定位位图／描边图里的**文字串**（先按局部密度剔除线条）。

    返回 PDF 矩形列表，按阅读顺序（先行后列）。比 `raster_runs` 稳 ——
    后者不做密度分离，引出线会污染连通块。
    """
    box = fitz.Rect(clip) if clip else page.rect
    sc = dpi / 72.0
    dk, w, h = _dark_map(page, box, dpi)
    tm = _density_mask(dk, w, h, rad, thresh)
    seen = bytearray(w * h)
    parts = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not tm[i] or seen[i]:
                continue
            st = [(x, y)]
            seen[i] = 1
            x0 = x1 = x
            y0 = y1 = y
            n = 0
            while st:
                cx, cy = st.pop()
                n += 1
                if cx < x0:
                    x0 = cx
                if cx > x1:
                    x1 = cx
                if cy < y0:
                    y0 = cy
                if cy > y1:
                    y1 = cy
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                               (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        j = ny * w + nx
                        if tm[j] and not seen[j]:
                            seen[j] = 1
                            st.append((nx, ny))
            bh = y1 - y0 + 1
            if hmin <= bh <= hmax and n >= min_px:
                parts.append((x0, y0, x1, y1))
    parts.sort(key=lambda b: (round(b[1] / 6), b[0]))
    runs = []
    for b in parts:
        if runs:
            rx0, ry0, rx1, ry1 = runs[-1]
            ov = min(ry1, b[3]) - max(ry0, b[1])
            if ov > 0.35 * min(ry1 - ry0 + 1, b[3] - b[1] + 1) \
                    and b[0] - rx1 <= gap:
                runs[-1] = (min(rx0, b[0]), min(ry0, b[1]),
                            max(rx1, b[2]), max(ry1, b[3]))
                continue
        runs.append(b)
    out = []
    for rx0, ry0, rx1, ry1 in runs:
        if rx1 - rx0 < min_w:
            continue
        out.append(fitz.Rect(box.x0 + rx0 / sc, box.y0 + ry0 / sc,
                             box.x0 + rx1 / sc, box.y0 + ry1 / sc))
    return out


def snap(page, approx, dpi=150, rad=4, thresh=0.24, pad=1.2, grow=6.0,
         min_frac=0.0):
    """把**粗略给出的**标注框吸附到真实墨迹上。

    图内标注的自动配框始终不稳（引出线与字母连成同一连通块时，
    该块因过大被滤掉，框就缺字母；放宽合并间距又会把相邻两条并成一条）。
    但只要人给出**粗略范围**，精确边界完全可以算：
    在该范围内按局部密度剔掉线条，取剩余文字像素的包围盒即可。

    **搜索区要向外扩张 `grow`**：只在粗框内找的话，粗框稍偏就只取到标注的
    一部分，成品上剩下半截英文（实测第 67 页 `Fill Hose Rack` 只盖住 `Hose`）。
    扩张后按**连通块**取「与粗框重叠最多的那一块」，并把同一行、间距小于
    一个字宽的相邻块并进来 —— 这样粗框只需大致命中，边界由程序定。

    ⚠ `min_frac` —— **防塌缩闸门**（避坑 84）。吸附只该微调，不该把框收掉
    一大半：实测一条 51pt 宽的 `Kelly Mandrel`，snap 收到单个笔画连通块上、
    只剩 25pt，描白因此只盖住 `Kell`，右半截英文原样留在成品图里，
    **而回叠计数照报成功**。传入 0.72 表示「宽或高收到不足 72% 就判吸附失败、
    返回 None」，调用方退回自己量的粗框。默认 0.0 保持既有行为不变；
    **新写的回叠一律传 min_frac**。

    另：若粗框本身已由检测器在源页上按墨迹检出（`figlabel`/`propose` 这类），
    就**不要再吸附**——那已经是精确框，再吸附只会引入位移。
    """
    rough = fitz.Rect(approx)
    box = fitz.Rect(rough) + (-grow, -grow, grow, grow)
    sc = dpi / 72.0
    dk, w, h = _dark_map(page, box, dpi)
    tm = _density_mask(dk, w, h, rad, thresh)
    seen = bytearray(w * h)
    comps = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not tm[i] or seen[i]:
                continue
            st = [(x, y)]
            seen[i] = 1
            x0 = x1 = x
            y0 = y1 = y
            n = 0
            while st:
                cx, cy = st.pop()
                n += 1
                if cx < x0:
                    x0 = cx
                if cx > x1:
                    x1 = cx
                if cy < y0:
                    y0 = cy
                if cy > y1:
                    y1 = cy
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                               (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        j = ny * w + nx
                        if tm[j] and not seen[j]:
                            seen[j] = 1
                            st.append((nx, ny))
            comps.append((fitz.Rect(box.x0 + x0 / sc, box.y0 + y0 / sc,
                                    box.x0 + x1 / sc, box.y0 + y1 / sc), n))
    if not comps:
        return None
    # 与粗框重叠面积最大的连通块作种子
    seed = max(comps, key=lambda c: (c[0] & rough).get_area())[0]
    if (seed & rough).get_area() <= 0:
        seed = min(comps, key=lambda c: abs((c[0].y0 + c[0].y1) / 2
                                            - (rough.y0 + rough.y1) / 2))[0]
    cw = max(seed.height * 0.9, 3.0)          # 一个字宽的估计
    # 同一行、与种子块横向间距小于一个字宽的块并进来。左右各扫一遍即可 ——
    # 反复全扫是 O(n²)，本页 17 条标注就跑成分钟级。
    same = [r for r, _n in comps
            if min(seed.y1, r.y1) - max(seed.y0, r.y0)
            >= 0.35 * min(seed.height, r.height)]
    out = fitz.Rect(seed)
    for r in sorted([r for r in same if r.x0 >= seed.x1 - 0.5],
                    key=lambda r: r.x0):
        if r.x0 - out.x1 > cw:
            break
        out |= r
    for r in sorted([r for r in same if r.x1 <= seed.x0 + 0.5],
                    key=lambda r: -r.x1):
        if out.x0 - r.x1 > cw:
            break
        out |= r
    out = out + (-pad, -pad, pad, pad)
    # 防塌缩：吸附只许微调。收掉一大半说明种子落在了某个笔画上，
    # 此时**宁可退回粗框**（调用方自己量的），也不要交出一个盖不住英文的框。
    if min_frac and (out.width < min_frac * rough.width
                     or out.height < min_frac * rough.height):
        return None
    return out


def slant(page, line, zh, h=8.0, fill=(1, 1, 1), color=(0, 0, 0), pad=0.9,
          font="zh", fontfile=None, up=0.40):
    """**任意角度**的图内标注回叠（贴着曲线排的图表图例说明）。

    此前这类标注只能「保留英文 + 附录说明」，理由是 `insert_textbox` 的
    `rotate` 只认 90° 的整数倍。其实两件事都能做（实测 API 载荷包络图
    Po/PQ/PT3T2/PT4T2 四条全部贴回）：

      · 写字改走 `insert_text(morph=(pivot, matrix))`，角度任意；
      · 描白改用**旋转四边形**（`draw_quad`）。轴对齐矩形会把标注旁边的
        曲线连带啃掉一大块 —— 这类标注恰恰就压在曲线上。

    `line` = 基线两端点 (x0, y0, x1, y1)，由人从带坐标网格的出图上读；
    角度、长度、中心全部由此算出，**不必手填角度**。
    `h` 取原英文的字面高度（略放一点，框要吃掉降部与上标，否则卡在墨迹上
    会留一小截黑渣，避坑 87）。

    ⚠ **两处旋转的符号相反**（避坑 85）：`Point * Matrix` 直接在页坐标
    （y 向下）里乘，正角即视觉顺时针 ⇒ 四边形用 `+deg`；而
    `insert_text(morph=…)` 的矩阵作用在**文本空间**（y 向上）⇒ 文字用 `-deg`。
    取同一个符号：要么字往右上排、要么描白框转反了（英文没抹掉、却在别处
    啃出缺口）—— 两种都实测见过。
    """
    import math
    from dwg_overlay import ZH_FONT, _width
    x0, y0, x1, y1 = line
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    if L < 1:
        return 0
    deg = math.degrees(math.atan2(dy, dx))
    ux, uy = dx / L, dy / L
    nx, ny = uy, -ux                        # 指向「上方」的垂线（页坐标 y 向下）
    # 字身在**基线之上**：四边形若以基线为中心上下对开，上半盖不全字、
    # 下半却啃掉基线下方的曲线 ⇒ 整体沿垂线上移 up×h。
    cx = (x0 + x1) / 2 + up * h * nx
    cy = (y0 + y1) / 2 + up * h * ny
    mq, mt = fitz.Matrix(deg), fitz.Matrix(-deg)
    hw, hh = L / 2 + pad, 0.62 * h + pad
    pts = []
    for lx, ly in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        p = fitz.Point(lx, ly) * mq
        pts.append(fitz.Point(p.x + cx, p.y + cy))
    page.draw_quad(fitz.Quad(pts[0], pts[1], pts[3], pts[2]), color=None, fill=fill)
    page.insert_font(fontname=font, fontfile=fontfile or ZH_FONT)
    s = h * 0.96
    while s > 3.0 and _width(zh, s) > L:
        s -= 0.2
    off = (L - _width(zh, s)) / 2.0         # 中文更短，沿基线居中
    sx, sy = x0 + ux * off, y0 + uy * off
    page.insert_text(fitz.Point(sx, sy), zh, fontname=font, fontsize=s,
                     color=color, morph=(fitz.Point(sx, sy), mt))
    return 1


def snap_all(page, items, **kw):
    """`items` = [(粗略矩形, 中文)] → [(吸附后矩形, 中文)]。吸附失败者原样保留。"""
    out = []
    for r, t in items:
        s = snap(page, r, **kw)
        out.append((s or fitz.Rect(r), t))
    return out
