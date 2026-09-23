# -*- coding: utf-8 -*-
"""标准构建驱动：每份文档的 build.py 只填 Job 配置，流程与闸门在这里。

两种模式（Job.flow）：
  · flow=True   R 级语义重排（V2 默认）：pages = 章的块列表，流式排版，
                页数由内容决定；以「内容对账」与「页数预算」代替逐页 1 页判据。
  · flow=False  P/H 级 1:1 同源：pages = 逐源页块列表，每逻辑页必须实排 1 页。

流程固定为四道关：
  1. 素材层自检   术语覆盖 / 图内标注覆盖 / 图片引用完整 / 插图来源核验
  2. 构建前自检   （1:1）逐页装配，每逻辑页单独实排必须 1 页
  3. 构建         两趟构建定附录标签；硬闸门断言物理页数
  4. 成品自检     版心外杂物 / 正文压页脚 / 页码标签与序列 / 残留英文与半角标点 /
                  避头尾 / 缺字 /（flow）内容对账 + 页数预算
任一关不过即返回 False，并把明细打印出来。
"""
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dataclasses import replace

import checks
from zhlib import styles, register_fonts
from builder import Geom, LETTER, Masthead, Footer, build_2pass, fit_check
from appendix import errata, glossary


def effective_geom(geom, decors):
    """把 Decor 的**实测**占位换算回 Geom，供成品自检使用。

    否则 check_footer 会拿 Geom 里过时的 foot_top 去扫，扫到签署块内部，
    报出「正文压页脚」的假阳性 —— 装饰件一旦让出比 geom.mb 更多的净空，
    两者就必须同步。测量而非写死，正是本引擎的既定原则。
    """
    top = geom.mast_top
    foot_top, foot_gap = geom.foot_top, geom.foot_gap
    for d in decors or ():
        if d.y_top is not None:
            if getattr(d, "full_bleed", False):
                # 满幅装饰件（如 ENG-* 的通栏蓝色标题带）本就画到页边，
                # 页边扫描须从**版心上沿**起算，否则把设计元素报成杂物。
                # 只对显式声明 full_bleed 的装饰件放宽，其余仍从页顶严格扫。
                top = max(top, d.reserve()[1])
            else:
                top = min(top, d.y_top)
        else:
            h = max(d.height(p) for p in (d.pages or (1, 2, 3)))
            if d.y_bot + h > foot_top:
                foot_top, foot_gap = d.y_bot + h, d.gap
    return replace(geom, mast_top=top, foot_top=foot_top, foot_gap=foot_gap)

# 徽标由各文档的 build.py 显式传入（Job.logo）；缺省无徽标。
# 徽标属客户资产，不随技能分发。
LOGO = None


@dataclass
class Job:
    name: str
    src: str                      # 原文 PDF
    work: str                     # 工作区（extract.py 的产出目录）
    out: str                      # 目标译稿
    pages: list                   # flow=True：章的块列表；flow=False：逐源页块列表
    flow: bool = False            # True = R 级语义重排（新文档推荐）
    chapter_break: bool = False   # flow 模式下每章另起一页（长手册可设 True；短文档接排）
    page_budget: tuple = (0.70, 0.85)   # flow：译版正文页数 / 原版页数 的预期区间
    token_ignore: tuple = ()      # 内容对账允许消失的记号（原版页码、修订号等）
    token_src_pages: tuple = None # 内容对账的源页范围（1 基；缺省全部）
    geom: Geom = LETTER
    mast_title: str = ""
    mast_info: tuple = ()
    mast_info_w: tuple = None
    mast_title_size: float = 18.0
    logo_w: float = 144.0
    logo_text: str = ""           # 无徽标图时抬头左格的品牌文字
    logo: str = LOGO              # 徽标图片路径；None = 抬头不放徽标
    foot: tuple = ("", "", "")
    foot_rule: bool = False
    glossary: dict = None
    gloss_note: str = None
    jia: tuple = ()
    yi: tuple = ()
    bing: tuple = ()
    errata_intro: str = None
    labels_zh: dict = None        # 图内英文 → 中文
    # 「保留不译」白名单正则。缺省只放过 1~2 位件号气泡与尺寸字母 A~K；
    # 图表类文档须放宽到任意位数刻度与百分数（坐标刻度同属图形语言）。
    labels_keep_re: object = None
    used_figs: tuple = ()         # 正文引用到的图文件名
    uniq_desc: tuple = ()         # 零件描述唯一串
    desc_zh: object = None
    whitelist: str = None         # 整体替换默认白名单（少用）
    whitelist_add: tuple = ()     # 追加本文档合法英文：人名、商品名、标准号
    whitelist_re: tuple = ()      # 追加原始正则：型号族、零件号格式等
    pre_story: list = None
    front_labels: dict = None
    body_total: int = None
    body_labels_on: bool = True   # False = 页码由内容层写进页眉（原版即如此）
    # 原版封面常不印「Page 1 of N」：把封面列入 nolabel_pages，
    # 并把 body_label_start 设为 2，否则页码序列自检会误报。
    nolabel_pages: tuple = ()
    body_label_start: int = 1
    # 原版整本不设自有页码（如产品样本沿用整册页码 62/63）时置 False，
    # 否则页码序列自检会拿「共 N 页」去比对而永远为空。
    page_seq_check: bool = True
    strict_unused_figs: bool = False   # 有未引用插图即判失败
    # 内容层若加了本文档专有样式（缩进档位等），必须把同一个 S 传进来 ——
    # 否则 driver 自建的 S 里没有那些键，渲染时 KeyError。
    styles_map: dict = None
    # 页面固定位置装饰件（每页可不同的页眉块 / 页脚签署块），见 builder.Decor
    decors: tuple = ()


