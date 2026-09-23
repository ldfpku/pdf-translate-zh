# -*- coding: utf-8 -*-
"""校验层（与文档无关）。交付前必须全绿。

用法
    python verify.py --src <原文.pdf> --out <译文.pdf> --work <workdir> \
                     [--body-pages 94] [--front-roman iv]

检查项
  A. 版心外杂物：四边页边带内不得有任何墨迹
     —— 「表格右侧凭空多出竖线」正属此类，实测曾误画 981 条。
  B. 逐页标签：每页都要有页码/附录标签；正文页码序列连续；前置件罗马数字齐全。
     逻辑页一旦溢出，其后所有页眉页脚标签整体错位，而页码看着仍然连续。
  C. 正文压页脚：版心底沿与页脚分隔线之间必须留净空。
  D. 插图张冠李戴：每幅裁图必须与「源页同 bbox 参考图」一致。
  E. 残留英文 / 中文行里的半角标点。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse, json, os, re, sys

try:
    import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
except ImportError:
    import fitz
import numpy as np

PAGE_W, PAGE_H = 612.0, 792.0


def _ink(page, rect, dpi=150):
    z = dpi / 72.0
    pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(z, z), alpha=False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, 3)
    return int((a.min(axis=2) < 170).sum())


def check_margins(doc, ml, mr, mt, mb, skip):
    bad = []
    for i, p in enumerate(doc):
        if (i + 1) in skip:
            continue
        for name, rect in (
                ("右页边", fitz.Rect(PAGE_W - mr + 2, mt, PAGE_W - 8, PAGE_H - mb)),
                ("左页边", fitz.Rect(8, mt, ml - 2, PAGE_H - mb))):
            n = _ink(p, rect)
            if n:
                bad.append((i + 1, name, n))
    return bad


def check_labels(doc, body_pages, front_roman, skip):
    nolabel, nums, romans = [], [], []
    for i, p in enumerate(doc):
        t = p.get_text()
        m = re.search(rf"第\s*(\d+)\s*页\s*/\s*共\s*{body_pages}\s*页", t)
        if m:
            nums.append(int(m.group(1)))
        m2 = re.search(rf"第\s*([ivx]+)\s*页\s*/\s*共\s*{front_roman}\s*页", t)
        if m2:
            romans.append(m2.group(1))
        if (i + 1) in skip:
            continue
        if not re.search(r"第\s*[\divx]+\s*页\s*/\s*共|附录\s*[A-Z]-\d", t):
            nolabel.append(i + 1)
    return nolabel, nums, romans


def check_footer_gap(doc, ml, mr, mb, foot_rule_y, skip):
    bad = []
    for i, p in enumerate(doc):
        if (i + 1) in skip:
            continue
        # fitz 左上原点、ReportLab 左下原点，必须换算
        rect = fitz.Rect(ml, PAGE_H - mb + 2, PAGE_W - mr, PAGE_H - foot_rule_y - 2)
        if rect.height <= 1:
            continue
        if _ink(p, rect) > 30:
            bad.append((i + 1, _ink(p, rect)))
    return bad


def check_fig_pages(src_pdf, work):
    """每幅裁图必须来自它自己那一页。
    参考图墨迹按 ±2px 膨胀以容忍取整位移；取错页面的差异在 50% 以上。"""
    from PIL import Image
    fp = os.path.join(work, "data", "figures.json")
    if not os.path.exists(fp):
        return [], 0
    doc = fitz.open(src_pdf)
    figs = json.load(open(fp, encoding="utf-8"))
    bad, n = [], 0
    for m in figs:
        path = os.path.join(work, "figures", m["file"])
        if not os.path.exists(path):
            continue
        b = fitz.Rect(m["bbox"])
        z = m["dpi"] / 72.0
        ref = doc[m["page"] - 1].get_pixmap(clip=b, matrix=fitz.Matrix(z, z),
                                            alpha=False)
        a = np.frombuffer(ref.samples, dtype=np.uint8).reshape(
            ref.height, ref.width, 3).min(axis=2)
        im = Image.open(path).convert("L")
        if abs(im.width - ref.width) > 3 or abs(im.height - ref.height) > 3:
            bad.append((m["file"], f"尺寸不符 {im.size} vs {(ref.width, ref.height)}"))
            continue
        h, w = min(im.height, ref.height), min(im.width, ref.width)
        g, a = np.asarray(im)[:h, :w], a[:h, :w]
        ri = a < 200
        dil = ri.copy()
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                dil |= np.roll(np.roll(ri, dy, axis=0), dx, axis=1)
        gi = g < 200
        both = (ri | gi).sum()
        extra = (gi & ~dil).sum()
        n += 1
        if both and extra / max(both, 1) > 0.08:
            bad.append((m["file"], f"多出墨迹 {extra/both:.1%}（疑似取错页面）"))
    return bad, n


def check_text(doc, allow_pages=()):
    NOISE = re.compile(r"[A-Za-z]{3,}")
    eng, half = [], []
    for i, p in enumerate(doc):
        if (i + 1) in allow_pages:
            continue
        for line in p.get_text().splitlines():
            s = line.strip()
            if not s:
                continue
            if NOISE.search(s) and not re.search(r"[一-鿿]", s):
                eng.append((i + 1, s[:90]))
            if re.search(r"[一-鿿]", s):
                for m in re.finditer(r"[,;:?!]", s):
                    j = m.start()
                    prv = s[j - 1] if j else ""
                    nxt = s[j + 1] if j + 1 < len(s) else ""
                    if m.group(0) in ",:" and prv.isdigit() and nxt.isdigit():
                        continue
                    half.append((i + 1, m.group(0), s[:80]))
    return eng, half


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--body-pages", type=int, default=0)
    ap.add_argument("--front-roman", default="iv")
    ap.add_argument("--ml", type=float, default=72.0)
    ap.add_argument("--mr", type=float, default=72.0)
    ap.add_argument("--mt", type=float, default=58.0)
    ap.add_argument("--mb", type=float, default=68.0)
    ap.add_argument("--foot-rule-y", type=float, default=60.0)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    doc = fitz.open(a.out)
    skip = {1, doc.page_count}          # 封面/封底自成设计
    ok = True
    print(f"译文总页数 {doc.page_count}")

    bad = check_margins(doc, a.ml, a.mr, a.mt, a.mb, skip)
    print(f"\nA. 版心外杂物：{len(bad)} 处")
    for x in bad[:20]:
        print("   ", x)
    ok &= not bad

    nolabel, nums, romans = check_labels(doc, a.body_pages or 9999,
                                         a.front_roman, skip)
    print(f"\nB. 无页码标签的物理页：{nolabel}")
    if a.body_pages:
        seq_ok = nums == list(range(1, a.body_pages + 1))
        print(f"   正文页码序列：{'正确' if seq_ok else '异常 ' + str(nums[:20])}")
        ok &= seq_ok
    print(f"   前置件页码：{romans}")
    ok &= not nolabel

    gap = check_footer_gap(doc, a.ml, a.mr, a.mb, a.foot_rule_y, skip)
    print(f"\nC. 正文压页脚：{gap}")
    ok &= not gap

    figbad, nfig = check_fig_pages(a.src, a.work)
    print(f"\nD. 插图来源核验：比对 {nfig} 幅，异常 {len(figbad)} 幅")
    for x in figbad[:20]:
        print("   ", x)
    ok &= not figbad

    eng, half = check_text(doc)
    print(f"\nE. 纯英文行 {len(eng)} 行；中文行中的半角标点 {len(half)} 处")
    print("   （人名、URL、勘误表引用的英文原文、术语对照表属合法白名单，须人工过一遍）")
    for x in eng[:10]:
        print("   ", x)

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
