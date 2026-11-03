# -*- coding: utf-8 -*-
"""环境自动配置：依赖、中文字体、插图超分后端全自动就位，不需要人工干预。

    python3 bootstrap.py            # 一次配齐：核心依赖 + 中文字体 + 引擎自检（已就绪约 1 秒返回）
    python3 bootstrap.py --sr       # 另外装插图超分后端（torch，按本机显卡选版本）+ 下载权重
    python3 bootstrap.py --check    # 只报告，不安装

平时**不用手动跑**：每个入口脚本（translate_pdf / extract / route / preview / sr / selftest …）
和工作区的 build.py 一开头都调 `bootstrap.ensure()`，缺什么当场补什么。

设计要点（都是为了「换一台电脑也不用管」）
  · 依赖装进**技能私有目录**（用户缓存下的 pydeps/<python 版本-平台>/），用 `pip install --target`：
      - 不碰系统 Python，不需要管理员权限；
      - 绕开 macOS Homebrew / 新版 Ubuntu 的 PEP 668「禁止 pip」；
      - 按 Python 版本与平台分目录，换了 Python 自动重装一份，不会加载到不兼容的二进制包。
    系统里已经装齐的包直接用，一个都不重装（快速路径只做 find_spec，毫秒级）。
  · 下载源依次尝试：官方 PyPI → 清华 → 阿里云（`PDF_ZH_PIP_INDEX` 可插自己的源，排最前）。
  · 镜像地址等设置可写进技能根目录的 config.json（见 config.example.json），**跟着技能走到每台
    电脑**，不必每台机器设环境变量；同名环境变量优先。
  · 路径写进 PYTHONPATH，子进程（translate_pdf 调 extract、rebuild_all 调各 build.py）自动继承。
  · 先装进暂存目录、成功后再换上，安装中途被打断不会留下半套依赖；多进程同时启动有文件锁。
  · 插图超分的 torch 体积大（CUDA 版约 2.5 GB），**不在核心安装里**：第一次真正需要超分时
    （sr.py 发现有 < 150 dpi 的位图）才装；`PDF_ZH_SR_AUTOINSTALL=0` 可关掉自动安装。
  · NVIDIA 显卡按「算力 + 驱动支持的 CUDA 版本」挑 cuXXX 轮子，装完在子进程实跑一次卷积才换上；
    候选版本从下载源索引实时读取（只列有本机 Python+平台轮子的），不写死任何显卡型号；
    已装的 torch 也体检（缓存在 sr_torch_check.json），缺本机显卡的计算内核就自动换装。

本文件只用标准库 —— 它要在任何依赖都还没装的机器上先跑起来。
"""
import importlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# (import 名, pip 包名)。PyMuPDF 的 import 名两个都认（新 pymupdf / 旧 fitz）
CORE = [(("pymupdf", "fitz"), "PyMuPDF>=1.23"), (("reportlab",), "reportlab>=3.6"),
        (("PIL",), "Pillow>=9.0"), (("numpy",), "numpy>=1.21"),
        (("fontTools",), "fonttools>=4.30"), (("scipy",), "scipy>=1.7")]
INDEXES = [None,                                                   # pip 自己的配置 / 官方 PyPI
           "https://pypi.tuna.tsinghua.edu.cn/simple",
           "https://mirrors.aliyun.com/pypi/simple"]

_DONE = set()
_CFG = None


def cfg(name, default=None):
    """设置项：环境变量 PDF_ZH_<NAME> 优先，其次技能根目录 config.json 的 name 键。"""
    v = os.environ.get("PDF_ZH_" + name.upper())
    if v:
        return v
    global _CFG
    if _CFG is None:
        _CFG = {}
        p = os.path.join(os.path.dirname(HERE), "config.json")
        try:
            with open(p, encoding="utf-8") as fh:
                _CFG = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
        except FileNotFoundError:
            pass
        except Exception as e:
            print("  [bootstrap] config.json 读取失败，忽略：%s" % e, file=sys.stderr)
    return _CFG.get(name, default)


# ---------------------------------------------------------------- 路径
def cache_dir():
    d = os.environ.get("PDF_ZH_CACHE")
    if not d:
        if sys.platform.startswith("win"):
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "pdf-translate-zh", "cache")
        else:
            base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
            d = os.path.join(base, "pdf-translate-zh")
    os.makedirs(d, exist_ok=True)
    return d


def _tag():
    return "cp%d%d-%s" % (sys.version_info[0], sys.version_info[1],
                          sysconfig.get_platform().replace("-", "_").replace(".", "_"))


def site_dir(kind="core"):
    return os.path.join(cache_dir(), "pydeps", "%s-%s" % (kind, _tag()))


