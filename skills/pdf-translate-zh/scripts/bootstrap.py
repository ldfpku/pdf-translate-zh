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

本文件只用标准库 —— 它要在任何依赖都还没装的机器上先跑起来。
"""
import importlib
import importlib.util
import json
import os
import platform
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


def pip_install(pkgs, target, extra_args=(), indexes=None, log=print, timeout=1800):
    """装进 target（先装暂存目录，成功后整体替换）。依次尝试多个下载源。"""
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
        if os.path.isdir(target):                   # 已有的包带过去，只补缺的
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
def _nvidia():
    exe = shutil.which("nvidia-smi")
    if not exe and sys.platform.startswith("win"):
        cand = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        exe = cand if os.path.exists(cand) else None
    if not exe:
        return False
    try:
        return subprocess.run([exe, "-L"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


def sr_plan():
    """本机该装哪种 torch：[(说明, pip 参数, 包列表, 下载源列表)]，按顺序尝试。"""
    torch_idx = cfg("torch_index") or "https://download.pytorch.org/whl/"
    if not torch_idx.endswith("/"):
        torch_idx += "/"
    plan = []
    # 配了 ONNX 模型来源（config.json 的 sr_onnx / sr_onnx_url）：先装 25 MB 的 onnxruntime 就够
    if cfg("sr_onnx") or cfg("sr_onnx_url"):
        plan.append(("onnxruntime（约 25 MB，配合已配置的 ONNX 模型）", [], ["onnxruntime"], None))
    if sys.platform == "darwin":
        plan.append(("torch（Apple 芯片走 MPS）", [], ["torch"], None))
    elif _nvidia():
        plan += [("torch CUDA 12.8 版（NVIDIA 显卡，约 2.5 GB）", [], ["torch"], [torch_idx + "cu128"]),
                 ("torch CUDA 12.6 版", [], ["torch"], [torch_idx + "cu126"]),
                 ("torch（PyPI / 国内镜像）", [], ["torch"], None)]
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
        return True
    if str(cfg("sr_autoinstall", "1")) == "0":
        return False
    sd = site_dir("sr")
    with _Lock(os.path.join(cache_dir(), "pydeps-sr.lock"), stale=7200):
        if _have(["torch"]):
            return True
        for desc, args, pkgs, idx in sr_plan():
            log("  [bootstrap] 自动安装插图超分后端：%s …" % desc)
            try:
                pip_install(pkgs, sd, extra_args=args, indexes=idx, log=log, timeout=7200)
            except Exception as e:
                log("  [bootstrap] %s 未装成：%s" % (desc, str(e).splitlines()[0]))
                continue
            _activate(sd)
            if _have(["torch"]):
                return True
            if _have(["onnxruntime"]) and "onnxruntime" in pkgs:
                return True
    return False


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
