# -*- coding: utf-8 -*-
"""列出若干工作区里「零件描述」的唯一串（SKILL §4 的 07_uniq_desc）。

零件表往往上百条描述，但高度模式化。先统计唯一串，再写
「正则规则 + 精确字典」的 desc_zh()，并用 test_terms 断言未命中 = 0，
以此保证同物同名、杜绝「开启套／活化套／激活套」混用。

    python uniq_desc.py <workdir> [<workdir> ...] [--col 2]
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse
import json
import os
import re
import sys
from collections import Counter


def norm(s):
    """JSON/PDF 里的名称常含前导与多重空格，查字典必然 miss（避坑 ⑫）。"""
    return " ".join(str(s or "").split())


PN = re.compile(r"^[\d\-]{6,}[A-Z]?$|^\d{8}$")   # 零件号形态


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work", nargs="+")
    ap.add_argument("--min-cols", type=int, default=3)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cnt = Counter()
    where = {}
    for w in a.work:
        fp = os.path.join(w, "data", "tables_raw.json")
        if not os.path.exists(fp):
            print(f"[跳过] 无 tables_raw.json: {w}")
            continue
        tabs = json.load(open(fp, encoding="utf-8"))
        stem = os.path.basename(w)
        for t in tabs:
            rows = t["data"]
            if not rows or t["cols"] < a.min_cols:
                continue
            hdr = [norm(c).upper() for c in rows[0]]
            # 只认真正的明细表：表头须含 PART NAME
            if not any("PART NAME" in h for h in hdr):
                continue
            ci = [i for i, h in enumerate(hdr) if "PART NAME" in h][0]
            for r in rows[1:]:
                if ci >= len(r):
                    continue
                d = norm(r[ci])
                if not d or PN.match(d):
                    continue
                cnt[d] += 1
                where.setdefault(d, set()).add(f"{stem[:22]} p{t['page']}")

    print(f"唯一零件描述 {len(cnt)} 条（按出现次数降序）\n")
    for d, n in cnt.most_common():
        print(f"({n:2d})  {d}")
    print("\n---- 便于粘贴进 terms.py 的骨架 ----")
    for d, _ in sorted(cnt.items()):
        print(f'    "{d}": "",')


if __name__ == "__main__":
    main()
