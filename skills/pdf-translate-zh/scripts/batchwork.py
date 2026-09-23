# -*- coding: utf-8 -*-
"""分批翻译的低开销回路。

为什么需要它：逐批推进时，真正吃掉上下文的不是译文本身，而是
  ① 把待译键**打印到控制台**（一批几十条、每条上千字符）；
  ② 每次 `Edit` 大词表文件后，工具会把**整份文件回显**；
  ③ 每批都重复输出进度叙述。

对策三条，本模块负责前两条：
  · `dump()` 把待译键写**文件**，调用方只 `Read` 需要的那几行；
  · 每批译文写成**独立模块** `<stem>_bNN.py`，`load()` 自动全部加载 ——
    永不重读大文件，也就永不被回显；
  · `stat()` 只回一行。

用法（每批三步，各一次工具调用）：
    python -c "import batchwork as B; B.dump(SRC, KEYDIR, mods)"   # 导出
    Read  KEYDIR/pending.txt  offset=N limit=M                     # 只读一片
    Write <stem>_bNN.py  →  python -c "...B.stat(...)"             # 落盘并计数
"""
import glob
import importlib
import os
import re
import sys

# 两条子规则都**必须加尾锚 `$`**，否则前缀匹配会当成整串匹配、静默吞掉正文：
#   · 代号规则若写成 `^[A-Z0-9\-]{2,}$` 而不要求含数字 → 吞掉全部全大写单词
#     （实测 手册 C 漏 398 键，`CUSTOMER`／`LENGTH`／`RELINE`…）
#   · 分数规则若写成 `^\d+/\d+` 而无 `$` → 吞掉凡以分数开头的**整行**
#     （实测 规范 F p33/p34 两行判据文字全漏）
# 两次都表现为「未命中 0 + 覆盖率 100%」，因为漏掉的串从未被当作待译单元。
# 本表必须与各文档 build.py 的 KEEP_RE **保持一致** —— 判据不同，
# 测出来的复用率与覆盖率都是假的。
KEEP = re.compile(r"^[\s\d.,;:/()\[\]+\-–—°'\"×x#%&*…]*$"
                  r"|^(?=[A-Z0-9\-]*\d)[A-Z0-9\-]{2,}$|^\d+/\d+$")


def _units(src, drop_font=None):
    try:
        import pymupdf as fitz   # PyMuPDF ≥ 1.24.3 的正式名；fitz 别名将被移除
    except ImportError:
        import fitz
    import hybrid_overlay as hy
    d = fitz.open(src)
    out = {}
    for i, pg in enumerate(d, 1):
        for r, t, s, k in hy.units_of(pg, drop_font=drop_font):
            if KEEP.match(t) or not re.search(r"[A-Za-z]{2,}", t):
                continue
            out.setdefault(t, i)
    d.close()
    return out


def load(cdir, stem):
    """加载 <stem>_dict.py 与全部 <stem>_bNN.py，返回 lookup 函数。"""
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    mods = []
    base = os.path.join(cdir, f"{stem}_dict.py")
    if os.path.exists(base):
        mods.append(importlib.import_module(f"{stem}_dict"))
    for p in sorted(glob.glob(os.path.join(cdir, f"{stem}_b*.py"))):
        mods.append(importlib.import_module(
            os.path.splitext(os.path.basename(p))[0]))

    def lookup(t):
        for m in mods:
            v = m.lookup(t)
            if v is not None:
                return v
        return None
    return lookup


def dump(src, cdir, stem, out=None, drop_font=None, maxlen=None,
         longest=False):
    """把未命中的键写文件，一行一条。返回统计一行。

    `longest=True` 时按**长度降序**排 —— 逐批推进时应优先译长段：
    覆盖率按条计，而字符数才是真工作量。实测 手册 I 一批长段推进 4.3 个
    百分点却砍掉 14.1K 字符，而一批短条目只砍 1.5K。
    """
    look = load(cdir, stem)
    u = _units(src, drop_font)
    miss = {t: p for t, p in u.items() if look(t) is None}
    hit = len(u) - len(miss)
    if longest:
        ks = sorted(miss, key=lambda k: -len(k))
    else:
        ks = sorted(miss, key=lambda k: (miss[k], len(k)))
    if maxlen:
        ks = [k for k in ks if len(k) <= maxlen]
    out = out or os.path.join(cdir, "pending.txt")
    with open(out, "w", encoding="utf-8") as f:
        for k in ks:
            f.write(k.replace("\n", " ") + "\n")
    pct = 100.0 * hit / max(len(u), 1)
    return (f"{pct:.1f}%  hit {hit}  miss {len(miss)} / "
            f"{sum(len(t) for t in miss):,} chars  -> {os.path.basename(out)}"
            f" ({len(ks)} lines)")


def stat(src, cdir, stem, drop_font=None):
    """只回一行命中率。"""
    look = load(cdir, stem)
    u = _units(src, drop_font)
    miss = [t for t in u if look(t) is None]
    hit = len(u) - len(miss)
    return (f"{100.0*hit/max(len(u),1):.1f}%  miss {len(miss)} / "
            f"{sum(len(t) for t in miss):,} chars")


def dupes(cdir, stem):
    """跨批次模块的**重复键**检查。

    分批模块按文件名顺序加载、**先命中者胜**，故同一键出现在两个模块里时
    后写的那份静默失效 —— 实测 手册 A 把某扭矩串的译文改在 b12，
    而 b10 里还留着旧译文，结果改了半天没效果、还以为是别的原因。

    返回 [(键, [模块名, ...]), ...]，只列出出现在 2 个及以上模块中的键。
    """
    import glob as _g
    seen = {}
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    files = ([os.path.join(cdir, f"{stem}_dict.py")]
             + sorted(_g.glob(os.path.join(cdir, f"{stem}_b*.py"))))
    for p in files:
        if not os.path.exists(p):
            continue
        name = os.path.splitext(os.path.basename(p))[0]
        m = importlib.import_module(name)
        for k in getattr(m, "D", {}):
            seen.setdefault(k, []).append(name)
    return [(k, v) for k, v in seen.items() if len(v) > 1]
