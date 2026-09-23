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
        print(log[-2000:])

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
        print(log[-2000:])
    for f in ("build.py", "content.py", "terms.py"):
        shutil.copy(os.path.join(ROOT, "examples", "mud-motor-manual", f), os.path.join(work, "content", f))
    rc, log, dt = run([os.path.join(work, "content", "build.py")])
    step("R 级出稿 + 全部闸门", rc == 0 and "PASS" in log, "%.0fs" % dt)
    if rc:
        print(log[-3000:])

    # ---- P 级：图纸叠印（examples/stator-drawing）
    rc, log, dt = run([os.path.join(SCRIPTS, "translate_pdf.py"), "stator_housing_drawing.pdf"], cwd=OUT)
    work = os.path.join(OUT, "translated", "stator_housing_drawing")
    step("P 级骨架 translate_pdf.py", rc == 0, "%.0fs" % dt)
    for f in ("build.py", "stator_housing_drawing_dict.py"):
        shutil.copy(os.path.join(ROOT, "examples", "stator-drawing", f), os.path.join(work, "content", f))
    rc, log, dt = run([os.path.join(work, "content", "build.py")])
    step("P 级叠印 + 六道关", rc == 0 and "PASS" in log, "%.0fs" % dt)
    if rc:
        print(log[-3000:])

    print("\n结论：" + ("全部通过" if not _fails else "失败 %d 项：%s" % (len(_fails), "、".join(_fails))))
    print("产物：" + OUT)
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
