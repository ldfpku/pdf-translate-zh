# -*- coding: utf-8 -*-
"""TypeSafe 图像判断（可选）：把页面图 / 插图 / 裁片交给 System One 模型 Jev 做**类型化判断**。

Jev 不生成文本，只返回判断：Choice（单选 + 各项概率）、Noul（是/否的概率）、Box（目标在图里的位置，
0~1 比例坐标 + 0~1 置信度）。本模块把它接在流水线里**现有启发式看不见**的三处：

    页面级别   route.py --typesafe      页面图 → Choice(R/P/S/空白)   只记录与对照，**不改判级**
    图内文字   figpipe.py detect        插图 → Noul 有无文字；每个检测框 → Noul 是文字标注 / 是件号气泡
    件号气泡   figpipe.py apply         三法求环都失败的气泡 → Noul 判存在 + Box 定环，坐标换算回图
    表格网格   tsjudge.py tables        tablefix.regions() 认出的每块区域 → Noul 是不是真表格

开关与密钥（**默认关闭；关闭时没有任何入口 import 本模块，默认流程字节不变**）：
    PDF_ZH_TYPESAFE=1        打开（只认环境变量，不读 config.json —— config.json 跟着技能走到每台电脑，
                             「把文档图片上传到云端」这种开关不该被静默带走）
    TYPESAFE_API_KEY=…       密钥，**只从环境变量读**，不写进任何文件、不进日志、不回显
    PDF_ZH_TYPESAFE_MOCK=1   不联网，返回占位答案（离线测试坐标换算与写盘格式用）
没有密钥时 enabled() 为 False，各入口照常走启发式，**不要替用户去要密钥**：提醒一次让用户自己设环境变量即可。

上游依赖（2026-10-20 按 docs.typesafe.ai/images、/primitives/box、/api 与 typesafe.ai/blog/jev-1-14 核实）：
    · 模型固定 jev-1.14.0（Box 原语只在 1.14；不用 jev-preview/jev-latest 这类会漂移的别名）；
    · 每个含图或含 Box 的请求必须带 HTTP 头 `TypeSafe-Danger-Zone-Images: true`，否则 400；
    · 图像功能是实验状态（"Dreamer-ready"），**请求格式、限制与准确度都可能随版本变**；
    · 图片放在顶层 `assets`（本模块用 JSON + base64），正文用唯一引用串替换；同一图被引用几次就计几次；
    · 限制：PNG/JPEG；单图 ≤ 16 MiB；边长 280~1568 px；总像素 78,400~2,458,624；请求体 ≤ 32 MiB；
      超限整个请求被拒、不缩放；EXIF 方向不处理 —— `prepare_image()` 统一转正、缩放、补白；
    · 按输入 token 计费（图像算输入 token，`usage.input_tokens`）；每次调用的 token 与耗时都随结果返回；
    · Box 没有「找不到」的答案，必须配一个 Noul 判存在；一问一目标；大图先裁区域再问。
    · 置信度不是校准概率，阈值要在自己的图上调。本文件里的阈值都是**未实测的缺省值**。

用法：
    python tsjudge.py status                       开关、密钥有无（不显示值）、模型、是否能联网自检
    python tsjudge.py route   <pdf> [--max-pages N] 逐页：启发式 vs TypeSafe，打印分歧与 token/耗时
    python tsjudge.py figures <工作区>              对 figpipe detect 的结果逐图逐框判断 → data/det_hints.json
    python tsjudge.py tables  <pdf> [页号,…]        tablefix.regions() 的每块区域是不是真表格
"""
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

