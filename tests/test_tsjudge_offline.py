# -*- coding: utf-8 -*-
"""tsjudge 离线自检（不联网、不需要密钥）：图像预处理的限制与坐标换算、占位模式下各入口的写盘格式、
以及**默认路径不变**（开关关闭时 route / figpipe 的产物与打开前逐字节一致）。

    py tests\\test_tsjudge_offline.py
"""
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pdf-translate-zh", "scripts")
OUT = os.path.join(ROOT, "tests", "_out", "tsjudge_offline")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402
bootstrap.ensure(quiet=True)
from PIL import Image  # noqa: E402
import tsjudge  # noqa: E402

_fails = []


def step(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + (("  —— " + detail) if detail else ""), flush=True)
    if not ok:
        _fails.append(name)


def t_prepare():
    for w, h in ((40, 40), (1568, 90), (4000, 3000), (300, 2000), (1568, 1568), (281, 279)):
        im = Image.new("RGB", (w, h), (200, 200, 200))
        p = tsjudge.prepare_image(im)
        ok = (280 <= p.w <= 1568 and 280 <= p.h <= 1568 and 78400 <= p.w * p.h <= 2458624)
        # 任取源图上一个矩形，经 from_src → to_src 回到原位（±1 px）
        rect = (w * 0.1, h * 0.2, w * 0.6, h * 0.7)
        back = p.to_src(p.from_src(rect))
        ok &= all(abs(a - b) <= 1.0 for a, b in zip(rect, back))
        step("prepare_image %dx%d → %dx%d scale %.3f 回算 ±1px" % (w, h, p.w, p.h, p.scale), ok)
    # EXIF 方向：竖拍照片标记为 6（顺时针 90°）应被转正为竖图
    im = Image.new("RGB", (600, 400), (10, 10, 10))
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6
    im.save(buf, "JPEG", exif=exif.tobytes())
    p = tsjudge.prepare_image(buf.getvalue())
    step("EXIF 方向 6 转正（600x400 → 竖图）", p.src_w == 400 and p.src_h == 600, "%dx%d" % (p.src_w, p.src_h))
    # 占位 Box：中央一半 → 源图像素
    im = Image.new("RGB", (1000, 500), (255, 255, 255))
    p = tsjudge.prepare_image(im)
    box = p.to_src({"top": 0.25, "bottom": 0.75, "left": 0.25, "right": 0.75})
    step("Box 比例 → 源图像素", all(abs(a - b) <= 1 for a, b in zip(box, (250, 125, 750, 375))), str(box))
    # 请求体上限
    try:
        tsjudge.build_request({"a": "x"}, {"q": {"type": "noul", "instructions": "x"}},
                              {"x": {"type": "image", "format": "png", "data_base64": "A" * (33 * 1024 * 1024)}})
        step("请求体 > 32 MiB 被拒", False)
    except tsjudge.TypeSafeError:
        step("请求体 > 32 MiB 被拒", True)


def t_mock_domain():
    os.environ["PDF_ZH_TYPESAFE"] = "1"
    os.environ["PDF_ZH_TYPESAFE_MOCK"] = "1"
    os.environ.pop("TYPESAFE_API_KEY", None)
    step("占位模式下 enabled()", tsjudge.enabled())
    im = Image.new("RGB", (900, 600), (255, 255, 255))
    r = tsjudge.page_level(im)
    step("page_level 占位", r["level"] in tsjudge.LEVEL_TEXT and r["input_tokens"] == 0, r["level"])
    h = tsjudge.figure_hints(im, [(100, 100, 160, 130), (300, 300, 340, 340)])
    step("figure_hints 占位：逐框两问", set(h["boxes"]) == {0, 1} and {"text", "bubble"} <= set(h["boxes"][0]))
    # locate：占位 Box 取裁片中央一半 → 换算回源图应落在 region 内部
    reg = (200, 100, 600, 400)
    loc = tsjudge.locate(im, reg, "x {img}", "y {img}", min_conf=0.0, yes=0.0)
    b = loc["box"]
    inside = b and reg[0] <= b[0] < b[2] <= reg[2] and reg[1] <= b[1] < b[3] <= reg[3]
    step("locate 占位：裁片坐标换算回源图并落在区域内", bool(inside), str(b))
    br = tsjudge.bubble_ring(im, (300, 200, 330, 220))
    step("bubble_ring 占位返回区域与框", "region" in br and "box" in br)
    # bubbles.ring_by_bbox：画一个真环，给外框，几何应接近
    import numpy as np
    from PIL import ImageDraw
    import bubbles
    im2 = Image.new("RGB", (400, 400), (255, 255, 255))
    ImageDraw.Draw(im2).ellipse([150, 160, 250, 240], outline=(0, 0, 0), width=5)
    g = np.array(im2.convert("L"))
    geo = bubbles.ring_by_bbox(g, (150, 160, 250, 240))
    ok = geo is not None and abs(geo["cx"] - 200) <= 1 and abs(geo["cy"] - 200) <= 1 and 3 <= geo["t"] <= 7
    step("bubbles.ring_by_bbox 还原环心与环厚", ok, "" if geo is None else "t=%.1f" % geo["t"])
    # redraw 的 locate 兜底只在三法失败时触发：空白图上 holes/rays 都失败 → locate 被调用
    calls = []

    def fake_locate(img, box):
        calls.append(box)
        return {"box": (150, 160, 250, 240), "present": 0.9, "confidence": 0.8}
    im3 = Image.new("RGB", (400, 400), (255, 255, 255))
    ImageDraw.Draw(im3).ellipse([150, 160, 250, 240], outline=(0, 0, 0), width=5)
    geo, rect = bubbles.redraw(im3, ImageDraw.Draw(im3), (190, 190, 210, 210), "07", locate=fake_locate)
    # 这张图上填洞法本身就能成功 → locate 不该被调用
    step("redraw：三法成功时不调 locate", not calls and geo is not None, geo["method"] if geo else "None")
    # 编号框离环很远（检测框错位的情形）：填洞法的搜索窗与射线都够不到环 → 三法失败 → 该走 locate
    im4 = Image.new("RGB", (400, 400), (255, 255, 255))
    ImageDraw.Draw(im4).ellipse([150, 160, 250, 240], outline=(0, 0, 0), width=5)
    geo, rect = bubbles.redraw(im4, ImageDraw.Draw(im4), (20, 20, 40, 40), "07", locate=fake_locate)
    step("redraw：三法失败时调 locate 并用其外框", calls == [(20, 20, 40, 40)] and geo is not None
         and geo["method"] == "bbox" and "locate" in geo and abs(geo["cx"] - 200) <= 1,
         geo["method"] if geo else "None")


