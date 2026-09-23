# -*- coding: utf-8 -*-
"""全量重建：先跑所有 build*.py，再跑所有 appendix*.py（附录必须后跑 ——
build 只写正文，会把已合并的附录页删掉）。引擎每改一次都要整体重跑。

    python rebuild_all.py [项目根目录]

根目录缺省取环境变量 PDF_ZH_PROJECTS，再缺省为当前目录；其下任意深度的
translated/<册>/content/build*.py 与 appendix*.py 都会被找到。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import glob
import os
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                       else os.environ.get("PDF_ZH_PROJECTS", os.getcwd()))


def run(path):
    d = os.path.dirname(path)
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.basename(path)],
                       cwd=d, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout or "").splitlines()
            if "FAIL" in l or "PASS" in l or "附录" in l or "未命中" in l
            or "合计" in l]
    return r.returncode, tail


def main():
    builds, apxs = [], []
    for pat in ("**/translated/*/content/build*.py",
                "**/translated/_*_build.py"):
        builds += glob.glob(os.path.join(ROOT, pat), recursive=True)
    apxs = glob.glob(os.path.join(ROOT, "**/translated/*/content/appendix*.py"),
                     recursive=True)
    bad = 0
    for p in sorted(builds):
        rc, tail = run(p)
        name = os.path.relpath(p, ROOT)
        flag = "OK " if rc == 0 else "ERR"
        if rc:
            bad += 1
        print(f"{flag} {name}")
        for l in tail:
            if "FAIL" in l or "未命中" in l:
                print("      " + l.strip())
    for p in sorted(apxs):
        rc, tail = run(p)
        if rc:
            bad += 1
            print("ERR " + os.path.relpath(p, ROOT))
            for l in tail:
                print("      " + l.strip())
    print(f"\n构建脚本 {len(builds)}，附录脚本 {len(apxs)}，失败 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
