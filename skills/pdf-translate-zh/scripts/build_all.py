# -*- coding: utf-8 -*-
"""回归跑：重建所有已写好内容层的文档，汇总关卡结果。

引擎一有改动就跑这个 —— 共享引擎被多份文档复用，
任何一处改动都可能打翻已交付的稿子。

    python build_all.py [--root 项目根目录] [--filter 关键字] [--quiet]

项目根目录缺省取环境变量 PDF_ZH_PROJECTS，再缺省为当前目录；
其下任意深度的 translated/<册>/content/build.py 都会被找到。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse
import glob
import os
import subprocess
import sys
import time

def find_builds(root):
    pat = os.path.join(root, "**", "translated", "*", "content", "build.py")
    return sorted(glob.glob(pat, recursive=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("PDF_ZH_PROJECTS", os.getcwd()))
    ap.add_argument("--filter", default="")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    builds = [b for b in find_builds(a.root) if a.filter.lower() in b.lower()]
    print(f"发现 {len(builds)} 个内容层\n")
    ok, bad = [], []
    t0 = time.time()
    for b in builds:
        stem = os.path.basename(os.path.dirname(os.path.dirname(b)))
        r = subprocess.run([sys.executable, b], capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           cwd=os.path.dirname(b),
                           env=dict(os.environ, PYTHONUTF8="1"))
        tail = [x for x in (r.stdout or "").splitlines()
                if x.strip().startswith(("FAIL", "PASS")) or "FAIL " in x]
        if r.returncode == 0:
            ok.append(stem)
            print(f"  PASS  {stem}")
        else:
            bad.append(stem)
            print(f"  FAIL  {stem}")
            for ln in tail[:8]:
                print("          ", ln.strip())
            if not tail and r.stderr:
                print("          ", r.stderr.strip().splitlines()[-1][:160])
        if not a.quiet and r.returncode != 0:
            pass
    print(f"\n通过 {len(ok)} / {len(builds)}   用时 {time.time()-t0:.0f}s")
    if bad:
        print("未通过：", ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