def _activate(path):
    """把私有依赖目录挂到 sys.path 最前，并写进 PYTHONPATH 让子进程继承。"""
    if not os.path.isdir(path):
        return
    if path not in sys.path:
        sys.path.insert(0, path)
    pp = os.environ.get("PYTHONPATH", "")
    if path not in pp.split(os.pathsep):
        os.environ["PYTHONPATH"] = path + (os.pathsep + pp if pp else "")
    importlib.invalidate_caches()


def _have(names):
    for n in names:
        try:
            if importlib.util.find_spec(n) is not None:
                return True
        except (ImportError, ValueError):
            pass
    return False


# ---------------------------------------------------------------- pip
class _Lock:
    """跨进程文件锁：两个构建同时启动时，只让一个去装。"""

    def __init__(self, path, stale=1800):
        self.path, self.stale = path, stale

    def __enter__(self):
        t0 = time.time()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > self.stale:
                        os.remove(self.path)          # 上次安装被强行中断留下的锁
                        continue
                except OSError:
                    continue
                if time.time() - t0 > self.stale:
                    raise TimeoutError("等待另一个安装进程超时：%s" % self.path)
                time.sleep(2)

    def __exit__(self, *a):
        try:
            os.close(self.fd)
            os.remove(self.path)
        except OSError:
            pass


def _pip_ok():
    if _have(["pip"]):
        return True
    # 个别 Linux 发行版的 python3 不带 pip：先试 ensurepip
    subprocess.run([sys.executable, "-m", "ensurepip", "--user", "--default-pip"],
                   capture_output=True)
    importlib.invalidate_caches()
    return _have(["pip"])


def pip_install(pkgs, target, extra_args=(), indexes=None, log=print, timeout=1800,
                fresh=False, verify=None):
    """装进 target（先装暂存目录，成功后整体替换）。依次尝试多个下载源。

    fresh=True：暂存目录从空开始（不带上 target 里已有的包），用于整套换装 torch；
    verify(stage) -> (ok, 原因)：换上之前先在暂存目录里验证，不过就丢弃、试下一个源。
    """
    if not _pip_ok():
        raise RuntimeError("这台机器的 Python 没有 pip，且 ensurepip 不可用。"
                           "Debian/Ubuntu: sudo apt install python3-pip；其他系统请装官方 Python 3.10+。")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    stage = target + ".staging"
    user_idx = cfg("pip_index")
    idx_list = indexes if indexes is not None else ([user_idx] if user_idx else []) + INDEXES
    errs = []
    for idx in idx_list:
        shutil.rmtree(stage, ignore_errors=True)
        if os.path.isdir(target) and not fresh:     # 已有的包带过去，只补缺的
            shutil.copytree(target, stage)
        cmd = [sys.executable, "-m", "pip", "install", "--target", stage, "--upgrade",
               "--disable-pip-version-check", "--no-warn-script-location",
               "--timeout", "30", "--retries", "2", *extra_args, *pkgs]
        if idx:
            cmd += ["-i", idx]
        log("  [bootstrap] pip 安装 %s%s" % (" ".join(pkgs), "（源：%s）" % idx if idx else ""))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                               env=dict(os.environ, PIP_NO_INPUT="1"))
        except subprocess.TimeoutExpired:
            errs.append("%s → 超时" % (idx or "默认源"))
            continue
        if r.returncode == 0:
            if verify is not None:
                ok, why = verify(stage)
                if not ok:
                    log("  [bootstrap] 装上了但验证不过：%s" % why)
                    errs.append("%s → 验证不过：%s" % (idx or "默认源", why))
                    continue
            old = target + ".old"
            shutil.rmtree(old, ignore_errors=True)
            try:
                if os.path.isdir(target):
                    os.replace(target, old)
                os.replace(stage, target)
            except OSError:
                # Windows：本进程已从 target 加载了 .pyd，目录被占用换不掉 → 直接装进 target
                if not os.path.isdir(target) and os.path.isdir(old):
                    os.replace(old, target)
                shutil.rmtree(stage, ignore_errors=True)
                if fresh:                           # 整套换装不能就地叠装（旧 torch 的 DLL 会残留）
                    raise RuntimeError("%s 正被别的进程占用，换不掉。关掉正在跑超分/用 torch 的程序后重跑："
                                       "python bootstrap.py --sr" % target)
                cmd2 = [c if c != stage else target for c in cmd]
                r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=timeout,
                                    env=dict(os.environ, PIP_NO_INPUT="1"))
                if r2.returncode:
                    errs.append("%s → 就地安装失败" % (idx or "默认源"))
                    continue
            shutil.rmtree(old, ignore_errors=True)
            return True
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
        errs.append("%s → %s" % (idx or "默认源", " | ".join(tail)))
    shutil.rmtree(stage, ignore_errors=True)
    raise RuntimeError("依赖安装失败（已试 %d 个下载源）：\n  %s\n可设 PDF_ZH_PIP_INDEX 指向可用的 pip 源后重试。"
                       % (len(idx_list), "\n  ".join(errs)))


