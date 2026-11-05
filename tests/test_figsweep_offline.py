# -*- coding: utf-8 -*-
"""合成离线回归测试：R 级逐用图漏译扫描 figlabel.sweep_figures_json。

验证点：
  · 已 cover 的文字块不报、未 cover 的文字块报出（正判）；
  · 负对照：covered 清空后，连已 cover 的文字块也被报出（判据非假）；
  · 只扫 used_figs 引用到的图，未引用图不参与；
  · 残留描红核查图写到 qa/sweep_<file>.png。
"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pdf-translate-zh", "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402
bootstrap.ensure(quiet=True)
import figlabel  # noqa: E402
import fontkit  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FAILS = []


def step(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + ((" — " + detail) if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


def _font(size):
    return ImageFont.truetype(fontkit.find("mono-bold"), size)


def _build_work(tmp):
    """造一个最小工作区：一张 figures/fig.png，图上两处英文——
    一处对应 figures.json 的矢量 label（= 已处置 covered），
    一处不在 figures.json 里（= 位图烧死的漏译）。另造一张未被引用的图。"""
    figdir = os.path.join(tmp, "figures")
    datadir = os.path.join(tmp, "data")
    os.makedirs(figdir)
    os.makedirs(datadir)

    # 300 dpi、宽 300pt → 像素宽 1250。这里直接按像素造图，dpi 记 300，
    # label 的 pt 坐标 = 像素坐标 / (dpi/72)。
    dpi = 300
    k = dpi / 72.0
    W, H = 600, 240
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    f = _font(34)
    # 已处置块（对应矢量 label）：像素框约 (40,50)-(300,95)
    d.text((40, 50), "COVERED", font=f, fill="black")
    # 未处置块（位图烧死，不在 figures.json）：像素框约 (40,150)-(300,195)
    d.text((40, 150), "MISSING", font=f, fill="black")
    im.save(os.path.join(figdir, "fig.png"))

    # 未被引用的图：整幅都是英文，但不应被扫（used_figs 不含它）
    im2 = Image.new("RGB", (W, H), "white")
    ImageDraw.Draw(im2).text((40, 90), "UNUSED", font=f, fill="black")
    im2.save(os.path.join(figdir, "other.png"))

    # figures.json：fig.png 有一条矢量 label，坐标对应「COVERED」块（pt）
    labels = [dict(text="Covered", size=12.0,
                   x=round(40 / k, 2), y=round(50 / k, 2),
                   w=round(260 / k, 2), h=round(45 / k, 2))]
    figs = [
        dict(page=1, idx=1, file="fig.png", bbox=[0, 0, W / k, H / k],
             w_pt=W / k, h_pt=H / k, dpi=dpi, labels=labels, kept_numbers=[]),
        dict(page=2, idx=1, file="other.png", bbox=[0, 0, W / k, H / k],
             w_pt=W / k, h_pt=H / k, dpi=dpi, labels=[], kept_numbers=[]),
    ]
    with open(os.path.join(datadir, "figures.json"), "w", encoding="utf-8") as fh:
        json.dump(figs, fh, ensure_ascii=False, indent=1)
    return tmp


def t_sweep():
    with tempfile.TemporaryDirectory(prefix="figsweep_") as tmp:
        _build_work(tmp)
        keep = re.compile(r"^(?:\(?\d{1,2}\)?|[A-K])$")

        # 正判：只扫被引用的 fig.png；COVERED 块被 figures.json label 覆盖、
        # MISSING 块无覆盖 → 应恰好报 fig.png 且残留 ≥1。
        res = figlabel.sweep_figures_json(
            tmp, used_figs=("fig.png",), zh_map={"Covered": "已处置"},
            keep_re=keep, verbose=False)
        files = [f for f, _ in res]
        step("正判：只报被引用图 fig.png", files == ["fig.png"], "res=%r" % res)
        n_miss = dict(res).get("fig.png", 0)
        step("正判：报出未处置块（MISSING）", n_miss >= 1, "残留=%d" % n_miss)
        step("未引用图 other.png 不参与扫描", "other.png" not in files)
        qa = os.path.join(tmp, "qa", "sweep_fig.png")
        step("残留核查图写到 qa/sweep_fig.png", os.path.exists(qa))

        # 负对照：把 figures.json 的 labels 清空（covered 为空）→ 连 COVERED
        # 块也应被报出，残留数应 > 正判（证明判据不是对谁都放行的假判据）。
        fp = os.path.join(tmp, "data", "figures.json")
        figs = json.load(open(fp, encoding="utf-8"))
        for m in figs:
            m["labels"] = []
        json.dump(figs, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        res2 = figlabel.sweep_figures_json(
            tmp, used_figs=("fig.png",), zh_map={}, keep_re=keep, verbose=False)
        n_all = dict(res2).get("fig.png", 0)
        step("负对照：清空 covered 后报出更多残留",
             n_all > n_miss, "清空后=%d 正判=%d" % (n_all, n_miss))

        # used_figs 为空 → 跳过、返回空
        res3 = figlabel.sweep_figures_json(tmp, used_figs=(), verbose=False)
        step("used_figs 为空：跳过返回空", res3 == [])


def main():
    print("figlabel.sweep_figures_json 离线自检")
    t_sweep()
    print("\n结论：" + ("全部通过" if not FAILS else "失败：" + "、".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