# ---------------------------------------------------------------- 集中配置（改模型/端点/头只改这里）
MODEL = "jev-1.14.0"                                  # Box 原语只在 1.14；固定版本号，不用别名
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
IMAGES_HEADER = ("TypeSafe-Danger-Zone-Images", "true")   # 含图/含 Box 的请求必带
DOCS_DATE = "2026-10-20"                              # 上游文档核实日期
KEY_ENV, SWITCH_ENV, MOCK_ENV = "TYPESAFE_API_KEY", "PDF_ZH_TYPESAFE", "PDF_ZH_TYPESAFE_MOCK"
BASE_URL_ENV = "TYPESAFE_BASE_URL"                    # 与官方 SDK 同名；一般不用设
TIMEOUT = 90.0                                        # 秒；SDK 缺省 10 s 对带图请求太短
RETRIES = 3                                           # 429 / 529 指数退避
MAX_SIDE, MIN_SIDE = 1568, 280                        # 上游边长限制（两端都含）
MAX_BODY = 32 * 1024 * 1024
CROPS_PER_REQUEST = 16                                # 一次请求里放几个裁片（控体积与上下文）

# 缺省阈值 —— 都**未实测**，在自己的图上调（references/typesafe.md）
NOUL_YES = 0.6
BOX_MIN_CONF = 0.5

REMINDER = ("TypeSafe 图像判断未启用：需要用户**自己**把密钥设为环境变量 TYPESAFE_API_KEY，并设 "
            "PDF_ZH_TYPESAFE=1（不要把密钥发到聊天里，也不要写进任何文件）。未设置时流程照常走启发式。")


class TypeSafeError(RuntimeError):
    """只带状态码与上游错误码，不带请求体、不带密钥。"""


# ---------------------------------------------------------------- 开关
def has_key():
    return bool(os.environ.get(KEY_ENV, "").strip())