# ---------------------------------------------------------------- 核心依赖
def ensure(install=True, quiet=False):
    """入口脚本第一行调用：挂上私有依赖目录；缺包就自动装（幂等，已就绪时毫秒级返回）。"""
    if "core" in _DONE:
        return True
    log = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr, flush=True))
    sd = site_dir("core")
    _activate(sd)
    _activate(site_dir("sr"))
    missing = [pkg for names, pkg in CORE if not _have(names)]
    if missing and install and str(cfg("no_autoinstall", "0")) != "1":
        log("  [bootstrap] 首次运行，自动安装缺少的依赖到 %s …" % sd)
        with _Lock(os.path.join(cache_dir(), "pydeps.lock")):
            missing = [pkg for names, pkg in CORE if not _have(names)]   # 等锁期间别人可能装好了
            if missing:
                pip_install(missing, sd, log=log)
        _activate(sd)
        still = [pkg for names, pkg in CORE if not _have(names)]
        if still:
            raise RuntimeError("依赖安装后仍缺：%s" % ", ".join(still))
        log("  [bootstrap] 依赖就绪")
    _compat_pymupdf()
    _DONE.add("core")
    return not missing or install


def _compat_pymupdf():
    """旧版 PyMuPDF 的 API 补丁：只补缺的，新版上什么都不做。

    Python 3.9 最高只能装到 PyMuPDF 1.26.x（1.27 起要求 3.10+），它的 Rect/IRect 没有
    `get_area()` —— 引擎各处都在用。macOS 自带的 /usr/bin/python3 就是 3.9。
    """
    try:
        import pymupdf as fz
    except ImportError:
        try:
            import fitz as fz
        except ImportError:
            return

    def get_area(self, *args):             # 与 PyMuPDF 1.27 的 _rect_area 同义
        unit = args[0] if args else "px"
        u = {"px": (1, 1), "in": (1.0, 72.0), "cm": (2.54, 72.0), "mm": (25.4, 72.0)}
        return (u[unit][0] / u[unit][1]) ** 2 * self.width * self.height
    for cls in (getattr(fz, "Rect", None), getattr(fz, "IRect", None)):
        if cls is not None and not hasattr(cls, "get_area"):
            cls.get_area = get_area


# ---------------------------------------------------------------- 中文字体
def _mac_fonts_pending(fontkit):
    """macOS：有苹方、但还没转成 TrueType（此时实际用的是华文黑体）。"""
    if sys.platform != "darwin" or "pingfang.ttc" not in fontkit._index():
        return False
    src = fontkit._SOURCE.get(("zh", True)) or ""
    if src.startswith(("环境变量", "技能 fonts/")):     # 用户自己指定了字体，不动
        return False
    return os.sep + "converted" + os.sep not in fontkit.find("zh", reportlab=True)


def ensure_fonts(log=None):
    """中文字体只有 CFF 版时，一次性转成 TrueType（之后走缓存）。

    · Linux：只有 Noto/思源 CJK（CFF）→ 转换（2~4 分钟）；
    · macOS：苹方是 CFF，不转就只能用华文黑体（° ′ ″ · 全角、粗体不明显）→ 转苹方 SC（约 30 秒）。
    在「开始一份文档」的入口（translate_pdf、build.py 的 _engine）调用，不在每个脚本的
    快速路径里调用。Windows、或已有可用 TrueType 中文字体时立即返回。
    `PDF_ZH_NO_AUTOFONTS=1` 可关掉。
    """
    if "fonts" in _DONE or str(cfg("no_autofonts", "0")) == "1":
        return
    _DONE.add("fonts")
    if not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        return
    log = log or (lambda *a: print(*a, file=sys.stderr, flush=True))
    sys.path.insert(0, HERE)
    try:
        import fontkit
        if sys.platform == "darwin":
            fontkit.find("zh", reportlab=True)
            if _mac_fonts_pending(fontkit):
                with _Lock(os.path.join(cache_dir(), "fonts.lock"), stale=1800):
                    log("  [bootstrap] 把系统苹方（CFF）转成 TrueType（约 30 秒，只做一次）…")
                    fontkit.convert_system_cjk(verbose=False)
            return
        r = fontkit.find("zh", reportlab=True)
        src = fontkit._SOURCE.get(("zh", True)) or ""
        if r != fontkit.find("zh-bold", reportlab=True) and "缺陷" not in src and "内置" not in src:
            return
        with _Lock(os.path.join(cache_dir(), "fonts.lock"), stale=1800):
            idx = fontkit._index()
            if not any(n in idx for n in ("notosanscjksc-regular.otf", "notosanssc-regular.otf",
                                          "sourcehansanssc-regular.otf", "notosanscjk-regular.ttc")):
                log("  [bootstrap] 本机没有中文字体，暂用 PyMuPDF 内置字体（无粗体）。"
                    "装系统字体可改善：sudo apt install fonts-noto-cjk，或设 PDF_ZH_FONT / PDF_ZH_FONT_BOLD")
                return
            log("  [bootstrap] 本机只有 CFF 版中文字体，一次性转成 TrueType（约 2~4 分钟，只做一次）…")
            fontkit.convert_system_cjk(verbose=False)
    except Exception as e:
        log("  [bootstrap] 字体自动转换跳过：%s" % e)


