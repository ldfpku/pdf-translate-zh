# -*- coding: utf-8 -*-
"""端到端冒烟测试（CI 与本机验证共用）：空白 Python 也能跑，依赖由 bootstrap 自动装。

    python3 tests/smoke_test.py            # Windows: py tests\\smoke_test.py

步骤：引擎自检 → 生成虚构样例 PDF → 定级（R/R/P）→ R 级完整示例出稿并过全部闸门 →
P 级图纸示例叠印并过六道关。任何一步失败返回非 0。
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pdf-translate-zh", "scripts")
OUT = os.path.join(ROOT, "tests", "_out")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
_fails = []


def step(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + (("  —— " + detail) if detail else ""), flush=True)
    if not ok:
        _fails.append(name)


def _gh(kind, title, lines):
    """GitHub Actions 注解：未登录也能在运行页上看到，便于排查 CI 失败。"""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    msg = "%0A".join(l.replace("%", "%25").replace("\r", "") for l in lines if l.strip())[:3500]
    print("::%s title=%s::%s" % (kind, title, msg), flush=True)


def report(name, log, tail=3000):
    """失败时打印日志尾部；CI 上另把 FAIL / 报错行做成注解。"""
    print(log[-tail:])
    key = [l for l in log.splitlines()
           if l.lstrip().startswith(("FAIL", "Traceback", "Error", "error"))
           or "Error:" in l or l.startswith("  File ") or l.startswith("         (")]
    _gh("error", "smoke: " + name, (key or log.splitlines())[-25:])


def apx_step(tag, pdf):
    """独立复核：附录 A、B 在译文之后，各自另起一页，任何一页都不同时有正文与附录。"""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    from appendix import A_TITLE, B_TITLE
    norm = lambda t: "".join(t.split())
    if not os.path.exists(pdf):
        step("%s 附录分页" % tag, False, "成品不存在")
        return
    with fitz.open(pdf) as d:
        first = {}
        for i, pg in enumerate(d):
            txt = norm(pg.get_text())
            for k, t in (("A", A_TITLE), ("B", B_TITLE)):
                if norm(t) in txt and k not in first:
                    first[k] = i
        ok = "A" in first and "B" in first and first["A"] > 0 and first["B"] > first["A"]
        detail = "A 起于第 %s 页，B 起于第 %s 页，共 %d 页" % (
            first.get("A", -1) + 1, first.get("B", -1) + 1, d.page_count)
        if ok:
            # 附录 A 首页上，标题之上不得有正文段落（页眉除外：与前一页同位置重复的文字）
            for k in ("A", "B"):
                pg, prev = d[first[k]], d[first[k] - 1]
                run = {(norm(b[4]), round(b[1])) for b in prev.get_text("blocks")}
                blocks = sorted(pg.get_text("blocks"), key=lambda b: b[1])
                t = norm(A_TITLE if k == "A" else B_TITLE)
                hit = next(b for b in blocks if t in norm(b[4]))
                above = [b for b in blocks if b[3] <= hit[1] + 0.5 and norm(b[4])
                         and (norm(b[4]), round(b[1])) not in run]
                if above:
                    ok = False
                    detail += "；附录 %s 首页标题上方有 %d 段正文" % (k, len(above))
    step("%s 附录分页（A、B 各自另起一页）" % tag, ok, detail)


def nav_step(pdf):
    """R 级书签：标题块与附录 A/B 自动进 PDF 大纲，且每条书签落在标题所在页。"""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    if not os.path.exists(pdf):
        step("R 级书签", False, "成品不存在")
        return
    with fitz.open(pdf) as d:
        toc = d.get_toc()
        bad = [t for lv, t, p in toc if "".join(t.split())[:6] not in "".join(d[p - 1].get_text().split())]
    titles = [t for _, t, _ in toc]
    ok = len(toc) >= 5 and any(t.startswith("附录 A") for t in titles) and any(t.startswith("附录 B") for t in titles) \
        and not bad
    step("R 级书签（标题 + 附录自动进大纲、落点正确）", ok, "%d 条%s" % (len(toc), "；落点不符 %s" % bad[:3] if bad else ""))


def run(args, cwd=None):
    t = time.time()
    r = subprocess.run([sys.executable, *args], cwd=cwd, env=ENV, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or ""), time.time() - t


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("pdf-translate-zh 冒烟测试  Python %s  %s" % (sys.version.split()[0], sys.platform))
    bootstrap.ensure()
    ENV["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)

    rc, log, dt = run([os.path.join(SCRIPTS, "selftest.py")])
    step("引擎自检 selftest.py", rc == 0, "%.0fs" % dt)
    if rc:
        report("selftest", log, 2000)
    try:
        import fontkit
        src = ["%s: %s" % (r, fontkit.find(r, reportlab=True, required=False)) for r in ("zh", "zh-bold")]
        src += ["来源: %s" % fontkit._SOURCE.get(("zh", True), "")]
        print("  字体  " + "  |  ".join(src))
        _gh("notice", "smoke: fonts", src)
    except Exception as e:
        print("  字体探测失败：%s" % e)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gen_testdocs
    gen_testdocs.main(OUT)
    step("生成样例 PDF", all(os.path.exists(os.path.join(OUT, f)) for f in
                          ("mud_motor_manual.pdf", "mud_motor_manual_long.pdf",
                           "stator_housing_drawing.pdf")))

    import route
    want = {"mud_motor_manual.pdf": "R", "mud_motor_manual_long.pdf": "R",
            "stator_housing_drawing.pdf": "P"}
    for f, lv in want.items():
        got = route.classify(os.path.join(OUT, f))["level"]
        step("定级 %s = %s" % (f, lv), got == lv, "实得 %s" % got)

    # ---- R 级：完整示例（examples/mud-motor-manual）
    rc, log, dt = run([os.path.join(SCRIPTS, "translate_pdf.py"), "mud_motor_manual.pdf"], cwd=OUT)
    work = os.path.join(OUT, "translated", "mud_motor_manual")
    step("R 级提取 translate_pdf.py", rc == 0 and os.path.exists(os.path.join(work, "data", "figures.json")),
         "%.0fs" % dt)
    if rc:
        report("R extract", log, 2000)
    for f in ("build.py", "content.py", "terms.py"):
        shutil.copy(os.path.join(ROOT, "examples", "mud-motor-manual", f), os.path.join(work, "content", f))
    rc, log, dt = run([os.path.join(work, "content", "build.py")])
    step("R 级出稿 + 全部闸门", rc == 0 and "PASS" in log, "%.0fs" % dt)
    if rc:
        report("R build", log)
    apx_step("R 级", os.path.join(OUT, "translated", "mud_motor_manual_中文_v01.pdf"))
    nav_step(os.path.join(OUT, "translated", "mud_motor_manual_中文_v01.pdf"))

    # ---- P 级：图纸叠印（examples/stator-drawing）
    rc, log, dt = run([os.path.join(SCRIPTS, "translate_pdf.py"), "stator_housing_drawing.pdf"], cwd=OUT)
    work = os.path.join(OUT, "translated", "stator_housing_drawing")
    step("P 级骨架 translate_pdf.py", rc == 0, "%.0fs" % dt)
    for f in ("build.py", "stator_housing_drawing_dict.py", "terms.py"):
        shutil.copy(os.path.join(ROOT, "examples", "stator-drawing", f), os.path.join(work, "content", f))
    rc, log, dt = run([os.path.join(work, "content", "build.py")])
    step("P 级叠印 + 六道关", rc == 0 and "PASS" in log, "%.0fs" % dt)
    if rc:
        report("P build", log)
    apx_step("P 级", os.path.join(OUT, "translated", "stator_housing_drawing_中文_v01.pdf"))

    print("\n结论：" + ("全部通过" if not _fails else "失败 %d 项：%s" % (len(_fails), "、".join(_fails))))
    print("产物：" + OUT)
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
