# -*- coding: utf-8 -*-
"""独立评分：检查代理（Antigravity + Gemini）交出的译稿，不信它的自述。

    py -3 grade.py            → 写 grade.json 与 grade.log

逐份文档：成品存在 → 重跑它写的 content/build.py（可复现、闸门全 PASS）→
独立复核附录 A/B 各自另起一页 → 统计正文中文占比、残留英文、术语条数、勘误条数。
"""
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(ROOT, ".agents", "skills", "pdf-translate-zh")
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402
bootstrap.ensure(quiet=True)
try:
    import pymupdf as fitz  # noqa: E402
except ImportError:
    import fitz  # noqa: E402
import checks  # noqa: E402
from appendix import A_TITLE, B_TITLE  # noqa: E402

DOCS = {"jar_field_guide": "R", "mandrel_drawing": "P"}
# 术语抽查：技能 references/industry.md 列为「外行必错」的词，正文必须用行业译名
MUST = {"jar_field_guide": ["震击器"], "mandrel_drawing": ["芯轴"]}
# 防抄：仓库示例文档（虚构品牌 Northstar / 675 螺杆钻具）的译文特征串
LEAK = ["螺杆钻具", "定子壳体", "NORTHSTAR"]
OUT = os.path.join(ROOT, "docs", "translated")
norm = lambda t: re.sub(r"\s+", "", t or "")  # noqa: E731
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s, flush=True)


def apx_layout(pdf):
    """按标题找附录起始页；并检查标题上方没有正文（页眉=与前一页同位置重复的文字）。"""
    res = {"pages": 0, "A": None, "B": None, "problems": []}
    with fitz.open(pdf) as d:
        res["pages"] = d.page_count
        for i, pg in enumerate(d):
            t = norm(pg.get_text())
            for k, title in (("A", A_TITLE), ("B", B_TITLE)):
                if res[k] is None and norm(title) in t:
                    res[k] = i + 1
        for k, title in (("A", A_TITLE), ("B", B_TITLE)):
            p = res[k]
            if p is None:
                res["problems"].append("附录 %s 缺失" % k)
                continue
            if p == 1:
                res["problems"].append("附录 %s 在第 1 页（无正文？）" % k)
                continue
            pg, prev = d[p - 1], d[p - 2]
            run = {(norm(b[4]), round(b[1])) for b in prev.get_text("blocks")}
            blocks = sorted(pg.get_text("blocks"), key=lambda b: b[1])
            hit = next(b for b in blocks if norm(title) in norm(b[4]))
            above = [b for b in blocks if b[3] <= hit[1] + 0.5 and norm(b[4])
                     and (norm(b[4]), round(b[1])) not in run]
            if above:
                res["problems"].append("附录 %s 首页标题上方有 %d 段正文（与正文同页）" % (k, len(above)))
        if res["A"] and res["B"] and res["B"] <= res["A"]:
            res["problems"].append("附录 B 不在附录 A 之后")
    return res


def body_stats(pdf, first_apx):
    cjk = lat = 0
    with fitz.open(pdf) as d:
        for i in range(0, (first_apx - 1) if first_apx else d.page_count):
            t = d[i].get_text()
            cjk += len(re.findall(r"[一-鿿]", t))
            lat += len(re.findall(r"[A-Za-z]{3,}", t))
    return cjk, lat