def _run(args, env):
    r = subprocess.run([sys.executable] + args, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def t_default_unchanged():
    """开关关闭时：route.py 与 figpipe detect 的产物在改动前后应完全一致；占位开关打开时只多出字段。"""
    base = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    for k in ("PDF_ZH_TYPESAFE", "PDF_ZH_TYPESAFE_MOCK", "TYPESAFE_API_KEY"):
        base.pop(k, None)
    on = dict(base, PDF_ZH_TYPESAFE="1", PDF_ZH_TYPESAFE_MOCK="1")
    pdf = os.path.join(ROOT, "docs", "showcase", "SWI-650-SS_Assembly_en.pdf")
    if not os.path.exists(pdf):
        step("样例 PDF 存在", False, pdf)
        return
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    j_off, j_on = os.path.join(OUT, "route_off.json"), os.path.join(OUT, "route_on.json")
    rc1, o1 = _run([os.path.join(SCRIPTS, "route.py"), pdf, "--json", j_off], base)
    rc2, o2 = _run([os.path.join(SCRIPTS, "route.py"), pdf, "--json", j_on, "--typesafe"], on)
    step("route.py 关闭/占位两次都成功", rc1 == 0 and rc2 == 0, (o1 + o2)[-300:] if rc1 or rc2 else "")
    a, b = json.load(open(j_off, encoding="utf-8"))[0], json.load(open(j_on, encoding="utf-8"))[0]
    step("route：关闭时无 ts 字段", "ts_usage" not in a and all("ts" not in r for r in a["rows"]))
    step("route：占位时判级与各行启发式字段不变",
         a["level"] == b["level"] and a["reason"] == b["reason"] and a["p_pages"] == b["p_pages"]
         and all({k: v for k, v in rb.items() if k != "ts"} == ra for ra, rb in zip(a["rows"], b["rows"])))
    step("route：占位时每行有 ts、文档级有 ts_usage/ts_disagree",
         all("ts" in r and "level" in r["ts"] for r in b["rows"]) and "ts_usage" in b and "ts_disagree" in b
         and b["ts_model"] == tsjudge.MODEL)
    # route.py 关闭时不得 import tsjudge
    rc, o = _run(["-c", "import sys; sys.path.insert(0, %r); import route; route.classify(%r); "
                  "print('tsjudge' in sys.modules)" % (SCRIPTS, pdf)], base)
    step("route.classify 关闭时不 import tsjudge", rc == 0 and o.strip().endswith("False"), o.strip()[-80:])
    # figpipe detect：关闭 vs 占位
    for tag, env in (("off", base), ("on", on)):
        work = os.path.join(OUT, "fig_" + tag)
        os.makedirs(work)
        rc, o = _run([os.path.join(SCRIPTS, "figpipe.py"), "extract", pdf, work], env)
        rc2, o2 = _run([os.path.join(SCRIPTS, "figpipe.py"), "detect", work, "--src", "figures_src"], env)
        step("figpipe extract+detect（%s）" % tag, rc == 0 and rc2 == 0, (o + o2)[-300:] if rc or rc2 else "")
    d_off = open(os.path.join(OUT, "fig_off", "data", "det_boxes.json"), "rb").read()
    d_on = open(os.path.join(OUT, "fig_on", "data", "det_boxes.json"), "rb").read()
    step("figpipe：det_boxes.json 关闭/占位逐字节一致", d_off == d_on)
    step("figpipe：关闭时没有 det_hints.json", not os.path.exists(os.path.join(OUT, "fig_off", "data", "det_hints.json")))
    hp = os.path.join(OUT, "fig_on", "data", "det_hints.json")
    if os.path.exists(hp):
        h = json.load(open(hp, encoding="utf-8"))
        boxes = json.loads(d_on)["boxes"]
        ok = h["model"] == tsjudge.MODEL and all(
            set(h["figures"][s]["boxes"]) == {str(i) for i in range(len(bs))} for s, bs in boxes.items())
        step("figpipe：占位时 det_hints.json 覆盖每个检测框", ok)
    else:
        step("figpipe：占位时写出 det_hints.json", False)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("tsjudge 离线自检  Python %d.%d  %s" % (sys.version_info[0], sys.version_info[1], sys.platform))
    t_prepare()
    t_mock_domain()
    t_default_unchanged()
    print("\n结论：" + ("全部通过" if not _fails else "失败 %d 项：%s" % (len(_fails), _fails)))
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
