# -*- coding: utf-8 -*-
"""定级：给一个 PDF，逐页量指标，给出 V2 版面三级（R / H / P / S）建议。

V2 公理：忠实的对象是**内容与表达方式**，不是英文版的物理坐标。所以
默认是 **R 语义重排**（抽结构 → 译 → 按中文版式流式排版），只有「版面本身
就是内容」的页才保位叠印：

    S 幻灯片     横开 + 大字号（主导字号 ≥ 18pt；或 ≥ 12pt 且字少 < 500、图面 ≥ 50%）的 PPT 导出页：
                 整页保位，页内列表整列重排。**S 判据排在 P 之前**：讲义页满版照片会先触发图纸判据
                 （2026-10-20 实测 16 页讲义全判成图纸，references/typesafe.md §6.1）
    P 版面保持   工程图纸（图面 ≥ 70% 或 路径 ≥ 3000/页）、可填写表单（勾选框 ≥ 15/页，
                 或 填写位 ≥ 8：带标签的空白横线 + 下划线串 + 冒号标签后留白）
    R 语义重排   其余散文 / 步骤 / 普通表格页（默认）
    H 混合       同一文档里 R 与 P 页并存 → 逐页分流

⚠ V1 的「页数 ≥ 20 → 叠印」判据**已作废**：重排不追坐标，成本与页数脱钩。
⚠ 不要用「路径数/字符数」这类比值，也不要拿「扁长矩形」当填写横线 ——
  表格单元格边框同样是扁长矩形，实测会把 8 份纯文字档全判成表单。
  「填写位」判据因此只认**线上线下都没有字、且左端有标签词**的横线（表格行线上下必有字）；
  实测 23 页表单命中 15、非表单页零误判（但空白格靠标题在上方的表单、横开装配汇总表仍漏）。

用法：
    python route.py <file.pdf> [more.pdf ...] [--json out.json] [--max-pages 80] [--typesafe]

--typesafe（或环境变量 PDF_ZH_TYPESAFE=1 且设有 TYPESAFE_API_KEY）：另把每个抽样页渲染成图，
交给 TypeSafe 的 Jev 模型做一次 Choice（R/P/S/空白），结果写进各行的 `ts`；模型 confidence ≥ TS_OVERRIDE_CONF
（0.8）且与启发式不同时**以模型为准**（该行 `level` 改写，原判保留在 `heur_level`，`ts_applied=True`），
否则仍用启发式。依据：2026-10-20 真实文档 122 页，启发式 68 对、模型 102 对、按 0.8 组合 111 对
（references/typesafe.md §6.1）。文档级另记 `ts_disagree`、`ts_applied`、`ts_usage`。
关闭时本脚本不会 import tsjudge。
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
TS_OVERRIDE_CONF = 0.8   # --typesafe 时模型置信度达到此值即覆盖启发式（2026-10-20 在 122 页上定的；低于它退回启发式）


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
                landscape=landscape, form=form_slots(pg))


def form_slots(pg):
    """填写位计数 = 带标签的空白横线 + 下划线串 `____` + 冒号标签后留白。

    空白横线：线段 25~300pt（经 dwg_bom.segments 合并共线短段），线上、线下 11pt 内都没有字
    （表格行线上下必有字，故不会把表格当表单），且左端 40pt 内同一行有词（标签）。
    2026-10-20 在 23 页真实表单上命中 15 页、非表单页零误判；靠上方标题定位的空白格仍认不出。
    """
    import re
    from dwg_bom import segments
    words = pg.get_text("words")
    wr = [fitz.Rect(w[:4]) for w in words]

    def any_in(r):
        return any(x.intersects(r) for x in wr)
    try:
        H, _V = segments(pg, min_h=25.0, min_v=3.0)
    except Exception:
        H = []
    nlab = 0
    for y, x0, x1 in H:
        if x1 - x0 > 300:
            continue
        if any_in(fitz.Rect(x0 + 2, y - 11, x1 - 2, y - 0.5)) or any_in(fitz.Rect(x0 + 2, y + 0.5, x1 - 2, y + 11)):
            continue
        if any_in(fitz.Rect(x0 - 40, y - 10, x0 - 0.5, y + 2)):
            nlab += 1
    us = sum(1 for w in words if re.fullmatch(r"_{4,}", w[4]))
    cb = sum(1 for w in words
             if w[4].endswith(":") and not any_in(fitz.Rect(w[2] + 1, w[1], w[2] + 120, w[3])))
    return nlab + us + cb


def page_level(m):
    # 幻灯片先于图纸：讲义页的满版照片会触发「图面 ≥ 70%」
    if m["landscape"] and (m["dom"] >= 18 or (m["dom"] >= 12 and m["chars"] < 500 and m["fig"] >= 50)):
        return "S", "幻灯片"
    if m["fig"] >= 70 or m["paths"] >= 3000:
        return "P", "图纸"
    if m["cbs"] >= 15 or m.get("form", 0) >= 8:
        return "P", "表单"
    if m["chars"] < 30 and m["fig"] < 20:
        return "R", "空白/分隔页"
    return "R", "散文/步骤/表格"


def _ts_wanted(flag):
    """None = 看环境变量开关；True/False = 调用方明示。只有为真时才 import tsjudge。"""
    if flag is None:
        flag = os.environ.get("PDF_ZH_TYPESAFE", "").strip().lower() in ("1", "true", "yes", "on")
    if not flag:
        return None
    import tsjudge
    return tsjudge if tsjudge.enabled() else None


def _ts_page(ts, pg, row):
    """TypeSafe 判一页，结果挂到 row["ts"]；任何失败只记一条 error，不影响启发式。"""
    try:
        r = ts.page_level(ts.page_png(pg))
        row["ts"] = dict(level=r["level"], confidence=round(r["confidence"], 3),
                         probabilities={k: round(v, 3) for k, v in r["probabilities"].items()},
                         input_tokens=r["input_tokens"], seconds=r["seconds"])
    except Exception as e:                      # 网络/配额/格式变动：一行提示，启发式结果原样
        row["ts"] = dict(error="%s: %s" % (type(e).__name__, e))


def classify(path, max_pages=MAX_PAGES, typesafe=None):
    ts = _ts_wanted(typesafe)
    d = fitz.open(path)
    n = d.page_count
    step = max(1, -(-n // max_pages))
    idx = list(range(0, n, step))
    rows = []
    for i in idx:
        m = page_metrics(d[i])
        lv, why = page_level(m)
        row = dict(page=i + 1, level=lv, kind=why, **m)
        if ts is not None:
            _ts_page(ts, d[i], row)
            t = row["ts"]
            if "level" in t:
                tl = t["level"] if t["level"] != "blank" else "R"
                if tl != lv and t["confidence"] >= TS_OVERRIDE_CONF:
                    row["heur_level"], row["level"], row["ts_applied"] = lv, tl, True
                    row["kind"] = "TypeSafe %s（conf %.2f）覆盖启发式 %s/%s" % (t["level"], t["confidence"], lv, why)
        rows.append(row)
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
    res = dict(file=path, pages=n, sampled=len(rows), level=doc, reason=why,
               counts=dict(cnt), p_pages=[r["page"] for r in rows if r["level"] == "P"],
               s_pages=[r["page"] for r in rows if r["level"] == "S"], rows=rows)
    if ts is not None:
        # 对照记录：模型判「blank」视同 R（空白页本就走重排）；分歧页只列出，判级不改
        ok = [r for r in rows if "ts" in r and "level" in r["ts"]]
        dis = [r["page"] for r in ok
               if (r["ts"]["level"] if r["ts"]["level"] != "blank" else "R") != r.get("heur_level", r["level"])]
        res["ts_model"] = ts.MODEL
        res["ts_override_conf"] = TS_OVERRIDE_CONF
        res["ts_disagree"] = dis
        res["ts_applied"] = [r["page"] for r in rows if r.get("ts_applied")]
        res["ts_errors"] = [r["page"] for r in rows if "ts" in r and "error" in r["ts"]]
        res["ts_usage"] = dict(pages=len(ok), input_tokens=sum(r["ts"]["input_tokens"] for r in ok),
                               seconds=round(sum(r["ts"]["seconds"] for r in ok), 1))
    return res


def main(argv):
    args = argv[1:]
    out_json, maxp = None, MAX_PAGES
    if "--json" in args:
        k = args.index("--json"); out_json = args[k + 1]; del args[k:k + 2]
    if "--max-pages" in args:
        k = args.index("--max-pages"); maxp = int(args[k + 1]); del args[k:k + 2]
    typesafe = None
    if "--typesafe" in args:
        args.remove("--typesafe")
        typesafe = True
        import tsjudge
        if not tsjudge.enabled():
            print(tsjudge.status_line() + "\n  " + tsjudge.REMINDER)
            typesafe = False
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
        r = classify(p, maxp, typesafe)
        res.append(r)
        print("%s  %d 页（抽 %d）  定级 %s  —— %s"
              % (os.path.basename(p), r["pages"], r["sampled"], r["level"], r["reason"]))
        if r["p_pages"]:
            print("    P 级页：", r["p_pages"][:40])
        if r["s_pages"] and r["level"] != "S":
            print("    S 级页：", r["s_pages"][:40])
        if "ts_usage" in r:
            u = r["ts_usage"]
            print("    TypeSafe（%s）：%d 页，分歧页 %s，其中 conf ≥ %.2f 已按模型改判 %s，出错页 %s，共 %d tok，%.1f s"
                  % (r["ts_model"], u["pages"], r["ts_disagree"] or "无", r["ts_override_conf"],
                     r["ts_applied"] or "无", r["ts_errors"] or "无", u["input_tokens"], u["seconds"]))
    if out_json:
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    print("\n注：这是建议不是判决。再问三问：坐标有语义吗？格子要回填吗？"
          "删掉版式重排后信息有损吗？任一为是 → 该页保位。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
