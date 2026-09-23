# -*- coding: utf-8 -*-
"""定级：给一个 PDF，逐页量指标，给出 V2 版面三级（R / H / P / S）建议。

V2 公理：忠实的对象是**内容与表达方式**，不是英文版的物理坐标。所以
默认是 **R 语义重排**（抽结构 → 译 → 按中文版式流式排版），只有「版面本身
就是内容」的页才保位叠印：

    P 版面保持   工程图纸（图面 ≥ 70% 或 路径 ≥ 3000/页）、可填写表单（勾选框 ≥ 15/页）
    S 幻灯片     横开 + 大字号（主导字号 ≥ 18pt）的 PPT 导出页：整页保位，页内列表整列重排
    R 语义重排   其余散文 / 步骤 / 普通表格页（默认）
    H 混合       同一文档里 R 与 P 页并存 → 逐页分流

⚠ V1 的「页数 ≥ 20 → 叠印」判据**已作废**：重排不追坐标，成本与页数脱钩。
⚠ 不要用「路径数/字符数」这类比值，也不要拿「扁长矩形」当填写横线 ——
  表格单元格边框同样是扁长矩形，实测会把 8 份纯文字档全判成表单。

用法：
    python route.py <file.pdf> [more.pdf ...] [--json out.json] [--max-pages 80]
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import json
import os
import sys
from collections import Counter

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz

MAX_PAGES = 80       # 超长文档均匀抽样，够用且快


def page_metrics(pg):
    """单页指标：图面占比%、路径数、勾选框数、字符数、主导字号、是否横开。"""
    A = pg.rect.get_area() or 1.0
    text = pg.get_text("dict")
    chars, sizes = 0, Counter()
    for b in text["blocks"]:
        for ln in b.get("lines", ()):
            for s in ln["spans"]:
                n = len(s["text"].strip())
                chars += n
                sizes[round(s["size"])] += n
    drs = pg.get_drawings()
    boxes = [fitz.Rect(im["bbox"]) for im in pg.get_image_info()]
    cbs = 0
    for dr in drs:
        r = fitz.Rect(dr["rect"])
        if r.width > 20 and r.height > 20 and r.get_area() < 0.9 * A:
            boxes.append(r)
        # 勾选框：近正方形的小矩形 —— 可填写表单的硬指标
        if 3.0 <= r.width <= 11.0 and 3.0 <= r.height <= 11.0 and abs(r.width - r.height) < 2.0:
            cbs += 1
    cells = set()                     # 并集按 8pt 网格估算，避免 O(n²)
    for r in boxes:
        for x in range(int(r.x0 // 8), int(r.x1 // 8) + 1):
            for y in range(int(r.y0 // 8), int(r.y1 // 8) + 1):
                cells.add((x, y))
    fig = min(100.0, len(cells) * 64.0 / A * 100)
    dom = sizes.most_common(1)[0][0] if sizes else 0
    landscape = pg.rect.width > pg.rect.height
    return dict(fig=fig, paths=len(drs), cbs=cbs, chars=chars, dom=dom,
                landscape=landscape)


def page_level(m):
    if m["fig"] >= 70 or m["paths"] >= 3000:
        return "P", "图纸"
    if m["cbs"] >= 15:
        return "P", "表单"
    if m["landscape"] and m["dom"] >= 18:
        return "S", "幻灯片"
    if m["chars"] < 30 and m["fig"] < 20:
        return "R", "空白/分隔页"
    return "R", "散文/步骤/表格"


def classify(path, max_pages=MAX_PAGES):
    d = fitz.open(path)
    n = d.page_count
    step = max(1, -(-n // max_pages))
    idx = list(range(0, n, step))
    rows = []
    for i in idx:
        m = page_metrics(d[i])
        lv, why = page_level(m)
        rows.append(dict(page=i + 1, level=lv, kind=why, **m))
    d.close()
    cnt = Counter(r["level"] for r in rows)
    chars = sum(r["chars"] for r in rows) / max(1, len(rows))
    if chars < 200 and sum(r["fig"] for r in rows) / max(1, len(rows)) < 70:
        doc, why = "R", ("文本层几乎为空（%.0f 字符/页）—— 文字已被转成曲线或是扫描件，"
                         "只能 OCR/视觉转录后重排" % chars)
    elif cnt["S"] >= 0.6 * len(rows):
        doc, why = "S", "PPT 导出：整页保位 + 页内列表整列重排（references/slides.md）"
    elif cnt["P"] and cnt["R"]:
        doc, why = "H", "R 页 %d、P 页 %d：逐页分流，正文页重排、图纸/表单页叠印" % (cnt["R"], cnt["P"])
    elif cnt["P"]:
        doc, why = "P", "全是图纸/表单：原页叠印（references/overlay.md）"
    else:
        doc, why = "R", "散文/步骤/表格为主：语义重排（默认路线）"
    return dict(file=path, pages=n, sampled=len(rows), level=doc, reason=why,
                counts=dict(cnt), p_pages=[r["page"] for r in rows if r["level"] == "P"],
                s_pages=[r["page"] for r in rows if r["level"] == "S"], rows=rows)


def main(argv):
    args = argv[1:]
    out_json, maxp = None, MAX_PAGES
    if "--json" in args:
        k = args.index("--json"); out_json = args[k + 1]; del args[k:k + 2]
    if "--max-pages" in args:
        k = args.index("--max-pages"); maxp = int(args[k + 1]); del args[k:k + 2]
    if not args:
        print(__doc__)
        return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    res = []
    for p in args:
        if not os.path.isfile(p):
            print("跳过（不存在）", p)
            continue
        r = classify(p, maxp)
        res.append(r)
        print("%s  %d 页（抽 %d）  定级 %s  —— %s"
              % (os.path.basename(p), r["pages"], r["sampled"], r["level"], r["reason"]))
        if r["p_pages"]:
            print("    P 级页：", r["p_pages"][:40])
        if r["s_pages"] and r["level"] != "S":
            print("    S 级页：", r["s_pages"][:40])
    if out_json:
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    print("\n注：这是建议不是判决。再问三问：坐标有语义吗？格子要回填吗？"
          "删掉版式重排后信息有损吗？任一为是 → 该页保位。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
