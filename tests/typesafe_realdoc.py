# -*- coding: utf-8 -*-
"""实文档页面级别对照：按一份「页清单 + 人工真值」跑 TypeSafe Choice，与启发式比。没有密钥时跳过并说明。

    py tests\\typesafe_realdoc.py <plan.json> [--out result.json] [--no-examples] [--limit N]

plan.json 是列表，每项至少 {"pdf": 路径, "page": 1 基页号, "heur": 启发式级别, "truth": 人工真值}（R / P / S）。
两种问法各跑一遍：plain（只有文字描述）与 examples（criteria 另带两张示例页图：仓库 SWI 第 2 页作 R、TDT 第 1 页作 P），
分别记准确率、token/页、秒/页。真值与清单由人工目检缩览拼贴给出，脚本不生成。
文档内容会以页面图形式发到 api.typesafe.ai —— 客户资料先确认合规。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pdf-translate-zh", "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402
bootstrap.ensure(quiet=True)
import tsjudge  # noqa: E402

SWI = os.path.join(ROOT, "docs", "showcase", "SWI-650-SS_Assembly_en.pdf")
TDT = os.path.join(ROOT, "docs", "showcase", "TDT-650-0100_Assembly_en.pdf")


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(argv) < 2:
        print(__doc__)
        return 2
    if not tsjudge.enabled():
        print("SKIP：" + tsjudge.status_line() + "\n  " + tsjudge.REMINDER)
        return 0
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    plan = json.load(open(argv[1], encoding="utf-8"))
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.splitext(argv[1])[0] + "_result.json"
    modes = ["plain"] if "--no-examples" in argv else ["plain", "examples"]
    if "--limit" in argv:
        plan = plan[:int(argv[argv.index("--limit") + 1])]
    examples = {"R": [tsjudge.page_png(fitz.open(SWI)[1])], "P": [tsjudge.page_png(fitz.open(TDT)[0])]}
    docs, rows, t0 = {}, [], time.time()
    for i, it in enumerate(plan):
        d = docs.setdefault(it["pdf"], fitz.open(it["pdf"]))
        png = tsjudge.page_png(d[it["page"] - 1])
        row = dict(it)
        for m in modes:
            try:
                r = tsjudge.page_level(png, examples if m == "examples" else None)
                lv = r["level"] if r["level"] != "blank" else "R"
                row[m] = dict(level=lv, raw=r["level"], conf=round(r["confidence"], 3), tokens=r["input_tokens"],
                              seconds=r["seconds"], probs={k: round(v, 3) for k, v in r["probabilities"].items()})
            except Exception as e:
                row[m] = dict(error="%s: %s" % (type(e).__name__, e))
        rows.append(row)
        line = "  #%-3d %-28s p%-4d 真值 %s 启发式 %s" % (i, os.path.basename(it["pdf"])[:28], it["page"], it["truth"], it["heur"])
        for m in modes:
            x = row[m]
            line += "  %s %s" % (m[:2], (x["raw"] + "/%.2f" % x["conf"]) if "level" in x else "ERR")
        print(line + ("" if all(row[m].get("level") == it["truth"] for m in modes) else "  ←"), flush=True)
        json.dump(dict(model=tsjudge.MODEL, docs_date=tsjudge.DOCS_DATE, modes=modes, rows=rows),
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = len(rows)
    print("\n%d 页，总耗时 %.0f s" % (n, time.time() - t0))
    print("  启发式准确率 %.0f%%（%d/%d）" % (100.0 * sum(1 for r in rows if r["heur"] == r["truth"]) / n,
                                      sum(1 for r in rows if r["heur"] == r["truth"]), n))
    for m in modes:
        ok = [r for r in rows if "level" in r[m]]
        acc = sum(1 for r in ok if r[m]["level"] == r["truth"])
        print("  TypeSafe %-8s 准确率 %.0f%%（%d/%d，出错 %d）  %.0f tok/页  %.1f s/页" % (
            m, 100.0 * acc / max(1, len(ok)), acc, len(ok), n - len(ok),
            sum(r[m]["tokens"] for r in ok) / max(1, len(ok)), sum(r[m]["seconds"] for r in ok) / max(1, len(ok))))
        from collections import Counter
        print("    错误类型（真值→判）：", dict(Counter("%s→%s" % (r["truth"], r[m]["level"]) for r in ok if r[m]["level"] != r["truth"])))
    print("结果写入", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