def main():
    report = {"docs": {}}
    allok = True
    for stem, level in DOCS.items():
        log("=" * 70)
        log("文档:", stem, "（预期定级 %s）" % level)
        r = {"expected_level": level}
        pdfs = sorted(glob.glob(os.path.join(OUT, stem + "_中文_v*.pdf")))
        if not pdfs:
            log("  FAIL 没有成品 PDF")
            r["ok"] = False
            allok = False
            report["docs"][stem] = r
            continue
        pdf = pdfs[-1]
        r["pdf"] = os.path.relpath(pdf, ROOT)
        rt = os.path.join(OUT, stem, "data", "route.json")
        if os.path.exists(rt):
            r["level"] = json.load(open(rt, encoding="utf-8")).get("level")
        build = os.path.join(OUT, stem, "content", "build.py")
        ok = True
        if os.path.exists(build):
            p = subprocess.run([sys.executable, "-X", "utf8", build], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            fails = [l.strip() for l in p.stdout.splitlines() if l.strip().startswith("FAIL")]
            r["rebuild_rc"] = p.returncode
            r["rebuild_fails"] = fails
            log("  重跑 build.py：rc=%d  %s" % (p.returncode, "全部 PASS" if not fails and p.returncode == 0 else "; ".join(fails)))
            ok &= p.returncode == 0 and not fails
            pdfs = sorted(glob.glob(os.path.join(OUT, stem + "_中文_v*.pdf")))
            pdf = pdfs[-1]
        else:
            log("  FAIL 找不到 content/build.py")
            ok = False
        lay = apx_layout(pdf)
        r["appendix"] = lay
        log("  附录分页：共 %d 页，A 起于 %s，B 起于 %s  %s" % (
            lay["pages"], lay["A"], lay["B"], "OK" if not lay["problems"] else lay["problems"]))
        ok &= not lay["problems"]
        cjk, lat = body_stats(pdf, lay["A"])
        r["body_cjk_chars"], r["body_latin_words"] = cjk, lat
        log("  正文中文字数 %d，正文 3 字母以上西文词 %d（含型号/标准号）" % (cjk, lat))
        allow = set(range(lay["A"], lay["pages"] + 1)) if lay["A"] else set()
        eng, half = checks.check_text(pdf, allow_pages=allow)
        r["residual_english_lines"] = len(eng)
        log("  残留英文行（缺省白名单，附录豁免）：%d  %s" % (len(eng), eng[:5]))
        r["glyph_missing"] = len(checks.check_glyphs(pdf))
        log("  缺字：%d" % r["glyph_missing"])
        ok &= r["glyph_missing"] == 0
        tp = os.path.join(OUT, stem, "content", "terms.py")
        if os.path.exists(tp):
            src = open(tp, encoding="utf-8").read()
            r["glossary_pairs"] = len(re.findall(r"\(\s*[\"'][^\"']+[\"']\s*,\s*[\"'][^\"']+[\"']", src))
            log("  terms.py 术语对（粗计）：%d" % r["glossary_pairs"])
        with fitz.open(pdf) as d:
            body = "".join(d[i].get_text() for i in range(0, (lay["A"] - 1) if lay["A"] else d.page_count))
        miss_terms = [t for t in MUST.get(stem, []) if t not in body]
        r["must_terms_missing"] = miss_terms
        log("  术语抽查 %s：%s" % (MUST.get(stem), "OK" if not miss_terms else "缺 %s" % miss_terms))
        ok &= not miss_terms
        cdir = os.path.join(OUT, stem, "content")
        leak = []
        for f in glob.glob(os.path.join(cdir, "*.py")):
            s = open(f, encoding="utf-8", errors="replace").read()
            leak += ["%s: %s" % (os.path.basename(f), k) for k in LEAK if k in s]
        r["leak"] = leak
        log("  抄示例检测：%s" % ("无" if not leak else leak))
        ok &= not leak
        r["ok"] = bool(ok)
        log("  结论：" + ("PASS" if ok else "FAIL"))
        allok &= ok
        report["docs"][stem] = r
    report["ok"] = bool(allok)
    report["report_md"] = os.path.exists(os.path.join(ROOT, "REPORT.md"))
    log("=" * 70)
    log("总评：" + ("PASS" if allok else "FAIL"), "  REPORT.md", "有" if report["report_md"] else "无")
    json.dump(report, open(os.path.join(ROOT, "grade.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    open(os.path.join(ROOT, "grade.log"), "w", encoding="utf-8").write("\n".join(LOG))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
