# -*- coding: utf-8 -*-
"""插图画质修复：Real-ESRGAN x4plus 超分，三种后端按本机条件自动选。

    python sr.py <src_dir> <dst_dir> [--backend auto|torch|onnx|lanczos]
                 [--places places.json --min-dpi 150] [--only x96,x100] [--twice x727]
                 [--tile 256] [--device auto|cuda|mps|cpu] [--weights PATH] [--onnx PATH]
    python sr.py --fetch                 # 只下载并校验权重（换电脑时预先准备）
    python sr.py --export-onnx [OUT]     # 在装了 torch 的机器上导出 ONNX，拷给没有 torch 的机器用

判据（figures.md §16）：位图**有效分辨率** = 像素宽 / 版面放置宽(pt) × 72。
  · < 150 dpi（实测 某客户 SWI 作业指导书 整册 510 px / 430 pt ≈ 85 dpi）→ 先超分 4 倍再做标注检测与回叠；
  · ≥ 300 dpi 的原图不动（超分只会引入伪影）；极小徽标（13×13 px）可 --twice（16 倍）。
⚠ 带**独立高分辨率软掩膜**的徽标不要超分：按掩膜分辨率把基色图放大后合成（figures.md §16.2）。

三种后端（--backend auto 按此顺序取第一个可用的）
  torch     Real-ESRGAN（RRDBNet 纯 PyTorch 实现）。自动选 CUDA → Apple MPS → CPU。
            体积大（CPU 版约 200 MB，Windows CUDA 版约 2.5 GB），适合有 NVIDIA 显卡或 Apple 芯片的机器。
  onnx      同一模型的 ONNX 版 + onnxruntime（约 25 MB）。没有 torch 的机器用它：
            在任一有 torch 的机器上 `--export-onnx` 一次，把 .onnx 拷过去即可（CPU/CoreML/DirectML/CUDA）。
  lanczos   兜底：Lanczos 放大 4 倍 + 反锐化。**不是超分**，只保证流程不中断；
            会在 sr_report.json 里如实记下，附录 A 丙必须写成「Lanczos 放大」而非「超分」。

权重 RealESRGAN_x4plus.pth（67 MB，BSD-3，不随技能分发）查找顺序：
  --weights → 环境变量 PDF_ZH_SR_WEIGHTS → scripts/models/ → 用户缓存目录；
  都没有就依次从下载源取（环境变量 PDF_ZH_SR_URL 可指定自己的镜像，例如公司内网或对象存储），
  每个下载都校验 SHA-256，截断或错文件一律丢弃换下一个源。
分块推理（--tile）让显存/内存与图幅无关；每块补成固定尺寸，CoreML 等静态图后端也能跑。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_NAME = "RealESRGAN_x4plus.pth"
ONNX_NAME = "RealESRGAN_x4plus.onnx"
MODEL_SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
# 下载源：官方 GitHub 发布页在前；Hugging Face 与其国内镜像作后备（内容以 SHA-256 为准，
# 源里若是别的文件会被校验拦下）。可用 PDF_ZH_SR_URL 追加自己的镜像，排在最前。
MODEL_URLS = [
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
    "https://hf-mirror.com/lllyasviel/Annotators/resolve/main/RealESRGAN_x4plus.pth",
    "https://huggingface.co/lllyasviel/Annotators/resolve/main/RealESRGAN_x4plus.pth",
]
MODEL_URL = MODEL_URLS[0]          # 兼容旧引用
MODEL_DEFAULT = None               # 兼容旧调用：None = 自动查找


# ================================================================ 路径与下载
def _cache_dir():
    try:
        sys.path.insert(0, HERE)
        import fontkit
        d = os.path.join(fontkit.cache_dir(), "models")
    except Exception:
        d = os.path.join(os.path.expanduser("~"), ".cache", "pdf-translate-zh", "models")
    os.makedirs(d, exist_ok=True)
    return d


def _find(env, name):
    for p in (os.environ.get(env), os.path.join(HERE, "models", name),
              os.path.join(_cache_dir(), name)):
        if p and os.path.exists(p):
            return p
    return None


def default_weights():
    """已存在的权重路径；都不存在时返回应当下载到的位置（用户缓存目录）。"""
    p = _bs.cfg("sr_weights")
    if p and os.path.exists(p):
        return p
    return _find("PDF_ZH_SR_WEIGHTS", MODEL_NAME) or os.path.join(_cache_dir(), MODEL_NAME)


def default_onnx(fetch=True):
    """ONNX 模型路径：config/环境变量 sr_onnx → scripts/models/ → 缓存；配了 sr_onnx_url 时自动下载。"""
    p = _bs.cfg("sr_onnx")
    if p and os.path.exists(p):
        return p
    p = _find("PDF_ZH_SR_ONNX", ONNX_NAME)
    if p or not fetch:
        return p
    url = _bs.cfg("sr_onnx_url")
    if not url:
        return None
    out = os.path.join(_cache_dir(), ONNX_NAME)
    try:
        import urllib.request
        print(f"[sr] 下载 ONNX 模型：{url}", flush=True)
        urllib.request.urlretrieve(url, out + ".part")
        want = _bs.cfg("sr_onnx_sha256")
        if want and _sha256(out + ".part") != want:
            os.remove(out + ".part")
            print("[sr] ONNX 模型 SHA-256 不符，已丢弃", flush=True)
            return None
        os.replace(out + ".part", out)
        return out
    except Exception as e:
        print(f"[sr] ONNX 模型下载失败：{e}", flush=True)
        return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_weights(path=None, verbose=True):
    path = path or default_weights()
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import urllib.request
    urls = ([_bs.cfg("sr_url")] if _bs.cfg("sr_url") else []) + MODEL_URLS
    tmp = path + ".part"
    errs = []
    for u in urls:
        try:
            if verbose:
                print(f"[sr] 下载权重（67 MB）：{u}", flush=True)
            urllib.request.urlretrieve(u, tmp)
            got = _sha256(tmp)
            if got == MODEL_SHA256:
                os.replace(tmp, path)
                return path
            errs.append(f"{u} → SHA-256 不符（{got[:12]}…）")
        except Exception as e:
            errs.append(f"{u} → {type(e).__name__}: {e}")
        if os.path.exists(tmp):
            os.remove(tmp)
    raise RuntimeError("[sr] 权重下载失败：\n  " + "\n  ".join(errs) +
                       f"\n请手动下载 RealESRGAN_x4plus.pth（SHA-256 {MODEL_SHA256[:16]}…）放到 {path}，"
                       "或设 PDF_ZH_SR_URL 指向可用镜像；也可 --backend lanczos 先出稿。")


# ================================================================ torch 后端
def _torch():
    import torch  # noqa: F401
    return torch


def build_net():
    """RRDBNet(num_feat=64, num_block=23, num_grow_ch=32)，键名与 basicsr 一致。"""
    torch = _torch()
    nn, F = torch.nn, torch.nn.functional

    class RDB(nn.Module):
        def __init__(self, nf=64, gc=32):
            super().__init__()
            self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
            self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
            self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
            self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
            self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, True)

        def forward(self, x):
            x1 = self.lrelu(self.conv1(x))
            x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
            x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
            x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
            x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
            return x5 * 0.2 + x

    class RRDB(nn.Module):
        def __init__(self, nf=64, gc=32):
            super().__init__()
            self.rdb1, self.rdb2, self.rdb3 = RDB(nf, gc), RDB(nf, gc), RDB(nf, gc)

        def forward(self, x):
            return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x

    class RRDBNet(nn.Module):
        def __init__(self, in_ch=3, out_ch=3, nf=64, nb=23, gc=32):
            super().__init__()
            self.conv_first = nn.Conv2d(in_ch, nf, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
            self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_last = nn.Conv2d(nf, out_ch, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, True)

        def forward(self, x):
            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
            return self.conv_last(self.lrelu(self.conv_hr(feat)))

    return RRDBNet()


def pick_device(name="auto"):
    torch = _torch()
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        return torch.device("mps")
    return torch.device("cpu")


def load_model(dev, weights=None):
    torch = _torch()
    try:
        ck = torch.load(ensure_weights(weights), map_location="cpu", weights_only=True)
    except TypeError:                         # torch < 1.13 没有 weights_only
        ck = torch.load(ensure_weights(weights), map_location="cpu")
    sd = ck.get("params_ema", ck.get("params", ck))
    net = build_net()
    net.load_state_dict(sd, strict=True)
    return net.eval().to(dev)


def export_onnx(out=None, weights=None, opset=17):
    """导出 ONNX（输入 1×3×H×W，H/W 动态）。需要 torch；产物可拷到任何装了 onnxruntime 的机器。"""
    torch = _torch()
    out = out or os.path.join(_cache_dir(), ONNX_NAME)
    net = load_model(torch.device("cpu"), weights)
    dummy = torch.rand(1, 3, 64, 64)
    torch.onnx.export(net, dummy, out, input_names=["x"], output_names=["y"], opset_version=opset,
                      dynamic_axes={"x": {2: "h", 3: "w"}, "y": {2: "h4", 3: "w4"}}, dynamo=False)
    return out


# ================================================================ 分块推理（三后端共用）
def _tiled(run, a, pad=10, tile=256, scale=4):
    """a: H×W×3 float32 [0,1] → (H·4)×(W·4)×3。每块补成固定 (tile+2pad)² 再推理，拼接无缝。"""
    H0, W0 = a.shape[:2]
    a = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    H, W = a.shape[:2]
    if not tile or (H <= tile + 2 * pad and W <= tile + 2 * pad):
        out = run(a)
    else:
        out = np.zeros((H * scale, W * scale, 3), np.float32)
        side = tile + 2 * pad
        for y0 in range(0, H, tile):
            for x0 in range(0, W, tile):
                y1, x1 = min(y0 + tile, H), min(x0 + tile, W)
                ya, xa = max(y0 - pad, 0), max(x0 - pad, 0)
                yb, xb = min(y1 + pad, H), min(x1 + pad, W)
                blk = a[ya:yb, xa:xb]
                ph, pw = side - blk.shape[0], side - blk.shape[1]
                if ph > 0 or pw > 0:            # 边缘块补到固定尺寸（静态形状后端需要）
                    blk = np.pad(blk, ((0, max(ph, 0)), (0, max(pw, 0)), (0, 0)), mode="edge")
                o = run(blk)
                out[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = \
                    o[(y0 - ya) * scale:(y1 - ya) * scale, (x0 - xa) * scale:(x1 - xa) * scale]
    out = out[pad * scale:(pad + H0) * scale, pad * scale:(pad + W0) * scale]
    return np.clip(out, 0, 1)


class Upscaler:
    """统一入口：Upscaler(backend="auto")(PIL 图) → PIL 图（4 倍）。`.method` 记处置方式。"""

    def __init__(self, backend="auto", device="auto", weights=None, onnx=None, tile=-1,
                 verbose=True):
        self.backend = self._pick(backend, onnx)
        self.tile = tile
        self.device = ""
        if self.backend == "torch":
            torch = _torch()
            self.dev = pick_device(device)
            self.net = load_model(self.dev, weights)
            self.device = str(self.dev)
            if self.tile < 0:
                self.tile = 512 if self.dev.type == "cuda" else 256
            self.method = f"Real-ESRGAN x4plus 超分 4 倍（torch/{self.device}）"
            self._torch = torch
        elif self.backend == "onnx":
            import onnxruntime as ort
            path = onnx or default_onnx()
            want = ["CUDAExecutionProvider", "DmlExecutionProvider",
                    "CoreMLExecutionProvider", "CPUExecutionProvider"]
            prov = [p for p in want if p in ort.get_available_providers()] or None
            self.sess = ort.InferenceSession(path, providers=prov)
            self.device = self.sess.get_providers()[0]
            if self.tile < 0:
                self.tile = 256
            self.method = f"Real-ESRGAN x4plus 超分 4 倍（onnxruntime/{self.device}）"
        else:
            self.method = "Lanczos 放大 4 倍 + 反锐化（非超分，本机无 torch/onnxruntime）"
        if verbose:
            print(f"[sr] 后端：{self.method}" + (f"  tile={self.tile}" if self.backend != "lanczos" else ""))

    @staticmethod
    def _pick(backend, onnx, autoinstall=True):
        if backend != "auto":
            return backend
        for attempt in (0, 1):
            try:
                _torch()
                return "torch"
            except Exception:
                pass
            try:
                import onnxruntime  # noqa: F401
                if onnx or default_onnx(fetch=autoinstall):
                    return "onnx"
            except Exception:
                pass
            # 第一次发现没有真超分后端：按本机条件自动装一个（torch CUDA / MPS / CPU），再选一次
            if attempt == 0 and autoinstall and _bs.ensure_sr():
                continue
            break
        return "lanczos"

    def _run_torch(self, blk):
        torch = self._torch
        t = torch.from_numpy(np.ascontiguousarray(blk.transpose(2, 0, 1)))[None].to(self.dev)
        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.float16,
                                             enabled=(self.dev.type == "cuda")):
            y = self.net(t).float()
        return y[0].permute(1, 2, 0).cpu().numpy()

    def _run_onnx(self, blk):
        x = np.ascontiguousarray(blk.transpose(2, 0, 1))[None].astype(np.float32)
        y = self.sess.run(None, {self.sess.get_inputs()[0].name: x})[0]
        return y[0].transpose(1, 2, 0)

    def __call__(self, im):
        if self.backend == "lanczos":
            w, h = im.size
            big = im.convert("RGB").resize((w * 4, h * 4), Image.LANCZOS)
            return big.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))
        a = np.asarray(im.convert("RGB")).astype(np.float32) / 255.0
        run = self._run_torch if self.backend == "torch" else self._run_onnx
        out = _tiled(run, a, tile=self.tile)
        return Image.fromarray((out * 255.0).round().astype(np.uint8))


def upscale(net, im, dev, pad=10, tile=0):
    """旧接口兼容：用已加载的 torch 模型放大一幅图。新代码请用 Upscaler。"""
    u = Upscaler.__new__(Upscaler)
    u.backend, u.net, u.dev, u.tile, u._torch = "torch", net, dev, tile, _torch()
    return u(im)


def effective_dpi(px_w, pt_w):
    """位图有效分辨率：像素宽 / 版面宽(pt) × 72。"""
    return px_w / float(pt_w) * 72.0 if pt_w else 0.0


def available():
    """doctor 用：(将选用的后端, 说明)。不加载模型。"""
    b = Upscaler._pick("auto", None, autoinstall=False)
    if b == "torch":
        torch = _torch()
        dev = "CUDA" if torch.cuda.is_available() else (
            "Apple MPS" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
            else "CPU")
        return b, f"torch {torch.__version__}（{dev}）"
    if b == "onnx":
        return b, f"onnxruntime + {default_onnx()}"
    return b, "无 torch / onnxruntime+ONNX 模型：只能 Lanczos 放大（非超分）"


# ================================================================ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", nargs="?")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--backend", default="auto", choices=["auto", "torch", "onnx", "lanczos"])
    ap.add_argument("--weights", default=None, help="缺省自动查找/下载")
    ap.add_argument("--onnx", default=None, help="ONNX 模型路径（onnx 后端）")
    ap.add_argument("--tile", type=int, default=-1, help="分块边长 px；0 = 不分块；缺省 GPU 512 / 其他 256")
    ap.add_argument("--device", default="auto", help="torch 后端：auto|cuda|mps|cpu")
    ap.add_argument("--only", default="")
    ap.add_argument("--twice", default="", help="逗号分隔：这些图做两遍（16 倍），供极小徽标")
    ap.add_argument("--places", default="", help="images.json：按有效 dpi 筛选（< --min-dpi 才处理）")
    ap.add_argument("--min-dpi", type=float, default=150.0)
    ap.add_argument("--fetch", action="store_true", help="只下载并校验权重")
    ap.add_argument("--export-onnx", nargs="?", const="", default=None, metavar="OUT",
                    help="导出 ONNX（需 torch），缺省写到用户缓存")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if a.fetch:
        print("权重就位：", ensure_weights(a.weights))
        return 0
    if a.export_onnx is not None:
        print("ONNX 已导出：", export_onnx(a.export_onnx or None, a.weights))
        return 0
    if not (a.src and a.dst):
        ap.error("需要 src 与 dst（或用 --fetch / --export-onnx）")

    up = Upscaler(a.backend, a.device, a.weights, a.onnx, a.tile)
    os.makedirs(a.dst, exist_ok=True)
    only = set(x.strip() for x in a.only.split(",") if x.strip())
    twice = set(x.strip() for x in a.twice.split(",") if x.strip())
    dpi_of = {}
    if a.places:
        for stem, m in json.load(open(a.places, encoding="utf-8")).items():
            ws = [p["rect"][2] - p["rect"][0] for p in m.get("places", []) if p.get("rect")]
            if ws and m.get("w"):
                dpi_of[m.get("file", stem + ".png")[:-4]] = effective_dpi(m["w"], max(ws))
    report = dict(backend=up.backend, device=up.device, method=up.method, files={})
    n = skipped = 0
    for f in sorted(os.listdir(a.src)):
        if not f.lower().endswith(".png") or f.endswith("_rgba.png"):
            continue
        stem = f[:-4]
        if only and stem not in only:
            continue
        if stem in dpi_of and dpi_of[stem] >= a.min_dpi:
            skipped += 1
            Image.open(os.path.join(a.src, f)).convert("RGB").save(os.path.join(a.dst, f))
            report["files"][f] = "原样（有效分辨率 %.0f dpi ≥ %.0f）" % (dpi_of[stem], a.min_dpi)
            continue
        t0 = time.time()
        im = Image.open(os.path.join(a.src, f)).convert("RGB")
        out = up(im)
        if stem in twice:
            out = up(out)
        out.save(os.path.join(a.dst, f))
        n += 1
        report["files"][f] = up.method + ("（两遍，16 倍）" if stem in twice else "")
        print(f"  {f:14s} {im.width}x{im.height} → {out.width}x{out.height}  {time.time() - t0:.1f}s"
              + (f"  ({dpi_of[stem]:.0f} dpi)" if stem in dpi_of else ""))
    with open(os.path.join(a.dst, "sr_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(f"done: 处理 {n} 幅，原样 {skipped} 幅 → {a.dst}（处置方式记在 sr_report.json，写附录 A 丙时照抄）")
    if up.backend == "lanczos":
        print("  WARN 本次是 Lanczos 放大而非超分：装 torch，或拷一个 ONNX 模型并装 onnxruntime 后重跑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
