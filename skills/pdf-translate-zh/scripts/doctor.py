# -*- coding: utf-8 -*-
"""环境自检：换一台电脑先跑这个（约 5 秒；加 --selftest 再跑一遍引擎冒烟）。

    python doctor.py [--selftest] [--install] [--fonts] [--sr] [--fix]

--fix     全自动修复：等同 `bootstrap.py --sr`（装依赖、转字体、装超分后端、下权重、跑自检）。
          平时不需要：入口脚本会自动调用 bootstrap。

（macOS / Linux 用 python3；Windows 用 py 或 python。）

逐项报 OK / WARN / FAIL，并给出修复命令：
  · Python ≥ 3.9；必需包 PyMuPDF、reportlab、Pillow、numpy、fontTools；
    可选包 scipy（件号气泡）、torch（插图超分）
  · 中文字体：PyMuPDF 用 / ReportLab 用各自解析到哪个文件，缺粗体、缺常用符号时提醒
  · 缓存目录可写；插图超分将用哪个后端（torch / onnxruntime / Lanczos 兜底）与权重是否就位
--install 会用当前解释器 pip 安装缺失的**必需**包（不装 torch —— 体积大，按需自行装）。
--sr      预先下载并校验超分权重（67 MB，多个下载源依次尝试；PDF_ZH_SR_URL 可指定自己的镜像）
--fonts   把本机的 Noto/思源 CJK（CFF）简体常规+粗体转成 TrueType 存进用户缓存
          （共约 2~4 分钟，只做一次）：Linux 上常见只有 CFF 版，不转则重排路线没有粗体、
          叠印路线文本层图号不可检索且成品不能子集化。
返回码：有 FAIL 为 1，否则 0。
"""
import importlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)

REQUIRED = [("pymupdf", "PyMuPDF", "fitz"), ("reportlab", "reportlab", None),
            ("PIL", "Pillow", None), ("numpy", "numpy", None),
            ("fontTools", "fonttools", None)]
OPTIONAL = [("scipy", "scipy", "件号气泡 bubbles.py / 部分图内检测")]


def torch_hint():
    """按平台给出最合适的超分依赖安装建议。"""
    py = f'"{sys.executable}" -m pip install'
    if sys.platform == "darwin":
        return (f"{py} torch   （Apple 芯片自动用 MPS 加速；装不了 torch 时：{py} onnxruntime，"
                "再从有 torch 的机器 `sr.py --export-onnx` 拷一个 ONNX 模型过来）")
    if sys.platform.startswith("win"):
        return ("有 NVIDIA 显卡：按 https://pytorch.org 选择器给的命令装 CUDA 版 torch（约 2.5 GB）；"
                f"没有：{py} onnxruntime（约 25 MB）+ 拷 ONNX 模型，或 {py} torch --index-url "
                "https://download.pytorch.org/whl/cpu（约 200 MB）")
    return (f"{py} torch --index-url https://download.pytorch.org/whl/cpu（约 200 MB；有 NVIDIA 显卡去掉 "
            f"--index-url 装 CUDA 版）；或 {py} onnxruntime + 拷 ONNX 模型")

_status = {"FAIL": 0, "WARN": 0}


def say(level, msg, fix=None):
    if level in _status:
        _status[level] += 1
    print(f"  {level:<4} {msg}")
    if fix:
        print(f"       → {fix}")