def _hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def run(job, quiet=False):
    register_fonts()
    try:
        import fontkit
        _src = fontkit._SOURCE.get(("zh", True)) or ""
        if "缺陷" in _src or "内置" in _src or \
                fontkit.find("zh", reportlab=True) == fontkit.find("zh-bold", reportlab=True):
            print("  note 本机中文字体非最佳（无粗体或缺符号）：先跑 `python <技能>/scripts/doctor.py --fonts`")
    except Exception:
        pass
    S = job.styles_map if job.styles_map is not None else styles(flow=job.flow)
    _hdr(f"构建 {job.name}")
    ok = True
    g = job.geom
    figdir = os.path.join(job.work, "figures")

    # ---- 1. 素材层 ----
    print("[1] 素材层自检")
    if job.desc_zh and job.uniq_desc:
        ok &= checks.report("零件描述规则覆盖", checks.test_terms(
            job.uniq_desc, job.desc_zh))
    if job.labels_zh is not None:
        keep = job.labels_keep_re or checks.NUMERIC_KEEP
        ok &= checks.report("图内标注中文覆盖", checks.test_labels(
            job.work, job.labels_zh, keep))
        # 把 extract 抹掉的图内矢量英文按 figures.json 坐标回叠成中文（幂等）
        import figlabel
        figlabel.apply_figures_json(job.work, job.labels_zh, verbose=not quiet)
    missing, unused = checks.test_assets(job.work, job.used_figs)
    ok &= checks.report("引用的图文件存在", missing)
    if unused:
        lvl = "FAIL" if job.strict_unused_figs else "note"
        print(f"  {lvl} 未被引用的插图 {len(unused)} 幅（须人工判断是否漏译）：")
        for x in unused[:10]:
            print("         ", x)
        if job.strict_unused_figs:
            ok = False
    figbad, nfig = checks.check_fig_pages(job.src, job.work)
    ok &= checks.report(f"插图来源核验（比对 {nfig} 幅）", figbad)

    # ---- 2. 构建前 ----
    print("[2] 构建前自检")
    mast = Masthead(job.mast_title, job.mast_info, logo=job.logo,
                    logo_w=job.logo_w, info_w=job.mast_info_w, S=S,
                    title_size=job.mast_title_size,
                    logo_text=job.logo_text) if job.mast_title else None
    foot = Footer(*job.foot, rule=job.foot_rule)
    if mast:
        mh = mast.height(g.fw)
        print(f"  note 抬头实测高 {mh:.1f}pt，版心上沿 "
              f"{g.mast_top + mh + g.body_gap:.1f}pt")
        if getattr(mast, "shrunk", None):
            print(f"  note 抬头元信息格字号自适配收缩：{mast.shrunk}")
    for d in (job.decors or ()):
        side, need = d.reserve()
        print(f"  note 装饰件让出 {side} 净空 {need:.1f}pt")
    if job.flow:
        print(f"  note 流式重排：{len(job.pages)} 章，页数由内容决定（不做逐页 1 页判据）")
    else:
        bad = fit_check(job.pages, g, mast, foot, S, figdir, decors=job.decors)
        ok &= checks.report("每逻辑页实排必须为 1 页", bad)
        if bad:
            print("  逐页装配未过，终止构建（避免产出标签错位的稿子）。")
            return False

    # ---- 3. 构建 ----
    print("[3] 两趟构建")
    # 传**工厂**而非现成 flowable：两趟构建会排两遍，ReportLab 的 Table 有状态，
    # 复用同一实例第二趟会抛 LayoutError（cell too large on page …）。
    def apx():
        out = []
        if job.jia or job.yi or job.bing or job.glossary:
            out.append(("A", errata(job.jia, job.yi, job.bing, S, g.fw,
                                    job.errata_intro)))
        if job.glossary:
            out.append(("B", glossary(job.glossary, S, g.fw,
                                      note=job.gloss_note)))
        return out

    os.makedirs(os.path.dirname(os.path.abspath(job.out)), exist_ok=True)
    info = {}
    n, labels, spans = build_2pass(job.out, job.pages, apx, g, mast, foot, S,
                                   figdir, pre_story=job.pre_story,
                                   front_labels=job.front_labels,
                                   body_total=job.body_total,
                                   body_labels_on=job.body_labels_on,
                                   decors=job.decors, flow_mode=job.flow,
                                   chapter_break=job.chapter_break, info=info)
    n_body = info.get("n_body") if job.flow else (job.body_total or len(job.pages))

    # ---- 4. 成品 ----
    print("[4] 成品自检")
    eg = effective_geom(g, job.decors)
    if (eg.foot_top, eg.mast_top) != (g.foot_top, g.mast_top):
        print(f"  note 自检几何按装饰件实测校正："
              f"页眉带上沿 {eg.mast_top:.1f}pt，页脚带上沿 {eg.foot_top:.1f}pt")
    ok &= checks.report("版心外杂物", checks.check_margins(job.out, eg))
    ok &= checks.report("正文压页脚", checks.check_footer(job.out, eg))
    nolabel, nums, seq = checks.check_labels(
        job.out, body_pages=n_body,
        skip=job.nolabel_pages, start=job.body_label_start)
    ok &= checks.report("无页码标签的物理页", nolabel)
    if job.page_seq_check:
        print(f"  {'OK  ' if seq else 'FAIL'} 正文页码序列 "
              f"{'连续' if seq else nums}")
        ok &= seq
    else:
        print("  note 本件原版不设自有页码，跳过页码序列自检")
    # 附录页允许出现英文：勘误表引用原文、术语对照表英文列
    allow = set()
    for _, p0, p1 in spans:
        allow |= set(range(p0, p1 + 1))
    wl = job.whitelist or checks._WL_DEFAULT
    if job.whitelist_add:
        import re as _re
        wl = wl + "|" + "|".join(_re.escape(x) for x in job.whitelist_add)
    if job.whitelist_re:
        wl = wl + "|" + "|".join(job.whitelist_re)
    eng, half = checks.check_text(job.out, allow_pages=allow, whitelist=wl)
    ok &= checks.report("残留英文行（附录页已豁免）", eng, detail=10)
    ok &= checks.report("中文行中的半角标点", half, detail=10)
    # 避头尾：正文页作硬闸门；附录页仅报告。
    # 原因是 ReportLab 的 CJK 折行分两条路径：单 frag 走 textsplit.dumbSplit，
    # 会查禁则表（zhlib._patch_kinsoku 已补齐 ，；：！？）；含 <b> 等内联标签的
    # 多 frag 走 cjkFragSplit，**完全不查禁则表**，属库本身的限制。
    # 附录 A/B 是 6 列 7.4pt 的密集表且含强调标签，恰落在后一条路径上。
    kin = checks.check_line_start(job.out)
    kin_body = [x for x in kin if x[0] not in allow]
    kin_apx = [x for x in kin if x[0] in allow]
    ok &= checks.report("避头尾：行首收尾标点（正文页）", kin_body, detail=10)
    kend = [x for x in checks.check_line_end(job.out) if x[0] not in allow]
    ok &= checks.report("避头尾：行尾起首标点（正文页）", kend, detail=10)
    ok &= checks.report("缺字（会渲染成豆腐块）", checks.check_glyphs(job.out),
                        detail=10)
    ok &= checks.report("文本层异常码位（别名码位，图号/汉字不可检索）",
                        checks.check_codepoints(job.out), detail=6)
    if kin_apx:
        print(f"  note 附录页避头尾 {len(kin_apx)} 处："
              f"ReportLab 多 frag CJK 折行不支持禁则，属库限制，已在丙中说明")

    if job.flow:
        # R 级第一关：内容对账（数字/件号/型号/标准号全集，附录页不作证）
        body_pages = set(range(1, n + 1)) - allow
        src_pages = set(job.token_src_pages) if job.token_src_pages else None
        lost = checks.check_content_tokens(job.src, job.out, src_pages=src_pages,
                                           out_pages=body_pages,
                                           ignore=job.token_ignore)
        ok &= checks.report("内容对账：源版记号在译版正文中失踪", lost, detail=15)
        try:
            try:
                import pymupdf as _fz
            except ImportError:
                import fitz as _fz
            with _fz.open(job.src) as _d:
                n_src = _d.page_count
            r = n_body / max(1, n_src)
            lo, hi = job.page_budget
            if n_src < 5:
                print(f"  note 页数预算：原版仅 {n_src} 页，比例无参考意义，跳过")
            else:
                tag = "OK  " if lo <= r <= hi else "note"
                print(f"  {tag} 页数预算：正文 {n_body} 页 / 原版 {n_src} 页 = {r:.0%}"
                      f"（预期 {lo:.0%}~{hi:.0%}；明显偏低先查是否整章漏译）")
        except Exception as e:
            print(f"  note 页数预算未能计算：{e}")

    print(f"\n  {'PASS' if ok else 'FAIL'}  {job.out}  共 {n} 页")
    return ok
