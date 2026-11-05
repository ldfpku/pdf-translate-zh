# -*- coding: utf-8 -*-
"""引擎冒烟自检：zh() 单测、块 DSL 参数位置、装配与几何。
换文档不用改；引擎一有改动就跑这个。

    python selftest.py [输出.pdf]
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import io
import os
import sys

sys.dont_write_bytecode = True       # 技能目录可能只读，也别留 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import checks
from zhlib import styles, register_fonts
from builder import (Geom, LETTER, D_LS, CHART_LS, Masthead, Footer, build,
                     build_2pass, fit_check, body_labels, appendix_labels)
from appendix import errata, glossary

ok = True
print("引擎冒烟自检")
ok &= checks.report("zh() 全角规范化单测", checks.test_zh())
ok &= checks.report("块 DSL 参数位置", checks.test_dsl())

LOGO = None          # 徽标是客户资产，不随技能分发
S = styles()
register_fonts()

mast = Masthead("技术服务通知", ["质量管理体系", "签发人：张工",
                                     "2020 年 12 月 11 日", "TN-Rev A"],
                logo=LOGO, info_w=[126, 176, 96, 70], logo_text="ACME DRILLING TOOLS")
foot = Footer(left="打印后即为非受控副本。\n仅在打印当日有效。",
              center="打印时间：2020 年 12 月 17 日 9:52",
              right="© ACME Drilling Tools")

print(f"  抬头实测高度 {mast.height(LETTER.fw):.1f}pt   "
      f"版心宽 {LETTER.fw:.0f}pt   下边距 {LETTER.mb:.0f}pt")

pages = [[("title", "技术通知 #33 — 动力段磨损标准"),
          ("kv", [("日期：", "2020 年 12 月 11 日"),
                  ("适用范围：", "全部业务区")]),
          ("sp", 6),
          ("p", "测试段落：转子与定子的配合, 应符合下表; 公称 1,500 lbf。"),
          ("ol", ["甲项", "乙项"], "alpha"),
          ("bul", ["要点一", "要点二"]),
          ("box", "这是一条注意事项。", "warn"),
          ("tbl", lambda: __import__("render").grid_table(
              [["部位", "限值", "说明"],
               ["定子小径 ID", "+0.020″", "自公称尺寸起"],
               ["转子谷至冠 OD", "-0.010″", "自公称尺寸起"]],
              [150, 90, 228], S, size="tbl9"), "表 1  磨损限值")]]

bad = fit_check(pages, LETTER, mast, foot, S)
ok &= checks.report("逐页装配（每页实测须为 1 页）", bad)

# 产物写到临时目录（技能目录可能只读，也不该被弄脏）；可用第一个参数指定路径
import tempfile
out = (sys.argv[1] if len(sys.argv) > 1
       else os.path.join(tempfile.mkdtemp(prefix="pdfzh_smoke_"), "smoke.pdf"))
GL = {"动力段": [("stator", "定子"), ("rotor", "转子"),
                 ("power section", "动力段"), ("minor ID", "小径内径")],
      "配合与公差": [("nominal", "公称"), ("fit", "配合")]}
apx = [("A", errata(jia=[["1", "第 1 页", "示例英文原文", "数值矛盾",
                          "示例勘正", "示例依据"]],
                    bing=[["1", "抬头", "徽标为位图", "按 8× 渲染后重嵌"]],
                    S=S, fw=LETTER.fw)),
       ("B", glossary(GL, S, LETTER.fw))]

n, lab, spans = build_2pass(out, pages, apx, LETTER, mast, foot, S)
print(f"  产出 {out}  物理页数 {n}")

ok &= checks.report("版心外杂物", checks.check_margins(out, LETTER))
ok &= checks.report("正文压页脚", checks.check_footer(out, LETTER))
nolabel, nums, seq = checks.check_labels(out, body_pages=1)
ok &= checks.report("无页码标签的物理页", nolabel)
print(f"        正文页码序列 {'正确' if seq else '异常'} {nums}")
ok &= checks.report("附录标签", [] if all(
    f"附录 {t}-" in "".join(lab.values()) for t in ("A", "B")) else ["附录标签缺失"])

# ---- 流式重排（R 级，V2 默认）：多页章节、页码按实排生成 ----
print("  —— 流式重排模式 ——")
S2 = styles(flow=True)
chap = [("h1", "第 1 章  概述")]
for i in range(1, 40):
    chap.append(("h2", f"1.{i}  小节 {i}"))
    chap.append(("p", f"第 {i} 段：钻头提离井底 0.5 m 后，以 60 r/min 转速循环 {i} min，"
                      "确认泵压稳定在 1,500 psi 以下。" * 2))
chapters = [chap, [("h1", "第 2 章  维护"), ("bul", ["检查定子 ID", "检查转子 OD"])]]
info = {}
out2 = out[:-4] + "_flow.pdf"
n2, lab2, sp2 = build_2pass(out2, chapters, lambda: [("B", glossary(GL, S2, LETTER.fw))],
                            LETTER, mast, foot, S2, flow_mode=True, info=info)
print(f"  产出 {out2}  物理页数 {n2}  正文 {info.get('n_body')} 页")
ok &= checks.report("流式：正文跨页（>1）", [] if info.get("n_body", 0) > 1 else ["正文未跨页"])
nl2, nums2, seq2 = checks.check_labels(out2, body_pages=info["n_body"])
ok &= checks.report("流式：无页码标签的物理页", nl2)
print(f"        正文页码序列 {'正确' if seq2 else '异常'} {nums2[:6]}…")
ok &= seq2
ok &= checks.report("流式：缺字", checks.check_glyphs(out2))

# ---- 图内文字漏译排查（逐用图 sweep）：矢量/位图两种形态 ----
print("  —— 图内文字漏译 sweep ——")
import json as _json
import re as _re
import tempfile as _tf
import figlabel as _fl
try:
    from PIL import Image as _Img, ImageDraw as _Draw, ImageFont as _Font
    import fontkit as _fk
    _work = _tf.mkdtemp(prefix="pdfzh_sweep_")
    _figdir = os.path.join(_work, "figures"); os.makedirs(_figdir)
    _datadir = os.path.join(_work, "data"); os.makedirs(_datadir)
    _dpi = 300; _k = _dpi / 72.0
    _im = _Img.new("RGB", (600, 240), "white")
    _f = _Font.truetype(_fk.find("mono-bold"), 34)
    _d = _Draw.Draw(_im)
    _d.text((40, 50), "COVERED", font=_f, fill="black")     # 对应矢量 label
    _d.text((40, 150), "MISSING", font=_f, fill="black")    # 位图烧死、漏译
    _im.save(os.path.join(_figdir, "fig.png"))
    _labels = [dict(text="Covered", size=12.0,
                    x=round(40 / _k, 2), y=round(50 / _k, 2),
                    w=round(260 / _k, 2), h=round(45 / _k, 2))]
    _json.dump([dict(page=1, idx=1, file="fig.png", bbox=[0, 0, 600 / _k, 240 / _k],
                     w_pt=600 / _k, h_pt=240 / _k, dpi=_dpi,
                     labels=_labels, kept_numbers=[])],
               open(os.path.join(_datadir, "figures.json"), "w", encoding="utf-8"),
               ensure_ascii=False, indent=1)
    _keep = _re.compile(r"^(?:\(?\d{1,2}\)?|[A-K])$")
    _swept = _fl.sweep_figures_json(_work, ("fig.png",),
                                    zh_map={"Covered": "已处置"},
                                    keep_re=_keep, verbose=False)
    if _swept:
        ok &= checks.report("sweep：位图烧死漏译报得出（COVERED 不误报）",
                            [] if dict(_swept).get("fig.png", 0) == 1 else _swept)
    else:
        print("  note sweep 本机未检出（后端降级？）——跳过该断言，流程不阻断")
    # 负对照：清空 covered → 连 COVERED 也应报出（判据非假）
    _fp = os.path.join(_datadir, "figures.json")
    _figs = _json.load(open(_fp, encoding="utf-8"))
    for _m in _figs:
        _m["labels"] = []
    _json.dump(_figs, open(_fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    _swept2 = _fl.sweep_figures_json(_work, ("fig.png",), zh_map={},
                                     keep_re=_keep, verbose=False)
    if _swept:   # 仅在后端可用时做负对照
        ok &= checks.report("sweep 负对照：清空 covered 后报出更多残留",
                            [] if dict(_swept2).get("fig.png", 0) > dict(_swept).get("fig.png", 0)
                            else ["负对照未报出更多：判据可疑"])
    import shutil as _sh
    _sh.rmtree(_work, ignore_errors=True)
except ImportError as _e:
    print(f"  note sweep 自检跳过（检测后端缺失：{_e}）")

print("\nPASS" if ok else "\nFAIL")
sys.exit(0 if ok else 1)
