# -*- coding: utf-8 -*-
"""粗框 → 墨迹框 → 生成 raster_zh_pNN.py，并画框出图目检。

用法： python genraster.py <0基页号> <rough模块名> <源PDF> <输出目录>
rough 模块须提供 ROUGH = [(x0,y0,x1,y1,中文,转角), …]，从当前目录或输出目录导入。

**必须拿源 PDF 量** —— 成品页上已铺白底写了中文，再量到的是中文自己。
"""
import os as _os, sys as _sys  # noqa: E401
_sys.dont_write_bytecode = True   # 不往（可能只读的）技能目录写 __pycache__
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import bootstrap as _bs  # noqa: E402
_bs.ensure()  # 首次运行自动安装缺少的依赖（已就绪时毫秒级返回）

import importlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import pymupdf as fitz
except ImportError:
    import fitz
import vectext       # noqa: E402

if len(sys.argv) < 5:
    sys.exit(__doc__)
PG = int(sys.argv[1])
ROUGH_MOD = sys.argv[2]
SRC, OUTDIR = sys.argv[3], sys.argv[4]
sys.path[:0] = [os.getcwd(), OUTDIR]
rm = importlib.import_module(ROUGH_MOD)
importlib.reload(rm)

d = fitz.open(SRC)
pg = d[PG]

L = ["ITEMS = ["]
bad = []
for x0, y0, x1, y1, zh, rot in rm.ROUGH:
    b = vectext.inkbox(pg, fitz.Rect(x0, y0, x1, y1))
    if b is None:
        bad.append(zh)
        continue
    segs = zh.split(chr(10))
    expr = " + chr(10) + ".join('"%s"' % t for t in segs)
    L.append('    ((%.1f, %.1f, %.1f, %.1f), %s%s),'
             % (b.x0, b.y0, b.x1, b.y1, expr,
                ", None, None, 90" if rot else ""))
    pg.draw_rect(b, color=(1, 0, 0), width=0.4)
L.append("]")

HDR = ('# -*- coding: utf-8 -*-' + chr(10)
       + '"""\u7b2c %d \u9875\u56fe\u5185\u70e7\u6b7b\u82f1\u6587\u7684\u4e2d\u6587\u56de\u53e0\u3002' % (PG + 1)
       + chr(10) + chr(10)
       + '\u63d2\u56fe\u662f\u5d4c\u5165\u4f4d\u56fe\uff0c\u6807\u6ce8\u70e7\u5728\u50cf\u7d20\u91cc \u2014\u2014 \u6587\u672c\u5c42\u91cc\u6ca1\u6709\u5b83\u4eec\uff0c'
       + '\u65e2\u63d0\u53d6\u4e0d\u5230\u4e5f\u62b9\u4e0d\u6389\uff08SKILL \u907f\u5751 \u3221\uff09\u3002' + chr(10)
       + '\u5750\u6807\uff1a\u6e32\u67d3**\u6e90\u56fe**\u8bfb\u7c97\u6846 \u2192 `vectext.inkbox()` \u53d6\u7c97\u6846\u5185\u5168\u90e8\u6df1\u50cf\u7d20\u7684\u5305\u56f4\u76d2\u3002'
       + chr(10)
       + '\u5b9a\u5b8c\u6846\u753b\u6846\u51fa\u56fe\u76ee\u68c0\u8fc7\u4e00\u6b21\u3002\u4ee3\u53f7\u3001\u5c3a\u5bf8\u503c\u4e0e\u5546\u6807\u4fdd\u7559\u4e0d\u8bd1\uff08SKILL \u00a73\uff09\u3002"""'
       + chr(10) + chr(10)
       + '# (\u58a8\u8ff9\u6846, \u4e2d\u6587[, \u5e95\u8272, \u5b57\u8272, \u8f6c\u89d2])' + chr(10))

out = os.path.join(OUTDIR, "raster_zh_p%d.py" % (PG + 1))
io.open(out, "w", encoding="utf-8").write(HDR + chr(10).join(L) + chr(10))
pg.get_pixmap(dpi=140).save(os.path.join(OUTDIR, "chk%d.png" % (PG + 1)))
print("p%d  %d 条，未取到 %s" % (PG + 1, len(rm.ROUGH) - len(bad), bad))
