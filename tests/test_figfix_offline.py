# -*- coding: utf-8 -*-
"""Synthetic, offline regression tests for bitmap figure-label replacement."""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pdf-translate-zh", "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402
bootstrap.ensure(quiet=True)
import figfix  # noqa: E402
import figpipe  # noqa: E402
import figlabel  # noqa: E402
import fontkit  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FAILS = []


def step(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + ((" — " + detail) if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


def _jpeg(im, quality=75, subsampling=2):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, subsampling=subsampling)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _font(path, size):
    return ImageFont.truetype(path, size)


def t_clean_and_protection():
    latin = fontkit.find("mono-bold")
    im = Image.new("RGB", (360, 180), "white")
    d = ImageDraw.Draw(im)
    d.text((70, 74), "TEST LABEL", font=_font(latin, 30), fill="black")
    im = _jpeg(im)
    final, report = figfix.apply_labels(im, [(62, 65, 265, 112)], {0: {"zh": "测试标签"}})
    a = np.asarray(final)
    ex0, ey0, ex1, ey1 = report["erase_boxes"][0]
    hx0, hy0 = max(0, ex0 - 24), max(0, ey0 - 24)
    hx1, hy1 = min(final.width, ex1 + 25), min(final.height, ey1 + 25)
    region = a[hy0:hy1, hx0:hx1]
    outside = np.ones(region.shape[:2], bool)
    outside[max(0, ey0 - hy0):min(region.shape[0], ey1 + 1 - hy0),
            max(0, ex0 - hx0):min(region.shape[1], ex1 + 1 - hx0)] = False
    near_white_not_white = outside & (region.min(axis=2) >= 245) & (region.max(axis=2) < 255)
    ratio = near_white_not_white.sum() / max(1, outside.sum())
    step("JPEG 灰框：文字框外 24px 内净化后 <0.1%", ratio < 0.001, "ratio=%.5f" % ratio)
    step("JPEG 灰框：残留核查命中 0", not figfix.check_residual(im, report["erase_image"], report["erase_boxes"]))

    crossed = Image.new("RGB", (300, 180), "white")
    cd = ImageDraw.Draw(crossed)
    cd.text((70, 75), "CROSS", font=_font(latin, 32), fill="black")
    cd.line((145, 50, 145, 145), fill="black", width=2)
    final, report = figfix.apply_labels(crossed, [(55, 66, 225, 125)], {0: {"zh": "交叉", "anchor": "C"}})
    source_pixels = np.asarray(crossed)[50:146, 144:147]
    final_pixels = np.asarray(final)[50:146, 144:147]
    step("线条保护：穿过描白区的竖线像素完整保留",
         np.array_equal(source_pixels, final_pixels))


def t_color_detection_and_cleanup():
    latin = fontkit.find("mono-bold")
    im = Image.new("RGB", (360, 140), "white")
    d = ImageDraw.Draw(im)
    d.text((30, 25), "ORANGE", font=_font(latin, 24), fill=(245, 129, 31))
    d.text((30, 78), "CYAN", font=_font(latin, 24), fill=(42, 170, 225))
    path = os.path.join(ROOT, "tests", "_out", "figfix_detection.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
    kw = dict(thr=150, min_area=2, max_h=40, line_gap=2, word_gap=12, para_gap=4)
    minimum = figlabel.detect_raster_labels(path, ink="min", **kw)
    luma = figlabel.detect_raster_labels(path, ink="luma", **kw)
    step("彩色检测：最小通道检出橙/青两行", len(minimum) == 2, "框数=%d" % len(minimum))
    step("彩色检测负对照：亮度漏检橙字", len(luma) == 1, "框数=%d" % len(luma))

    curve = Image.new("RGB", (320, 100), "white")
    ImageDraw.Draw(curve).line((20, 50, 300, 50), fill=(250, 235, 230), width=4)
    jpeg = _jpeg(curve)
    before = np.asarray(jpeg).astype(np.int16)
    curve_mask = (before.max(axis=2) - before.min(axis=2) > 12) & (before.min(axis=2) >= 225)
    figfix.clean_global(jpeg, chroma_max=12)
    after = np.asarray(jpeg).astype(np.int16)
    preserved = np.all(after[curve_mask] == before[curve_mask], axis=1).mean() if curve_mask.any() else 1.0
    step("全局净化：色度上限保留 ≥95% 浅彩曲线", preserved >= 0.95,
         "preserved=%.3f" % preserved)

    color = (205, 31, 69)
    label = Image.new("RGB", (300, 130), "white")
    ImageDraw.Draw(label).text((60, 46), "RED LABEL", font=_font(latin, 32), fill=color)
    jpeg_label = _jpeg(label, quality=75, subsampling=2)
    got = figfix.ink_color(np.asarray(jpeg_label), (45, 37, 260, 100), mode="sat")
    delta = max(abs(a - b) for a, b in zip(color, got))
    step("JPEG 字色：sat 取色最大通道差 ≤20", delta <= 20, "真值=%s 实得=%s" % (color, got))


def t_layout_and_gates():
    latin = fontkit.find("mono-bold")
    zh = fontkit.find("zh")
    im = Image.new("RGB", (440, 190), "white")
    d = ImageDraw.Draw(im)
    f = _font(latin, 24)
    d.text((50, 70), "LONG LABEL", font=f, fill="black")
    tb = d.textbbox((50, 70), "LONG LABEL", font=f)
    endpoint = (tb[2] + 8, 84)
    d.line((endpoint[0], endpoint[1], 390, endpoint[1]), fill="black", width=2)
    source = im.copy()
    final, report = figfix.apply_labels(
        im, [(42, 59, 230, 105)],
        {0: {"zh": "中文", "anchor": "R:%d,%d" % endpoint}},
    )
    box = report["text_boxes"][0]
    gap = endpoint[0] - box[2]
    gap_ok = abs(gap - 8) <= 2
    line_ok = np.asarray(final)[84, endpoint[0]:390].min() < 30
    step("引线补接：中文边缘保持原设计间距 ±2px 且引线连续",
         gap_ok and line_ok, "gap=%.1f" % gap)

    two = Image.new("RGB", (420, 190), "white")
    td = ImageDraw.Draw(two)
    td.text((40, 35), "FIRST ROW", font=f, fill="black")
    td.text((40, 85), "SECOND", font=f, fill="black")
    endpoint = (250, 99)
    td.line((endpoint[0], endpoint[1], 380, endpoint[1]), fill="black", width=2)
    _, report = figfix.apply_labels(
        two, [(32, 29, 215, 120)],
        {0: {"zh": "合并文字", "anchor": "R:%d,%d" % endpoint}},
    )
    ymid = (report["text_boxes"][0][1] + report["text_boxes"][0][3]) / 2
    step("两行合一行：手给端点垂直对齐 ≤2px", abs(ymid - endpoint[1]) <= 2,
         "差=%.1f" % abs(ymid - endpoint[1]))

    vertical = Image.new("RGB", (220, 260), "white")
    vd = ImageDraw.Draw(vertical)
    vd.text((100, 40), "V", font=_font(latin, 24), fill="black")
    vd.text((100, 70), "E", font=_font(latin, 24), fill="black")
    vd.text((100, 100), "R", font=_font(latin, 24), fill="black")
    final, report = figfix.apply_labels(
        vertical, [(98, 30, 120, 142)], {0: {"zh": "竖", "rot": 90}}
    )
    tall = report["erase_boxes"][0][3] - report["erase_boxes"][0][1]
    step("竖排：不被收成单字，误擦核查为 0",
         tall > 3 * (report["erase_boxes"][0][2] - report["erase_boxes"][0][0]) and
         not figfix.check_lost(vertical, final, report["erase_boxes"], report["text_boxes"]))

    number = Image.new("RGB", (240, 100), "white")
    nd = ImageDraw.Draw(number)
    draw_font = _font(latin, 32)
    nd.text((30, 25), "0123456789", font=draw_font, fill="black")
    cap = figfix.cap_height(np.asarray(number), (20, 18, 220, 65))
    size = int(round(cap / figfix.font_cap_ratio(zh)))
    output = Image.new("RGB", (240, 100), "white")
    od = ImageDraw.Draw(output)
    od.text((30, 25), "0123456789", font=_font(zh, size), fill="black")
    drawn = figfix.cap_height(np.asarray(output), (20, 18, 220, 65))
    step("字号：中文数字墨迹高与原文相差 ≤1px", abs(drawn - cap) <= 1,
         "原文=%.1f 中文=%.1f" % (cap, drawn))

    src = Image.new("RGB", (200, 120), "white")
    sd = ImageDraw.Draw(src)
    sd.text((30, 40), "MISS", font=f, fill="black")
    wrong_erase = src.copy()
    ImageDraw.Draw(wrong_erase).rectangle((95, 35, 185, 90), fill="white")
    residual = figfix.check_residual(src, wrong_erase, [(30, 40, 150, 75)])
    line_src = Image.new("RGB", (200, 120), "white")
    ImageDraw.Draw(line_src).line((100, 20, 100, 100), fill="black", width=2)
    line_final = line_src.copy()
    ImageDraw.Draw(line_final).line((100, 20, 100, 100), fill="white", width=2)
    lost = figfix.check_lost(line_src, line_final, [(90, 30, 110, 90)], [])
    overlap = figfix.check_overlap(line_src, [(90, 35, 110, 85)])
    step("三道核查负对照：残留 / 误擦 / 压线各命中",
         bool(residual) and bool(lost) and bool(overlap),
         "残留=%d 误擦=%d 压线=%d" % (len(residual), len(lost), len(overlap)))

    bubble = Image.new("RGB", (180, 130), (210, 220, 230))
    bd = ImageDraw.Draw(bubble)
    bd.ellipse((45, 35, 95, 85), outline=(20, 40, 60), width=3)
    bd.text((59, 48), "07", font=_font(latin, 20), fill=(20, 40, 60))
    bd.line((95, 60, 145, 95), fill=(20, 40, 60), width=3)
    kept, _ = figfix.apply_labels(bubble, [(42, 30, 100, 90)], {0: "__KEEP__"})
    step("气泡 KEEP：未列入 BUBBLES 时原图逐像素不变",
         np.array_equal(np.asarray(bubble), np.asarray(kept)))


def t_figpipe_integration():
    latin = fontkit.find("mono-bold")
    image = Image.new("RGB", (320, 160), "white")
    ImageDraw.Draw(image).text((60, 55), "SAMPLE", font=_font(latin, 28), fill="black")
    with tempfile.TemporaryDirectory(prefix="figfix_") as work:
        src = os.path.join(work, "figures_src")
        data = os.path.join(work, "data")
        os.makedirs(src)
        os.makedirs(data)
        image.save(os.path.join(src, "demo.png"))
        with open(os.path.join(data, "det_boxes.json"), "w", encoding="utf-8") as stream:
            json.dump({"src": "figures_src", "boxes": {"demo": [[50, 45, 205, 95]]}}, stream)
        errors = figpipe.apply(work, {"demo": {0: {"zh": "样例标注"}}})
        qa = figpipe.check(work)
        step("figpipe 默认 figfix apply → check 三道核查", not errors and not qa,
             "apply=%d check=%d" % (len(errors), len(qa)))

        legacy_work = os.path.join(work, "legacy")
        os.makedirs(os.path.join(legacy_work, "figures_src"))
        os.makedirs(os.path.join(legacy_work, "data"))
        image.save(os.path.join(legacy_work, "figures_src", "demo.png"))
        with open(os.path.join(legacy_work, "data", "det_boxes.json"), "w", encoding="utf-8") as stream:
            json.dump({"src": "figures_src", "boxes": {"demo": [[50, 45, 205, 95]]}}, stream)
        legacy_errors = figpipe.apply(legacy_work, {"demo": {0: "Sample label"}},
                                      label_style="legacy")
        step("LABEL_STYLE=legacy 保留旧路径可用",
             not legacy_errors and os.path.exists(os.path.join(legacy_work, "figures", "demo.png")))


def main():
    t_clean_and_protection()
    t_color_detection_and_cleanup()
    t_layout_and_gates()
    t_figpipe_integration()
    print("\n结论：" + ("全部通过" if not FAILS else "失败：" + "、".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