def switch_on():
    return os.environ.get(SWITCH_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def mock_on():
    return os.environ.get(MOCK_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def enabled():
    """开关打开且（有密钥或处于离线占位模式）。各入口只在这里为 True 时才走本模块。"""
    return switch_on() and (has_key() or mock_on())


def status_line():
    """给 doctor.py 的一行状态，绝不输出密钥值。"""
    sw = "开" if switch_on() else "关"
    key = "有" if has_key() else "无"
    mode = "（离线占位模式）" if mock_on() else ""
    return "TypeSafe 图像判断：开关 %s，密钥 %s，模型 %s%s" % (sw, key, MODEL, mode)


# ---------------------------------------------------------------- 图像预处理（独立函数）
class Prepared(object):
    """预处理结果：png 字节 + 送出图尺寸 + 从送出图比例坐标换回**源图像素**所需的量。

    源图 → 送出图：先 `scale` 缩放（长边 ≤ MAX_SIDE；短边 < MIN_SIDE 时放大），再在**右、下**补白到
    MIN_SIDE（补白不移动原点，所以只需 scale 与补白前的尺寸）。
    """

    def __init__(self, png, w, h, scale, src_w, src_h):
        self.png, self.w, self.h, self.scale, self.src_w, self.src_h = png, w, h, scale, src_w, src_h

    def to_src(self, box):
        """Box 答案 {top,bottom,left,right}（0~1，相对送出图含补白）→ 源图像素 (x0,y0,x1,y1)，钳在源图内。"""
        x0 = box["left"] * self.w / self.scale
        x1 = box["right"] * self.w / self.scale
        y0 = box["top"] * self.h / self.scale
        y1 = box["bottom"] * self.h / self.scale
        clamp = lambda v, hi: max(0.0, min(float(hi), v))
        return (clamp(x0, self.src_w), clamp(y0, self.src_h), clamp(x1, self.src_w), clamp(y1, self.src_h))

    def from_src(self, rect):
        """源图像素 (x0,y0,x1,y1) → 送出图比例坐标（测试与画图用）。"""
        x0, y0, x1, y1 = rect
        return dict(left=x0 * self.scale / self.w, right=x1 * self.scale / self.w,
                    top=y0 * self.scale / self.h, bottom=y1 * self.scale / self.h)


def prepare_image(src, max_side=MAX_SIDE, min_side=MIN_SIDE):
    """任何来源（PIL 图 / 文件路径 / 字节）→ 符合上游限制的 PNG（转正、缩放、补白）。

    · EXIF 方向：上游不处理，这里先 `exif_transpose` 把像素转正；
    · 长边 > max_side 缩小；短边 < min_side 放大（放大后长边仍不许超 max_side）；
    · 仍有一边 < min_side 的（细长条：表格行带、长标注裁片）在右、下补白到 min_side；
    · 输出 PNG（无损，裁片小；大页面图也在几 MB 内）。
    边长都落在 [min_side, max_side] 内时，总像素自然落在 [78,400, 2,458,624] 内。
    """
    from PIL import Image, ImageOps
    if isinstance(src, (bytes, bytearray)):
        im = Image.open(io.BytesIO(src))
    elif isinstance(src, str):
        im = Image.open(src)
    else:
        im = src
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    src_w, src_h = im.size
    long_, short = max(src_w, src_h), min(src_w, src_h)
    scale = min(1.0, max_side / float(long_))
    if short * scale < min_side:
        scale = min(min_side / float(short), max_side / float(long_))
    w, h = max(1, int(round(src_w * scale))), max(1, int(round(src_h * scale)))
    if (w, h) != (src_w, src_h):
        im = im.resize((w, h), Image.LANCZOS)
    pw, ph = max(w, min_side), max(h, min_side)
    if (pw, ph) != (w, h):
        canvas = Image.new("RGB", (pw, ph), (255, 255, 255))
        canvas.paste(im, (0, 0))
        im = canvas
    if not (min_side <= im.width <= max_side and min_side <= im.height <= max_side):
        raise TypeSafeError("prepare_image 结果超限：%dx%d" % (im.width, im.height))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return Prepared(buf.getvalue(), im.width, im.height, scale, src_w, src_h)


def page_png(page, dpi=110):
    """PyMuPDF 页 → PNG 字节（A4 在 110 dpi 约 910×1290 px，落在上游限制内）。"""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    pm = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    return pm.tobytes("png")


# ---------------------------------------------------------------- 请求
class Answer(object):
    def __init__(self, answers, model, input_tokens, output_tokens, seconds, request_bytes):
        self.answers, self.model = answers, model
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        self.seconds, self.request_bytes = seconds, request_bytes

    def noul(self, qid):
        return float(self.answers[qid]["noul"])

    def choice(self, qid):
        a = self.answers[qid]
        return a["choice"], dict(a.get("probabilities", {})), float(a.get("confidence", 0.0))

    def box(self, qid):
        a = self.answers[qid]
        return dict(a["box"]), float(a.get("confidence", 0.0))


def asset(prepared):
    """一张图 → (引用串, assets 条目)。引用串用 UUID，不会与正文误匹配。"""
    ref = str(uuid.uuid4())
    return ref, {"type": "image", "format": "png",
                 "data_base64": base64.b64encode(prepared.png).decode("ascii")}


def build_request(state, questions, assets, model=MODEL):
    body = {"model": model, "state": state, "assets": assets, "questions": questions}
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_BODY:
        raise TypeSafeError("请求体 %.1f MiB 超过 32 MiB 上限：减少裁片或缩小图" % (len(data) / 2.0 ** 20))
    return data


_mock_handler = None     # 测试可注入：f(body_dict) -> answers_dict


def _mock_answers(body):
    """离线占位：Noul 0.5，Choice 取首项等概率，Box 取中央一半。只用于测试写盘格式与坐标换算。"""
    if _mock_handler is not None:
        return _mock_handler(body)
    out = {}
    for qid, q in body["questions"].items():
        t = q["type"]
        if t == "noul":
            out[qid] = {"type": "noul", "noul": 0.5}
        elif t == "choice":
            keys = list(q["criteria"].keys())
            p = 1.0 / max(1, len(keys))
            out[qid] = {"type": "choice", "choice": keys[0], "probabilities": {k: p for k in keys},
                        "confidence": 0.0}
        elif t == "score":
            n = len(q["criteria"])
            out[qid] = {"type": "score", "score": (n - 1) / 2.0, "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                        "probabilities": {str(i): 1.0 / n for i in range(n)}, "confidence": 0.0}
        elif t == "box":
            out[qid] = {"type": "box", "box": {"top": 0.25, "bottom": 0.75, "left": 0.25, "right": 0.75},
                        "confidence": 0.5}
    return out


def ask(state, questions, assets, model=MODEL, timeout=TIMEOUT, retries=RETRIES):
    """发一次请求。返回 Answer；失败抛 TypeSafeError（只含状态码与上游错误码）。

    一个请求里的问题彼此独立、并行评估，互相看不到答案；同一张图放在 state 里被多个问题按路径引用，
    比写进每个问题的 instructions 省 token。
    """
    data = build_request(state, questions, assets, model)
    t0 = time.time()
    if mock_on():
        body = json.loads(data.decode("utf-8"))
        return Answer(_mock_answers(body), model + "(mock)", 0, 0, time.time() - t0, len(data))
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise TypeSafeError("缺少环境变量 %s" % KEY_ENV)
    url = os.environ.get(BASE_URL_ENV, "").rstrip("/")
    url = (url + "/v1/systemone") if url else ENDPOINT
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json; charset=utf-8",
               IMAGES_HEADER[0]: IMAGES_HEADER[1], "User-Agent": "pdf-translate-zh/tsjudge"}
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            usage = payload.get("usage") or {}
            return Answer(payload["answers"], payload.get("model", model),
                          int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0),
                          time.time() - t0, len(data))
        except urllib.error.HTTPError as e:
            code = ""
            try:
                err = json.loads(e.read().decode("utf-8", "replace"))
                code = str(err.get("error", err.get("code", err.get("message", ""))))[:120]
            except Exception:
                pass
            last = TypeSafeError("HTTP %d %s" % (e.code, code))
            if e.code in (429, 529) and attempt < retries:
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = TypeSafeError("连接失败：%s" % type(e).__name__)
            if attempt < retries:
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise last
    raise last


# ---------------------------------------------------------------- 领域判断
# 页面级别：一页一问。H 是**文档级**属性（R 页与 P 页并存），由代码汇总，不是页面选项。
LEVEL_TEXT = {
    "R": "A page of running text: paragraphs, numbered steps, bullet lists or an ordinary table. "
         "Illustrations, if any, sit inside a text layout. The page can be re-flowed without losing meaning.",
    "P": "A page whose layout IS the content: an engineering drawing (views, dimension lines, section hatching, "
         "part-number balloons, a title block), a fillable form with boxes and lines, or a chart. "
         "Coordinates carry meaning.",
    "S": "A landscape slide exported from a presentation: large text, few words per page, bullets, a title bar.",
    "blank": "An almost empty page: blank, a separator, or only a short title/number.",
}


def level_criteria(examples=None):
    """Choice 的 criteria：文字描述 + 可选示例页图引用（{"R": [ref, …], "P": [...], …}）。"""
    crit = {}
    for k, desc in LEVEL_TEXT.items():
        refs = (examples or {}).get(k) or []
        crit[k] = {"description": desc, "examples": refs} if refs else desc
    return crit


def page_level(page_image, example_images=None):
    """一页的版面级别。`page_image` 为 PNG 字节 / 路径 / PIL；`example_images` = {"R": [PIL/路径…], …}。

    返回 dict(level, probabilities, confidence, input_tokens, seconds)。
    """
    pg = prepare_image(page_image)
    ref, a = asset(pg)
    assets, ex_refs = {ref: a}, {}
    for k, ims in (example_images or {}).items():
        for im in ims:
            r, aa = asset(prepare_image(im))
            assets[r] = aa
            ex_refs.setdefault(k, []).append(r)
    qs = {"level": {"type": "choice",
                    "instructions": "Which kind of page is `page`? Judge by what the page is for, "
                                    "not by how much ink it has.",
                    "criteria": level_criteria(ex_refs)}}
    ans = ask({"page": ref}, qs, assets)
    lv, probs, conf = ans.choice("level")
    return dict(level=lv, probabilities=probs, confidence=conf,
                input_tokens=ans.input_tokens, seconds=round(ans.seconds, 2), model=ans.model)


def _crop_pad(im, box, pad_frac=0.6, pad_min=12):
    """按框裁片，四周外扩（气泡要看到环，标注要看到引线头），钳在图内。返回 (PIL, (x0,y0,x1,y1))。"""
    x0, y0, x1, y1 = box
    px = max(pad_min, (x1 - x0) * pad_frac)
    py = max(pad_min, (y1 - y0) * pad_frac)
    X0, Y0 = int(max(0, x0 - px)), int(max(0, y0 - py))
    X1, Y1 = int(min(im.width, x1 + px)), int(min(im.height, y1 + py))
    return im.crop((X0, Y0, X1, Y1)), (X0, Y0, X1, Y1)


def figure_hints(im, boxes, per_request=CROPS_PER_REQUEST):
    """一幅插图 + figpipe detect 的检测框 → 图级「有无文字」+ 逐框「是文字标注 / 是件号气泡」。

    返回 dict(has_text=p, boxes={i: {"text": p, "bubble": p}}, input_tokens, seconds, requests)。
    判断只是**提示**：写进 data/det_hints.json 供内容层填 labels_zh.py 时参考，det_boxes.json 不动。
    """
    from PIL import Image
    if isinstance(im, str):
        im = Image.open(im)
    im = im.convert("RGB")
    out = dict(has_text=None, boxes={}, input_tokens=0, seconds=0.0, requests=0)
    fig = prepare_image(im)
    fref, fa = asset(fig)
    idx = list(range(len(boxes)))
    chunks = [idx[i:i + per_request] for i in range(0, len(idx), per_request)] or [[]]
    for ci, chunk in enumerate(chunks):
        # 整幅图只随第一批发（只有 has_text 引用它）；后续批次只发裁片，省 token 与体积
        assets, state, qs = ({fref: fa}, {"figure": fref, "crops": {}}, {}) if ci == 0 else ({}, {"crops": {}}, {})
        if ci == 0:
            qs["has_text"] = {"type": "noul",
                              "instructions": "Does `figure` contain any printed words or text labels "
                                              "(names, captions, notes), not counting bare numbers inside "
                                              "circles and not counting dimension values?"}
        for i in chunk:
            crop, _rect = _crop_pad(im, boxes[i])
            r, a = asset(prepare_image(crop))
            assets[r] = a
            state["crops"]["c%d" % i] = r
            qs["text_%d" % i] = {"type": "noul",
                                 "instructions": "Is the dark mark in the middle of `crops.c%d` a printed word or "
                                                 "text label (letters, possibly with digits), rather than a line, "
                                                 "arrow, part outline, hatching or a lone number in a circle?" % i}
            qs["bubble_%d" % i] = {"type": "noul",
                                   "instructions": "Is the mark in the middle of `crops.c%d` a part-number callout "
                                                   "balloon: a number (or letter+number) enclosed by a circular or "
                                                   "oval ring, usually with a leader line?" % i}
        ans = ask(state, qs, assets)
        out["requests"] += 1
        out["input_tokens"] += ans.input_tokens
        out["seconds"] += ans.seconds
        if ci == 0:
            out["has_text"] = round(ans.noul("has_text"), 3)
        for i in chunk:
            out["boxes"][i] = {"text": round(ans.noul("text_%d" % i), 3),
                               "bubble": round(ans.noul("bubble_%d" % i), 3)}
    out["seconds"] = round(out["seconds"], 2)
    return out


def table_is_grid(crop_image):
    """一块候选表格区（裁片）是不是真表格。返回 (概率, input_tokens, seconds)。"""
    pg = prepare_image(crop_image)
    ref, a = asset(pg)
    qs = {"grid": {"type": "noul",
                   "instructions": "Is `region` a real ruled table: rows and columns of cells with text or numbers "
                                   "inside, separated by ruling lines? Answer no for a drawing frame, a part "
                                   "outline, a box around a note, or a title block with only a few labels."}}
    ans = ask({"region": ref}, qs, {ref: a})
    return ans.noul("grid"), ans.input_tokens, ans.seconds


def locate(im, region, target, presence, min_conf=BOX_MIN_CONF, yes=NOUL_YES):
    """在 `region`（源图像素框）裁片上：Noul 判存在 + Box 定位；坐标换算回源图像素。

    返回 dict(present=p, box=(x0,y0,x1,y1) 或 None, confidence, input_tokens, seconds)。
    present < yes 或 confidence < min_conf 时 box 为 None（Box 没有「找不到」答案，必须用 Noul 把关）。
    """
    from PIL import Image
    if isinstance(im, str):
        im = Image.open(im)
    im = im.convert("RGB")
    X0, Y0, X1, Y1 = [int(v) for v in region]
    X0, Y0 = max(0, X0), max(0, Y0)
    X1, Y1 = min(im.width, X1), min(im.height, Y1)
    crop = im.crop((X0, Y0, X1, Y1))
    pg = prepare_image(crop)
    ref, a = asset(pg)
    qs = {"present": {"type": "noul", "instructions": presence.replace("{img}", "`crop`")},
          "where": {"type": "box", "instructions": target.replace("{img}", "`crop`")}}
    ans = ask({"crop": ref}, qs, {ref: a})
    p = ans.noul("present")
    bx, conf = ans.box("where")
    out = dict(present=round(p, 3), box=None, confidence=round(conf, 3),
               input_tokens=ans.input_tokens, seconds=round(ans.seconds, 2))
    if p >= yes and conf >= min_conf:
        x0, y0, x1, y1 = pg.to_src(bx)
        out["box"] = (X0 + x0, Y0 + y0, X0 + x1, Y0 + y1)
    return out


def bubble_ring(im, numbox, grow=4.0, extra=40):
    """件号气泡：以编号框为中心裁一块（四周各扩 grow 倍框尺寸 + extra px），问环在哪。

    供 bubbles.redraw(locate=…) 在填洞 / 射线 / 模板三法都失败时兜底；返回源图像素框或 None。
    """
    x0, y0, x1, y1 = numbox
    w, h = x1 - x0, y1 - y0
    region = (x0 - grow * w - extra, y0 - grow * h - extra, x1 + grow * w + extra, y1 + grow * h + extra)
    r = locate(im, region,
               target="the circular or oval ring (part-number callout balloon) that encloses the number "
                      "nearest the centre of {img}, including the ring's full outline",
               presence="Is the number nearest the centre of {img} enclosed by a circular or oval ring "
                        "(a part-number callout balloon)?")
    r["region"] = region
    return r


# ---------------------------------------------------------------- 命令行
def _route_cmd(pdf, max_pages=None):
    import route
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    rt = route.classify(pdf, max_pages or route.MAX_PAGES, typesafe=False)
    rows, tok, sec, agree = [], 0, 0.0, 0
    with fitz.open(pdf) as d:
        for r in rt["rows"]:
            res = page_level(page_png(d[r["page"] - 1]))
            same = (res["level"] if res["level"] != "blank" else "R") == r["level"]
            agree += 1 if same else 0
            tok += res["input_tokens"]
            sec += res["seconds"]
            rows.append((r["page"], r["level"], res["level"], res["confidence"], res["input_tokens"], res["seconds"]))
            print("  p%-4d 启发式 %s  TypeSafe %-5s conf %.2f  %5d tok  %.1fs  %s"
                  % (r["page"], r["level"], res["level"], res["confidence"], res["input_tokens"], res["seconds"],
                     "" if same else "← 分歧"))
    n = len(rows)
    print("\n%s：%d 页，一致 %d（%.0f%%），平均 %.0f tok/页，%.1f s/页，模型 %s"
          % (os.path.basename(pdf), n, agree, 100.0 * agree / max(1, n), tok / max(1, n), sec / max(1, n), MODEL))
    print("注：启发式与模型都不是真值；分歧页请目检。")
    return 0


def _figures_cmd(work):
    from PIL import Image
    dpath = os.path.join(work, "data", "det_boxes.json")
    d = json.load(open(dpath, encoding="utf-8"))
    sdir = os.path.join(work, d["src"])
    hints, tok, sec = {}, 0, 0.0
    for stem, bs in d["boxes"].items():
        p = os.path.join(sdir, stem + ".png")
        if not os.path.exists(p):
            continue
        h = figure_hints(Image.open(p), bs)
        hints[stem] = {"has_text": h["has_text"],
                       "boxes": {str(i): v for i, v in h["boxes"].items()},
                       "input_tokens": h["input_tokens"], "seconds": h["seconds"]}
        tok += h["input_tokens"]
        sec += h["seconds"]
        print("  %s: 有文字 %.2f；%d 框（文字≥%.1f：%d，气泡≥%.1f：%d）  %d tok  %.1fs" % (
            stem, h["has_text"] if h["has_text"] is not None else -1, len(bs),
            NOUL_YES, sum(1 for v in h["boxes"].values() if v["text"] >= NOUL_YES),
            NOUL_YES, sum(1 for v in h["boxes"].values() if v["bubble"] >= NOUL_YES),
            h["input_tokens"], h["seconds"]))
    out = os.path.join(work, "data", "det_hints.json")
    json.dump({"model": MODEL, "docs_date": DOCS_DATE, "thresholds": {"noul_yes": NOUL_YES}, "figures": hints},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写入 %s（合计 %d tok，%.1fs）。这些只是提示，labels_zh.py 仍按核查图逐框核对。" % (out, tok, sec))
    return 0


def _tables_cmd(pdf, pages=None):
    import tablefix
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    from PIL import Image
    with fitz.open(pdf) as d:
        idx = pages if pages else list(range(d.page_count))
        for pi in idx:
            pg = d[pi]
            for k, r in enumerate(tablefix.regions(pg)):
                z = 2.5
                pm = pg.get_pixmap(clip=r, matrix=fitz.Matrix(z, z), alpha=False)
                im = Image.open(io.BytesIO(pm.tobytes("png")))
                p, tok, sec = table_is_grid(im)
                print("  p%d 区域 %d  %s  真表格 %.2f  %d tok  %.1fs%s"
                      % (pi + 1, k, tuple(round(v) for v in r), p, tok, sec, "" if p >= NOUL_YES else "  ← 存疑"))
    return 0


def _status_cmd():
    print(status_line())
    print("  端点 %s；文档核实日期 %s；请求头 %s: %s" % (ENDPOINT, DOCS_DATE, IMAGES_HEADER[0], IMAGES_HEADER[1]))
    if not enabled():
        print("  " + REMINDER)
        return 0
    from PIL import Image
    im = Image.new("RGB", (320, 320), (255, 255, 255))
    try:
        pg = prepare_image(im)
        ref, a = asset(pg)
        ans = ask({"img": ref}, {"blank": {"type": "noul", "instructions": "Is `img` an entirely blank white image?"}},
                  {ref: a})
        print("  联网自检 OK：模型 %s，%d tok，%.1fs，blank=%.2f" % (ans.model, ans.input_tokens, ans.seconds, ans.noul("blank")))
    except TypeSafeError as e:
        print("  联网自检失败：%s" % e)
        return 1
    return 0


def main(argv):
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bootstrap
    bootstrap.ensure()          # 命令行单跑时自动补装缺的依赖（已就绪时毫秒级返回）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    cmd = args[0]
    if cmd == "status":
        return _status_cmd()
    if not enabled():
        print(status_line())
        print("  " + REMINDER)
        return 3
    if cmd == "route":
        mp = int(args[args.index("--max-pages") + 1]) if "--max-pages" in args else None
        return _route_cmd(args[1], mp)
    if cmd == "figures":
        return _figures_cmd(args[1])
    if cmd == "tables":
        pages = [int(x) - 1 for x in args[2].split(",")] if len(args) > 2 else None
        return _tables_cmd(args[1], pages)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
