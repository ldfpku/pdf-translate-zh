# -*- coding: utf-8 -*-
"""全库跑 `toccheck` 八道判据。每册的封面页／目录页登记在一个**登记表模块**里。

    python tocsweep.py <项目根目录> --pages 我的登记表.py

登记表模块提供 PAGES（必需）、WL（白名单正则）、WAIVE（明示豁免），
格式见 examples/toc_pages_example.py。不给 --pages 时对每一册自动登记
「封面 = 第 1 页、目录 = 无」，只跑封面与残留英文两类判据。

页号是**成品**上的物理页（1 基）。登记为 `()` 表示该册没有这一部分 ——
不是所有文档都有封面和目录，短文档大多两样都没有，不要硬造。

`toc` 里**只登记真目录**。普查脚本会把零件表页误判成目录（行尾都是数字），
实测 手册 B p6 / 手册 C p6,p12 / 图纸族 J 全是这一类，一律不登记。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # noqa: E402
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz
import sweep                                                  # noqa: E402
import toccheck                                               # noqa: E402

def _waived(base, key, text):
    for k, frag, _why in WAIVE.get(base, ()):
        if key.startswith(k) and frag in str(text):
            return True
    return False


PAGES, WL, WAIVE = {}, r"Page|of", {}


def load_registry(path):
    """从登记表模块读 PAGES / WL / WAIVE。"""
    global PAGES, WL, WAIVE
    import importlib.util
    spec = importlib.util.spec_from_file_location("toc_pages", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    PAGES = getattr(m, "PAGES", {})
    WL = getattr(m, "WL", WL)
    WAIVE = getattr(m, "WAIVE", {})


def main(root=".", auto=False):
    n = ok = 0
    nw = 0
    for src, out in sweep.pairs(root):
        base = os.path.basename(src)[:-4]
        hit = next((k for k in PAGES if base.startswith(k[:34])), None)
        if not hit:
            if not auto:
                continue
            hit = base
            cfg = ((1,), ())
        else:
            cfg = PAGES[hit]
        cover, toc = cfg[0], cfg[1]
        rebuilt = len(cfg) > 2 and cfg[2]
        n += 1
        d = fitz.open(out)
        res = toccheck.check(d, toc_pages=toc, cover_pages=cover, src=src,
                             whitelist=WL, verbose=False, rebuilt=rebuilt)
        d.close()
        res = {k: [x for x in v if not _waived(hit, k, x)]
               for k, v in res.items()}
        w = sum(1 for k, frag, _ in WAIVE.get(hit, ()))
        nw += w
        tot = sum(len(v) for v in res.values())
        tag = f"（豁免 {w}）" if w else ""
        if tot:
            print(f"  FAIL {base[:42]:44s} {tot} 处{tag}")
            for k in sorted(res):
                for x in res[k][:4]:
                    print(f"        {k}  {x}")
        else:
            ok += 1
            print(f"  OK   {base[:42]:44s} 八关全绿{tag}")
    print(f"\n{ok}/{n} 通过" + (f"（另有 {nw} 条明示豁免，理由见 WAIVE）"
                                if nw else ""))
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    reg = None
    if "--pages" in args:
        k = args.index("--pages")
        reg = args[k + 1]
        del args[k:k + 2]
    if reg:
        load_registry(reg)
    sys.exit(main(args[0] if args else ".", auto=reg is None))