def _import(mod, alt=None):
    try:
        return importlib.import_module(mod)
    except Exception:
        if alt:
            try:
                return importlib.import_module(alt)
            except Exception:
                return None
        return None


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    if "--fix" in argv:
        import bootstrap
        return bootstrap.setup(with_sr=True)
    try:
        import bootstrap
        bootstrap.ensure(install="--install" in argv, quiet=True)   # 只挂上私有依赖目录
    except Exception as e:
        print(f"  [bootstrap] {e}")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    pip = f'"{sys.executable}" -m pip install'
    print(f"pdf-translate-zh 环境自检   Python {sys.version.split()[0]}  ({sys.platform})")
    print(f"  技能脚本目录：{HERE}\n")

    print("[1] Python 与依赖包")
    if sys.version_info < (3, 9):
        say("FAIL", "Python 版本过低（需 ≥ 3.9）", "安装 Python 3.10+")
    else:
        say("OK", f"Python {sys.version.split()[0]}")
    missing = []
    for mod, pkg, alt in REQUIRED:
        m = _import(mod, alt)
        if m is None:
            missing.append(pkg)
            say("FAIL", f"缺少 {pkg}", f"{pip} {pkg}")
        else:
            say("OK", f"{pkg} {getattr(m, '__version__', getattr(m, 'VersionBind', ''))}")
    if missing and "--install" in argv:
        print(f"  … 安装 {' '.join(missing)}")
        r = subprocess.run([sys.executable, "-m", "pip", "install", *missing],
                           capture_output=True, text=True)
        print((r.stdout or "")[-800:])
        if r.returncode:
            err = (r.stderr or "")
            print(err[-800:])
            if "externally-managed" in err or "externally managed" in err:
                # macOS Homebrew / 新版 Debian·Ubuntu 的系统 Python 禁止直接 pip（PEP 668）
                venv = os.path.join(os.path.expanduser("~"), ".venvs", "pdf-translate-zh")
                pyv = os.path.join(venv, "Scripts" if sys.platform.startswith("win") else "bin", "python")
                req = os.path.join(HERE, "requirements.txt")
                print("  这台机器的系统 Python 不允许直接 pip 安装（PEP 668）。建一个专用虚拟环境：\n"
                      f"    {sys.executable} -m venv {venv}\n"
                      f"    {pyv} -m pip install -r {req}\n"
                      f"  之后一律用 {pyv} 运行本技能的脚本。")
            return 1
    for mod, pkg, why in OPTIONAL:
        m = _import(mod)
        if m is None:
            say("WARN", f"未装 {pkg}（可选：{why}）", f"{pip} {pkg}")
        elif mod == "torch":
            dev = "CPU"
            try:
                if m.cuda.is_available():
                    dev = "CUDA " + m.cuda.get_device_name(0)
                elif getattr(m.backends, "mps", None) and m.backends.mps.is_available():
                    dev = "Apple MPS"
            except Exception:
                pass
            say("OK", f"torch {m.__version__}（超分设备：{dev}）")
        else:
            say("OK", f"{pkg} {getattr(m, '__version__', '')}")
    fz = _import("pymupdf", "fitz")
    if fz is not None and _import("pymupdf") is None:
        say("WARN", "只有旧名 `fitz` 可用（PyMuPDF < 1.24.3）", f"{pip} -U PyMuPDF")
    if _status["FAIL"]:
        print("\n必需包未装齐，先按上面的命令安装再重跑。")
        return 1

    print("\n[2] 中文字体（fontkit：环境变量 → 技能 fonts/ → 转换缓存 → 系统 → 内置兜底）")
    import fontkit
    if "--fonts" in argv:
        for role, dst, st in fontkit.convert_system_cjk():
            print(f"  … {role}: {st} {dst or ''}")
    rep = fontkit.report()
    for role in ("zh", "zh-bold"):
        for rl, who in ((False, "PyMuPDF 叠印"), (True, "ReportLab 重排")):
            p, src = rep[(role, rl)]
            lvl = "OK"
            fix = None
            if p is None:
                lvl, fix = "FAIL", f"设环境变量 {fontkit._ENV[role]} 或把字体放进 {os.path.join(fontkit.SKILL_ROOT, 'fonts')}"
            elif "内置" in (src or "") or "退回" in (src or "") or "缺陷" in (src or ""):
                lvl = "WARN"
                fix = ("可用但非最佳：先试 `python doctor.py --fonts`（把本机 Noto CJK 转成 TrueType）；"
                       "或设环境变量 PDF_ZH_FONT / PDF_ZH_FONT_BOLD 指向微软雅黑/思源黑体 TTF；"
                       "技能目录可写时也可把字体放进技能 fonts/")
            say(lvl, f"{role:<8} {who:<11} {os.path.basename(str(p))}  [{src}]", fix)
    for role in ("latin-bold", "mono"):
        p, src = rep[(role, False)]
        say("OK" if p else "WARN", f"{role:<8} {os.path.basename(str(p)) if p else '无（退回 PIL 内置字体）'}")
    zr, zb = rep[("zh", True)][0], rep[("zh-bold", True)][0]
    if zr and zr == zb:
        say("WARN", "ReportLab 的中文粗体与常规体是同一个文件 —— 标题不会显示为粗体",
            "`python doctor.py --fonts`，或设 PDF_ZH_FONT_BOLD 指向 TrueType 中文粗体（如 msyhbd.ttc）")
    print("  提示：各机器字体不同，排版度量会略有差异；要逐字节一致，把同一套字体放进技能 fonts/。")

    print("\n[3] 缓存与插图超分")
    try:
        d = fontkit.cache_dir()
        probe = os.path.join(d, ".write_test")
        open(probe, "w").close()
        os.remove(probe)
        say("OK", f"缓存目录可写：{d}")
    except Exception as e:
        say("FAIL", f"缓存目录不可写：{e}", "设环境变量 PDF_ZH_CACHE 指向可写目录")
    try:
        import sr
        backend, info = sr.available()
        if backend == "lanczos":
            say("WARN", f"插图超分：{info}（只影响 < 150 dpi 的位图，其余流程不受影响）", torch_hint())
        else:
            say("OK", f"插图超分后端：{info}")
        if backend == "torch":
            w = sr.default_weights()
            if "--sr" in argv and not os.path.exists(w):
                try:
                    w = sr.ensure_weights()
                except Exception as e:
                    say("FAIL", str(e).splitlines()[0], "设 PDF_ZH_SR_URL 指向可用镜像，或手动放置权重")
            if os.path.exists(w):
                say("OK", f"超分权重就位：{w}")
            else:
                say("WARN", "超分权重未下载（首次超分时自动下载 67 MB；预先准备：doctor.py --sr）",
                    f"离线机器：把 RealESRGAN_x4plus.pth 放到 {w}，或设 PDF_ZH_SR_WEIGHTS")
    except Exception as e:
        say("WARN", f"未能检查插图超分：{e}")

    if "--selftest" in argv:
        print("\n[4] 引擎冒烟自检")
        rc = subprocess.call([sys.executable, os.path.join(HERE, "selftest.py")],
                             env=dict(os.environ, PYTHONUTF8="1"))
        if rc:
            say("FAIL", "selftest.py 未通过（见上方明细）")
        else:
            say("OK", "selftest.py 通过")

    print(f"\n结论：FAIL {_status['FAIL']}  WARN {_status['WARN']}  "
          + ("—— 可以开工" if not _status["FAIL"] else "—— 先修 FAIL 项"))
    return 1 if _status["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