# ---------------------------------------------------------------- 插图超分
#
# torch 的 CUDA 轮子只带编译时列入的显卡架构（sm_XX）。装错版本时 torch.cuda.is_available()
# 照样是 True，到第一次真算才报「no kernel image is available for execution on the device」
# （例：算力 12.0 的显卡装了 arch 列表止于 sm_90 的 cu126 版）。所以全部按**本机实测**来定，不针对任何型号：
#   ① 本机：nvidia-smi 读显卡算力（compute_cap）与驱动支持的最高 CUDA 版本；Python 版本与平台标签；
#   ② 下载源：从 PyTorch 索引读出「有本机 Python+平台轮子」的 cuXXX 标签（缓存 1 天；联网失败用内置表）；
#   ③ 过滤：不超过驱动版本；按算力代际排除明知不支持的（见 CC_RULES）；新的在前；
#   ④ 装完在子进程里实跑一次卷积，过了才换上 —— 这一步是最终裁决，前面只是少下几个 2.5 GB；
#   ⑤ 已装的 torch 也做同样体检（结果缓存，torch/显卡/驱动不变就不重查），不合格自动换装。
CUDA_TAGS = ["cu134", "cu132", "cu130", "cu129", "cu128", "cu126", "cu124", "cu121", "cu118"]   # 联网失败时的兜底表
# 算力代际 → CUDA 版本区间（PyTorch 官方轮子的实际情况）。只用来少试几个；新算力不在表里时不设限，交给实跑体检。
#   (算力下限, 算力上限(不含), 最低 CUDA, 最高 CUDA)
CC_RULES = [
    ((10, 0), None, (12, 8), None),      # 10.x/12.x 代：cu128 起才带 sm_100/sm_120
    ((7, 0), (7, 5), None, (12, 9)),     # 7.0 代：CUDA 13 起不再编译
    ((0, 0), (7, 0), None, (12, 6)),     # 7.0 以下：cu128 起不再编译
]
_GPU = []          # gpu_info() 的进程内缓存（[] = 还没查）
_SR_MARK = "sr_torch_check.json"
_IDX_CACHE = "torch_cuda_tags.json"

# 子进程体检：导入 torch、读架构列表、在显卡上真跑一次卷积（含 fp16 autocast，与 sr.py 推理一致）
_PROBE = r'''
import json, sys
r = {}
try:
    import torch
    r["version"] = torch.__version__
    r["cuda"] = torch.version.cuda
    r["file"] = torch.__file__
    r["avail"] = bool(torch.cuda.is_available())
    if r["avail"]:
        r["cc"] = list(torch.cuda.get_device_capability(0))
        r["name"] = torch.cuda.get_device_name(0)
        r["arch"] = list(torch.cuda.get_arch_list())
        x = torch.randn(1, 3, 32, 32, device="cuda")
        w = torch.randn(8, 3, 3, 3, device="cuda")
        y = torch.nn.functional.conv2d(x, w, padding=1)
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            y = y + torch.nn.functional.conv2d(x, w, padding=1).float()
        torch.cuda.synchronize()
        r["sum"] = float(y.sum())
        r["ok"] = True
    else:
        r["ok"] = False
except BaseException as e:
    r["ok"] = False
    r["err"] = (type(e).__name__ + ": " + str(e)).strip().splitlines()[0][:300]
print("@@PROBE" + json.dumps(r))
'''


def _smi():
    exe = shutil.which("nvidia-smi")
    if not exe and sys.platform.startswith("win"):
        cand = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        exe = cand if os.path.exists(cand) else None
    return exe


