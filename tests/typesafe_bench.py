# -*- coding: utf-8 -*-
"""TypeSafe 图像判断小规模对照：现有启发式 vs Jev（jev-1.14.0）。没有密钥时**跳过并说明**，返回 0。

    py tests\\typesafe_bench.py            # Windows；macOS / Linux 用 python3
    py tests\\typesafe_bench.py --dry-run  # 不联网：只构造全部请求、核对每张图与请求体在上游限制内、数请求数

样本（都在仓库里，无客户资料）：
    docs/showcase/SWI-650-SS_Assembly_en.pdf   R 级作业指导书（11 页，页级真值 R）
    docs/showcase/TDT-650-0100_Assembly_en.pdf P 级总装图（3 张，页级真值 P）
    tests/gen_testdocs.py 生成的 3 份样例        R / R / P（与 smoke_test 相同）
对照项：
    ① 页面级别：启发式 route.page_level vs TypeSafe Choice(R/P/S/blank；blank 计作 R)，Choice 的 criteria
       带示例页图（SWI 第 2 页作 R 例、TDT 第 1 页作 P 例；评测时**排除示例页本身**）；
    ② 插图框：对 SWI 跑 figpipe extract → sr（无 torch 时为 Lanczos 放大）→ detect，再逐框问
       「是文字标注 / 是件号气泡」，真值取 examples/showcase-swi/content/labels_zh.py —— 只在该图检测框数
       与 labels_zh 登记数一致时计分（框号由检测给出，超分后端不同可能导致框数不同，不一致的图报出并跳过）；
    ③ 表格区：对 TDT 的 tablefix.regions() 逐块问「真表格」，只列概率（样本里没有已标注的负例，不计准确率）。
输出：准确率、每页 / 每框 token 用量、耗时，并写 tests/_out/typesafe_bench.json。
把结果数字填进 references/typesafe.md 的「实测」表时，一并写上日期与模型版本。
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pdf-translate-zh", "scripts")
OUT = os.path.join(ROOT, "tests", "_out", "typesafe_bench")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402
bootstrap.ensure(quiet=True)
import tsjudge  # noqa: E402

SWI = os.path.join(ROOT, "docs", "showcase", "SWI-650-SS_Assembly_en.pdf")
TDT = os.path.join(ROOT, "docs", "showcase", "TDT-650-0100_Assembly_en.pdf")
LABELS = os.path.join(ROOT, "examples", "showcase-swi", "content", "labels_zh.py")
# PDF_ZH_SR_AUTOINSTALL=0：对照测试不该顺带触发 torch 自动安装（无 torch 时 sr.py 退回 Lanczos，框数可能与 labels_zh 不同 —— 不一致的图会被报出并跳过）
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PDF_ZH_SR_AUTOINSTALL="0")


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    return fitz


def _samples():
    """[(pdf, 真值级别)]。"""
    fitz = _fitz()
    out = [(SWI, "R"), (TDT, "P")]
    gen = os.path.join(OUT, "gen")
    os.makedirs(gen, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "gen_testdocs.py"), gen],
                   check=True, env=ENV, capture_output=True)
    for f, lv in (("mud_motor_manual.pdf", "R"), ("mud_motor_manual_long.pdf", "R"),
                  ("stator_housing_drawing.pdf", "P")):
        p = os.path.join(gen, f)
        if os.path.exists(p):
            out.append((p, lv))
    for p, _lv in out:
        with fitz.open(p):
            pass
    return out


def bench_pages(dry):
    """① 页面级别。返回统计 dict。"""
    import route
    fitz = _fitz()
    examples = {"R": [tsjudge.page_png(fitz.open(SWI)[1])], "P": [tsjudge.page_png(fitz.open(TDT)[0])]}
    skip = {(SWI, 2), (TDT, 1)}
    rows, n_req = [], 0
    for pdf, truth in _samples():
        with fitz.open(pdf) as d:
            for i in range(d.page_count):
                if (pdf, i + 1) in skip:
                    continue
                m = route.page_metrics(d[i])
                heur = route.page_level(m)[0]
                png = tsjudge.page_png(d[i])
                if dry:
                    pg = tsjudge.prepare_image(png)
                    ref, a = tsjudge.asset(pg)
                    assets = {ref: a}
                    ex = {}
                    for k, ims in examples.items():
                        for im in ims:
                            r, aa = tsjudge.asset(tsjudge.prepare_image(im))
                            assets[r] = aa
                            ex.setdefault(k, []).append(r)
                    body = tsjudge.build_request({"page": ref}, {"level": {"type": "choice", "instructions": "x",
                                                                           "criteria": tsjudge.level_criteria(ex)}},
                                                 assets)
                    n_req += 1
                    rows.append(dict(pdf=os.path.basename(pdf), page=i + 1, truth=truth, heur=heur,
                                     bytes=len(body), px="%dx%d" % (pg.w, pg.h)))
                    continue
                r = tsjudge.page_level(png, examples)
                ts = r["level"] if r["level"] != "blank" else "R"
                rows.append(dict(pdf=os.path.basename(pdf), page=i + 1, truth=truth, heur=heur, ts=ts,
                                 ts_raw=r["level"], conf=round(r["confidence"], 3),
                                 tokens=r["input_tokens"], seconds=r["seconds"]))
                print("  %-32s p%-3d 真值 %s  启发式 %s  TypeSafe %-5s conf %.2f  %5d tok  %.1fs%s" % (
                    os.path.basename(pdf), i + 1, truth, heur, r["level"], r["confidence"],
                    r["input_tokens"], r["seconds"], "" if ts == truth else "  ← 错"))
    if dry:
        return dict(pages=len(rows), requests=n_req, max_bytes=max(r["bytes"] for r in rows), rows=rows)
    n = len(rows)
    return dict(pages=n,
                heuristic_acc=sum(1 for r in rows if r["heur"] == r["truth"]) / max(1, n),
                typesafe_acc=sum(1 for r in rows if r["ts"] == r["truth"]) / max(1, n),
                tokens_per_page=sum(r["tokens"] for r in rows) / max(1, n),
                seconds_per_page=sum(r["seconds"] for r in rows) / max(1, n), rows=rows)


def _labels_truth():
    import importlib.util
    spec = importlib.util.spec_from_file_location("labels_zh", LABELS)
    mod = importlib.util.module_from_spec(spec)
    import figpipe
    sys.modules.setdefault("figpipe", figpipe)
    spec.loader.exec_module(mod)
    return mod.LABELS, mod.BUBBLES


def bench_figures(dry):
    """② 插图框。真值：labels_zh 的译名 → text；KEEP 且在 BUBBLES → bubble；SKIP → neither；KEEP 非气泡 → 不计。"""
    from PIL import Image
    import figpipe
    work = os.path.join(OUT, "swi")
    os.makedirs(work, exist_ok=True)
    figpipe.extract(SWI, work)
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "sr.py"), os.path.join(work, "figures_src"),
                    os.path.join(work, "figures_sr"), "--places", os.path.join(work, "data", "images.json"),
                    "--min-dpi", "150"], check=True, env=ENV, capture_output=True)
    boxes = figpipe.detect(work)
    LAB, BUB = _labels_truth()
    sdir = os.path.join(work, "figures_sr")
    stats = dict(figures=0, skipped=[], boxes=0, text_ok=0, bubble_ok=0, tokens=0, seconds=0.0, requests=0, rows=[])
    for stem, bs in boxes.items():
        lab = LAB.get(stem)
        if lab is None:
            continue
        n_reg = sum(1 for k in lab if isinstance(k, int))
        if n_reg != len(bs):
            stats["skipped"].append("%s（检测 %d 框，labels_zh 登记 %d 框）" % (stem, len(bs), n_reg))
            continue
        im = Image.open(os.path.join(sdir, stem + ".png"))
        if dry:
            for i in range(0, len(bs), tsjudge.CROPS_PER_REQUEST):
                chunk = bs[i:i + tsjudge.CROPS_PER_REQUEST]
                assets = {}
                r, a = tsjudge.asset(tsjudge.prepare_image(im))
                assets[r] = a
                for b in chunk:
                    crop, _ = tsjudge._crop_pad(im.convert("RGB"), b)
                    rr, aa = tsjudge.asset(tsjudge.prepare_image(crop))
                    assets[rr] = aa
                body = tsjudge.build_request({"x": list(assets)}, {"q": {"type": "noul", "instructions": "x"}}, assets)
                stats["requests"] += 1
                stats["rows"].append(dict(stem=stem, crops=len(chunk), bytes=len(body)))
            stats["figures"] += 1
            stats["boxes"] += len(bs)
            continue
        h = tsjudge.figure_hints(im, bs)
        stats["figures"] += 1
        stats["tokens"] += h["input_tokens"]
        stats["seconds"] += h["seconds"]
        stats["requests"] += h["requests"]
        for i, b in enumerate(bs):
            z = lab.get(i)
            truth = ("bubble" if i in BUB.get(stem, {}) else None) if z == figpipe.KEEP else \
                    ("neither" if z == figpipe.SKIP else "text")
            if truth is None:
                continue
            p = h["boxes"][i]
            t_ok = (p["text"] >= tsjudge.NOUL_YES) == (truth == "text")
            b_ok = (p["bubble"] >= tsjudge.NOUL_YES) == (truth == "bubble")
            stats["boxes"] += 1
            stats["text_ok"] += 1 if t_ok else 0
            stats["bubble_ok"] += 1 if b_ok else 0
            stats["rows"].append(dict(stem=stem, box=i, truth=truth, text=p["text"], bubble=p["bubble"]))
        print("  %s: %d 框  has_text %.2f  %d tok  %.1fs" % (stem, len(bs), h["has_text"], h["input_tokens"], h["seconds"]))
    if not dry and stats["boxes"]:
        stats["text_acc"] = stats["text_ok"] / stats["boxes"]
        stats["bubble_acc"] = stats["bubble_ok"] / stats["boxes"]
        stats["tokens_per_box"] = stats["tokens"] / stats["boxes"]
    return stats


def bench_tables(dry):
    """③ 表格区：只列概率。"""
    import tablefix
    import io
    from PIL import Image
    fitz = _fitz()
    rows = []
    with fitz.open(TDT) as d:
        for pi, pg in enumerate(d):
            for k, r in enumerate(tablefix.regions(pg)):
                pm = pg.get_pixmap(clip=r, matrix=fitz.Matrix(2.5, 2.5), alpha=False)
                im = Image.open(io.BytesIO(pm.tobytes("png")))
                if dry:
                    pr = tsjudge.prepare_image(im)
                    rows.append(dict(page=pi + 1, region=k, px="%dx%d" % (pr.w, pr.h)))
                    continue
                p, tok, sec = tsjudge.table_is_grid(im)
                rows.append(dict(page=pi + 1, region=k, grid=round(p, 3), tokens=tok, seconds=round(sec, 2)))
                print("  TDT p%d 区域 %d  真表格 %.2f  %d tok  %.1fs" % (pi + 1, k, p, tok, sec))
    return dict(regions=len(rows), rows=rows)


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    dry = "--dry-run" in argv
    if not dry and not tsjudge.enabled():
        print("SKIP typesafe_bench：" + tsjudge.status_line())
        print("  " + tsjudge.REMINDER)
        print("  不联网核对请求构造：--dry-run")
        return 0
    if not os.path.exists(SWI) or not os.path.exists(TDT):
        print("SKIP typesafe_bench：缺 docs/showcase 样例 PDF")
        return 0
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    print("[1] 页面级别（启发式 vs TypeSafe）" + ("  —— dry-run" if dry else ""))
    pages = bench_pages(dry)
    print("[2] 插图框（文字标注 / 件号气泡）")
    figs = bench_figures(dry)
    print("[3] 表格区（真表格概率）")
    tabs = bench_tables(dry)
    res = dict(model=tsjudge.MODEL, docs_date=tsjudge.DOCS_DATE, dry_run=dry,
               thresholds=dict(noul_yes=tsjudge.NOUL_YES, box_min_conf=tsjudge.BOX_MIN_CONF),
               pages=pages, figures=figs, tables=tabs, total_seconds=round(time.time() - t0, 1))
    with open(os.path.join(ROOT, "tests", "_out", "typesafe_bench.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    if dry:
        print("\ndry-run：页面请求 %d 个（最大 %.2f MiB）；插图请求 %d 个（%d 幅 %d 框，跳过 %s）；表格区 %d 块；"
              "全部图片与请求体在上游限制内。" % (pages["requests"], pages["max_bytes"] / 2.0 ** 20, figs["requests"],
                                        figs["figures"], figs["boxes"], figs["skipped"] or "无", tabs["regions"]))
        return 0
    print("\n页面级别：%d 页  启发式准确率 %.0f%%  TypeSafe 准确率 %.0f%%  %.0f tok/页  %.1f s/页" % (
        pages["pages"], 100 * pages["heuristic_acc"], 100 * pages["typesafe_acc"],
        pages["tokens_per_page"], pages["seconds_per_page"]))
    if figs["boxes"] and "text_acc" in figs:
        print("插图框：%d 幅 %d 框  文字标注判对 %.0f%%  气泡判对 %.0f%%  %.0f tok/框  %.1f s/幅（跳过 %s）" % (
            figs["figures"], figs["boxes"], 100 * figs["text_acc"], 100 * figs["bubble_acc"],
            figs["tokens_per_box"], figs["seconds"] / max(1, figs["figures"]), figs["skipped"] or "无"))
    print("表格区：%d 块（概率见 tests/_out/typesafe_bench.json）" % tabs["regions"])
    print("模型 %s；上游文档核实日期 %s；阈值 noul_yes=%.2f。把数字填进 references/typesafe.md 时写上今天日期。"
          % (tsjudge.MODEL, tsjudge.DOCS_DATE, tsjudge.NOUL_YES))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
