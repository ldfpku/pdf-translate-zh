# -*- coding: utf-8 -*-
"""全量成品体检：保留项失踪 / 中文重叠 / 缺字。

`build.py` 的五道关只看「写进去了什么」，看不见「被抹掉了什么」。
本脚本补上第六视角，并对**全部成品**一次跑完 —— 引擎每改一次都要跑。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # noqa: E402
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz
import checks                                                 # noqa: E402

KEEP = re.compile(r"^[\s\d.,;:/()\[\]+\-–—°'\"×x#%&*…]*$"
                  r"|^(?=[A-Z0-9\-]*\d)[A-Z0-9\-]{2,}$|^\d+/\d+$")


def kept(t):
    return bool(KEEP.match(t)) or not re.search(r"[A-Za-z]{2,}", t)


def lost_tokens(src, out):
    """跨字号块里**应原样保留**的记号是否还在成品上。"""
    a, o = fitz.open(src), fitz.open(out)
    bad = []
    for pno, pg in enumerate(a, 1):
        if pno > len(o):
            break
        # 源上一行里被并在一起的各列（`2-7/8"- 12"12010010090`）在成品上
        # 是分开的单元格，按空白分词比对必然误报 —— 两边都**去掉全部空白**再比。
        have = "".join(o[pno - 1].get_text().split())
        for b in pg.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            rows = []
            for ln in b["lines"]:
                sp = [s for s in ln["spans"] if s["text"].strip()]
                if not sp:
                    continue
                zs = [s["size"] for s in sp]
                rows.append((" ".join("".join(s["text"] for s in sp).split()),
                             max(set(zs), key=zs.count)))
            if len(rows) < 2:
                continue
            zz = [z for _t, z in rows]
            if max(zz) / min(zz) < 1.4:
                continue
            lo = min(zz)
            for t, z in rows:
                tk = "".join(t.split())
                if z / lo < 1.4 and kept(t) and len(tk) >= 3 and tk not in have:
                    bad.append((pno, t[:28]))
    a.close()
    o.close()
    return bad


def pairs(root="."):
    """root 下任意深度的 <dir>/X.pdf ↔ <dir>/translated/X_中文_vNN.pdf（取最新版）。"""
    for src in sorted(glob.glob(os.path.join(root, "**", "*.pdf"), recursive=True)):
        if os.sep + "translated" + os.sep in src:
            continue
        base = os.path.basename(src)[:-4]
        outs = sorted(glob.glob(os.path.join(os.path.dirname(src), "translated",
                                             glob.escape(base) + "_中文_v*.pdf")))
        if outs:
            yield src, outs[-1]


def main(root="."):
    n = ok = 0
    for src, out in pairs(root):
        n += 1
        tag = []
        lt = lost_tokens(src, out)
        if lt:
            tag.append(f"保留项失踪 {len(lt)} {lt[:3]}")
        ov = checks.check_overlap(out)
        if ov:
            tag.append(f"重叠 {len(ov)} {[(r[0], r[1][:12], r[2][:12]) for r in ov[:3]]}")
        gl = checks.check_glyphs(out)
        if gl:
            tag.append(f"缺字 {len(gl)}")
        if tag:
            print(f"  FAIL {os.path.basename(out)[:44]:44s} " + " | ".join(tag))
        else:
            ok += 1
    print(f"\n{ok}/{n} 通过")
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