def gpu_info():
    """NVIDIA 显卡信息：{name, cc:(主,次), driver, cuda:(主,次)}；没有 NVIDIA 显卡返回 None。

    cc = 算力（compute capability，12.0 即 sm_120）；cuda = 驱动支持到的最高 CUDA 版本
    （nvidia-smi 表头的「CUDA Version」/ 新驱动的「CUDA UMD Version」）。老驱动查不到的字段缺省。
    """
    if _GPU:
        return _GPU[0]
    info = None
    exe = _smi()
    if exe:
        try:
            r = subprocess.run([exe, "--query-gpu=name,compute_cap,driver_version",
                                "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                f = [s.strip() for s in r.stdout.strip().splitlines()[0].split(",")]
                info = {"name": f[0]}
                m = re.match(r"(\d+)\.(\d+)", f[1] if len(f) > 1 else "")
                if m:
                    info["cc"] = (int(m.group(1)), int(m.group(2)))
                if len(f) > 2:
                    info["driver"] = f[2]
            elif subprocess.run([exe, "-L"], capture_output=True, timeout=15).returncode == 0:
                info = {"name": "NVIDIA GPU"}           # 老驱动不认 compute_cap 查询
            if info is not None:
                h = subprocess.run([exe], capture_output=True, text=True, timeout=15).stdout or ""
                m = re.search(r"CUDA (?:UMD )?Version:\s*(\d+)\.(\d+)", h)
                if m:
                    info["cuda"] = (int(m.group(1)), int(m.group(2)))
        except Exception:
            pass
    _GPU.append(info)
    return info


def _nvidia():
    return gpu_info() is not None


def _sm(cc):
    return "sm_%d%d" % tuple(cc) if cc else "?"


def _tag_ver(t):
    """cu134 → (13, 4)；cu118 → (11, 8)；cu75 → (7, 5)。"""
    d = t[2:]
    return (int(d[:-1]), int(d[-1]))


def _wheel_tags():
    """本机 pip 认的轮子标签：(cpXY, 平台正则)。平台按 PyTorch 轮子的命名（win_amd64 / manylinux_*_x86_64 …）。"""
    py = "cp%d%d" % sys.version_info[:2]
    m = platform.machine().lower()
    if sys.platform.startswith("win"):
        plat = r"win_arm64" if m in ("arm64", "aarch64") else r"win_amd64"
    elif sys.platform.startswith("linux"):
        plat = r"(?:many)?linux[_0-9]*_" + ("aarch64" if m in ("arm64", "aarch64") else "x86_64")
    else:
        plat = None                                # macOS 没有 CUDA 轮子
    return py, plat


def _http_get(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "pdf-translate-zh-bootstrap"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def available_cuda_tags(torch_idx=None, refresh=False):
    """下载源上「有本机 Python+平台 torch 轮子」的 CUDA 标签，新的在前。返回 (标签列表, 来源说明)。

    依次：缓存（1 天，同一下载源 + Python + 平台）→ 合并索引 <源>/torch/ → 根索引列出 cuXXX 目录后
    逐个读 <源>/cuXXX/torch/ → 内置 CUDA_TAGS（联网失败 / 自建镜像没有索引页时）。
    """
    torch_idx = torch_idx or cfg("torch_index") or "https://download.pytorch.org/whl/"
    if not torch_idx.endswith("/"):
        torch_idx += "/"
    py, plat = _wheel_tags()
    if not plat:
        return [], "本平台无 CUDA 轮子"
    key = "%s|%s|%s" % (torch_idx, py, plat)
    cp = os.path.join(cache_dir(), _IDX_CACHE)
    if not refresh:
        try:
            with open(cp, encoding="utf-8") as fh:
                c = json.load(fh)
            if c.get("key") == key and time.time() - c.get("t", 0) < 86400 and c.get("tags"):
                return c["tags"], "下载源索引（缓存 %s）" % time.strftime("%m-%d %H:%M", time.localtime(c["t"]))
        except Exception:
            pass
    pat = re.compile(r"torch-[0-9][^\s\"'<>/]*?\+(cu\d+)-%s-%s-%s\.whl" % (py, py, plat))
    tags, src = set(), ""
    try:
        tags = set(pat.findall(_http_get(torch_idx + "torch/")))
        src = "下载源合并索引 %storch/" % torch_idx
    except Exception:
        pass
    if not tags:
        try:
            dirs = sorted(set(re.findall(r"\b(cu\d{2,3})/?[\"'<\s]", _http_get(torch_idx))), key=_tag_ver, reverse=True)
            for t in dirs:
                try:
                    if pat.search(_http_get(torch_idx + t + "/torch/")):
                        tags.add(t)
                except Exception:
                    continue
            src = "下载源逐目录索引 %s" % torch_idx
        except Exception:
            pass
    if not tags:
        return list(CUDA_TAGS), "内置表（读不到下载源索引）"
    out = sorted(tags, key=_tag_ver, reverse=True)
    try:
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump({"key": key, "t": time.time(), "tags": out}, fh)
    except OSError:
        pass
    return out, src


def _cc_allows(cc, v):
    """CC_RULES：该算力是否可能被 CUDA 版本 v 的官方轮子支持。表里没有的情况一律放行（交给实跑体检）。"""
    for lo, hi, vmin, vmax in CC_RULES:
        if cc >= lo and (hi is None or cc < hi):
            return (vmin is None or v >= vmin) and (vmax is None or v <= vmax)
    return True


def cuda_tags(info, limit=3, avail=None):
    """按本机显卡算力与驱动、下载源实有的轮子挑 CUDA 标签，新的在前（最多 limit 个，免得一个个下 2.5 GB）。

    · 候选 = available_cuda_tags()（下载源上有本机 Python+平台轮子的）；
    · 不超过驱动支持的 CUDA 版本（否则 torch 认不到显卡）；驱动版本查不到时不设上限；
    · 按 CC_RULES 排除明知不支持本机算力的；全被排除时退回「只按驱动过滤」，仍交给实跑体检；
    · 查不到算力的老驱动 → 只按驱动过滤。
    config.json 的 torch_cuda（如 "cu130"）可钉死一个标签，排最前。
    """
    cc, drv = info.get("cc"), info.get("cuda")
    cand = list(avail) if avail is not None else available_cuda_tags()[0]
    by_drv = [t for t in cand if not drv or _tag_ver(t) <= tuple(drv)]
    out = [t for t in by_drv if not cc or _cc_allows(tuple(cc), _tag_ver(t))] or by_drv
    out = out[:limit]
    pin = cfg("torch_cuda")
    if pin:
        out = [pin] + [t for t in out if t != pin]
    return out


def _probe_env(path=None):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    if path:                                     # 只看 path 里的 torch（验证暂存目录用）
        env["PYTHONPATH"] = os.pathsep.join([path, site_dir("core")])
    return env


def torch_probe(path=None, timeout=900):
    """在子进程里体检 torch（不污染本进程；崩了也不连累调用方）。返回 dict，ok=True 表示显卡能真算。"""
    try:
        r = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=_probe_env(path))
    except subprocess.TimeoutExpired:
        return {"ok": False, "err": "体检超时"}
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("@@PROBE"):
            return json.loads(ln[7:])
    tail = ((r.stderr or r.stdout or "").strip().splitlines() or ["无输出"])[-1]
    return {"ok": False, "err": "体检进程异常退出（%s）：%s" % (r.returncode, tail[:300])}


def probe_reason(p, info=None):
    """把体检结果翻成一句人话。"""
    info = info or {}
    if p.get("ok"):
        return "torch %s（CUDA %s）在 %s 上运算正常" % (p.get("version"), p.get("cuda"), p.get("name"))
    if not p.get("version"):
        return "torch 导入失败：%s" % p.get("err", "?")
    if not p.get("cuda"):
        return "装的是 CPU 版 torch %s" % p["version"]
    if not p.get("avail"):
        drv = info.get("cuda")
        return "torch %s（CUDA %s 版）认不到显卡%s" % (
            p["version"], p["cuda"], "：驱动只支持到 CUDA %d.%d" % drv if drv else "（驱动太旧或显卡被占用）")
    sm = _sm(p.get("cc"))
    arch = p.get("arch") or []
    if sm not in arch:
        return "torch %s 不含本机显卡 %s（%s）的计算内核（它只带 %s）" % (
            p["version"], p.get("name"), sm, " ".join(arch) or "?")
    return "torch %s 在显卡上运算失败：%s" % (p["version"], p.get("err", "?"))


def _torch_loc():
    try:
        spec = importlib.util.find_spec("torch")
    except (ImportError, ValueError):
        return None
    return os.path.dirname(spec.origin) if spec and spec.origin else None


def _torch_ver(loc):
    try:
        with open(os.path.join(loc, "version.py"), encoding="utf-8") as fh:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", fh.read())
            return m.group(1) if m else "?"
    except OSError:
        return "?"


def _under(p, root):
    p, root = os.path.normcase(os.path.abspath(p)), os.path.normcase(os.path.abspath(root))
    return p == root or p.startswith(root + os.sep)


def _mark_key(info):
    loc = _torch_loc()
    if not loc:
        return None
    return "|".join([_torch_ver(loc), os.path.normcase(loc), info.get("name", ""),
                     _sm(info.get("cc")), info.get("driver", "")])


def _mark(key=None, **kv):
    """读（无 kv）/ 写体检缓存。"""
    p = os.path.join(cache_dir(), _SR_MARK)
    if not kv:
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    kv.update(key=key, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(kv, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return kv


def _verify_cuda(stage):
    p = torch_probe(stage)
    return bool(p.get("ok")), probe_reason(p, gpu_info())


def _install_torch_cuda(log):
    """按 sr_plan() 里的 CUDA 候选逐个整套换装进技能私有目录，装完验证能真算才换上。"""
    sd = site_dir("sr")
    for desc, args, pkgs, idx in sr_plan():
        if not _is_cuda_entry(idx):
            continue
        log("  [bootstrap] 换装 %s …" % desc)
        try:
            pip_install(pkgs, sd, extra_args=args, indexes=idx, log=log, timeout=7200,
                        fresh=True, verify=_verify_cuda)
        except Exception as e:
            log("  [bootstrap] %s 未成：%s" % (desc, str(e).splitlines()[0]))
            continue
        _activate(sd)
        return True
    return False


def check_torch(log=print, force=False):
    """体检已装的 torch 能否在本机 NVIDIA 显卡上真算；不能就自动换装（结果缓存）。

    返回 True = 显卡可用；False = 不可用（超分会退到 CPU）；None = 不适用（没有 NVIDIA 显卡 /
    没装 torch / 本进程已加载 torch —— 已加载的换不掉，运行时由 sr.pick_device 兜底退 CPU）。
    · 自动换装只动技能私有目录里的 torch；系统里用户自己装的 torch 只提示，不覆盖。
    · force=True（`bootstrap.py --sr`）：不看缓存、也给系统 torch 在私有目录装一份匹配的（优先加载）。
    · 换装失败会记下，torch / 显卡 / 驱动不变就不再重试（避免每次都下几 GB）。
    """
    info = gpu_info()
    if not info or "torch" in sys.modules:
        return None
    _activate(site_dir("sr"))
    key = _mark_key(info)
    if not key:
        return None
    m = _mark()
    auto = force or str(cfg("sr_autoinstall", "1")) != "0"
    if not force and m.get("key") == key:
        if m.get("ok"):
            return True
        if m.get("tried") or not auto:
            if "srwarn" not in _DONE:
                _DONE.add("srwarn")
                log("  [bootstrap] 提示：%s；超分走 CPU。修复：python bootstrap.py --sr" % m.get("why", ""))
            return False
    p = torch_probe()
    why = probe_reason(p, info)
    if p.get("ok"):
        _mark(key, ok=True, why=why)
        return True
    loc = _torch_loc()
    mine = _under(loc, site_dir("sr"))
    if not auto or not (mine or force):
        _mark(key, ok=False, tried=not mine, why=why)
        log("  [bootstrap] %s；超分改走 CPU（约慢 10 倍）。%s" % (why, (
            "要用显卡：python bootstrap.py --sr（在技能私有目录另装匹配的 CUDA 版，不动 %s）" % loc)
            if not mine else "要用显卡：python bootstrap.py --sr"))
        return False
    log("  [bootstrap] %s → 自动换装匹配本机显卡（%s，%s）的 torch，约 2.5 GB …"
        % (why, info.get("name"), _sm(info.get("cc"))))
    with _Lock(os.path.join(cache_dir(), "pydeps-sr.lock"), stale=7200):
        ok = _install_torch_cuda(log)
    importlib.invalidate_caches()
    if ok:
        p = torch_probe()
        why = probe_reason(p, info)
        ok = bool(p.get("ok"))
    _mark(_mark_key(info), ok=ok, tried=True, why=why)
    log("  [bootstrap] " + ("换装完成：" if ok else "换装未成功，超分走 CPU：") + why)
    return ok


def sr_plan():
    """本机该装哪种 torch：[(说明, pip 参数, 包列表, 下载源列表)]，按顺序尝试。"""
    torch_idx = cfg("torch_index") or "https://download.pytorch.org/whl/"
    if not torch_idx.endswith("/"):
        torch_idx += "/"
    plan = []
    # 配了 ONNX 模型来源（config.json 的 sr_onnx / sr_onnx_url）：先装 25 MB 的 onnxruntime 就够
    if cfg("sr_onnx") or cfg("sr_onnx_url"):
        plan.append(("onnxruntime（约 25 MB，配合已配置的 ONNX 模型）", [], ["onnxruntime"], None))
    info = None if sys.platform == "darwin" else gpu_info()
    if sys.platform == "darwin":
        plan.append(("torch（Apple 芯片走 MPS）", [], ["torch"], None))
    elif info:
        gpu = "%s，%s" % (info.get("name", "NVIDIA"), _sm(info.get("cc")))
        for i, t in enumerate(cuda_tags(info)):
            plan.append(("torch CUDA %s.%s 版（%s%s）" % (t[2:-1], t[-1], gpu, "，约 2.5 GB" if i == 0 else ""),
                         [], ["torch"], [torch_idx + t]))
        plan.append(("torch（PyPI / 国内镜像；Windows 上是 CPU 版）", [], ["torch"], None))
    else:
        plan += [("torch CPU 版（约 200 MB）", [], ["torch"], [torch_idx + "cpu"]),
                 ("torch（PyPI / 国内镜像%s）" % ("，Linux 版含 CUDA 库约 2 GB"
                                              if sys.platform.startswith("linux") else ""),
                  [], ["torch"], None)]
    return plan


def ensure_sr(log=print):
    """保证有一个真超分后端（torch 或 onnxruntime+模型）。成功返回 True；关掉自动安装或全部失败返回 False。"""
    ensure(quiet=True)
    _activate(site_dir("sr"))
    if _have(["torch"]):
        try:
            check_torch(log)                     # 装了但缺本机显卡的计算内核 → 自动换装
        except Exception as e:
            log("  [bootstrap] torch 显卡体检跳过：%s" % e)
        return True
    if str(cfg("sr_autoinstall", "1")) == "0":
        return False
    sd = site_dir("sr")
    with _Lock(os.path.join(cache_dir(), "pydeps-sr.lock"), stale=7200):
        if _have(["torch"]):
            return True
        for desc, args, pkgs, idx in sr_plan():
            log("  [bootstrap] 自动安装插图超分后端：%s …" % desc)
            cuda = _is_cuda_entry(idx)
            try:
                pip_install(pkgs, sd, extra_args=args, indexes=idx, log=log, timeout=7200,
                            fresh=cuda, verify=_verify_cuda if cuda else None)
            except Exception as e:
                log("  [bootstrap] %s 未装成：%s" % (desc, str(e).splitlines()[0]))
                continue
            _activate(sd)
            if _have(["torch"]):
                if cuda:
                    _mark(_mark_key(gpu_info()), ok=True, why="安装时已验证")
                return True
            if _have(["onnxruntime"]) and "onnxruntime" in pkgs:
                return True
    return False


def _is_cuda_entry(idx):
    return bool(idx) and re.search(r"/cu\d+/?$", idx[0] or "") is not None


# ---------------------------------------------------------------- 一次配齐
def setup(with_sr=False, check_only=False):
    print("pdf-translate-zh 环境自动配置   Python %s  %s  %s" % (
        platform.python_version(), sys.platform, platform.machine()))
    if sys.version_info < (3, 9):
        print("  FAIL Python 版本过低（需 ≥ 3.9）。Windows: winget install Python.Python.3.12；"
              "macOS: xcode-select --install 或 brew install python")
        return 1
    ok = ensure(install=not check_only)
    missing = [pkg for names, pkg in CORE if not _have(names)]
    print("  依赖：" + ("齐全" if not missing else "缺 %s" % ", ".join(missing)))
    if missing:
        return 1
    sys.path.insert(0, HERE)
    import fontkit
    # 中文字体：Linux 常见只有 Noto CJK（CFF），重排路线没有粗体、叠印路线文本层不可检索 → 一次性转换
    src = ""
    try:
        fontkit.find("zh", reportlab=True)
        src = fontkit._SOURCE.get(("zh", True)) or ""
        same = fontkit.find("zh", reportlab=True) == fontkit.find("zh-bold", reportlab=True)
    except Exception:
        same = True
    if (same or "缺陷" in src or "内置" in src or _mac_fonts_pending(fontkit)) and not check_only:
        res = fontkit.convert_system_cjk()
        if any(st in ("已转换", "已更新别名映射") for _r, _d, st in res):
            print("  字体：已把本机 %s 转成 TrueType（一次性，已缓存）"
                  % ("苹方 SC" if sys.platform == "darwin" else "Noto/思源 CJK"))
    for role in ("zh", "zh-bold"):
        p = fontkit.find(role, reportlab=True)
        print("  字体 %-7s → %s  [%s]" % (role, os.path.basename(p), fontkit._SOURCE.get((role, True))))
    gi = gpu_info()
    if gi:
        print("  显卡：%s  算力 %s（%s）  驱动 %s，支持到 CUDA %s" % (
            gi.get("name"), "%d.%d" % gi["cc"] if gi.get("cc") else "?", _sm(gi.get("cc")),
            gi.get("driver", "?"), "%d.%d" % gi["cuda"] if gi.get("cuda") else "?"))
        if _have(["torch"]) and (with_sr or check_only):
            if check_only:
                print("  torch 体检：" + probe_reason(torch_probe(), gi))
            else:
                check_torch(log=print, force=True)
    if with_sr and not check_only:
        if ensure_sr():
            try:
                import sr
                print("  超分：", sr.available()[1])
                if sr.available()[0] == "torch":
                    print("  权重：", sr.ensure_weights())
            except Exception as e:
                print("  超分：后端已装，权重未就绪 —— %s" % e)
        else:
            print("  超分：未装成（将用 Lanczos 兜底，不影响其余流程）")
    rc = subprocess.call([sys.executable, os.path.join(HERE, "selftest.py")],
                         env=dict(os.environ, PYTHONUTF8="1"), stdout=subprocess.DEVNULL)
    print("  引擎自检：" + ("通过" if rc == 0 else "未通过（python3 selftest.py 看明细）"))
    state = dict(python=sys.executable, version=platform.python_version(), tag=_tag(),
                 core=site_dir("core"), sr=site_dir("sr"), selftest=rc == 0,
                 time=time.strftime("%Y-%m-%d %H:%M:%S"))
    with open(os.path.join(cache_dir(), "env.json"), "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    print("  结论：" + ("可以开工" if rc == 0 else "有问题，见上"))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    if "-h" in a or "--help" in a:
        print(__doc__)
        sys.exit(0)
    sys.exit(setup(with_sr="--sr" in a, check_only="--check" in a))
