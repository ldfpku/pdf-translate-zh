# -*- coding: utf-8 -*-
"""tocsweep.py 的登记表示例（虚构文档名）。复制一份改成你的，然后：

    python3 tocsweep.py <项目根目录> --pages 我的登记表.py
"""

# 键 = 源 PDF 主名（不含 .pdf，前 34 个字符匹配即可）；
# 值 = (封面页, 目录页[, 从零重建=True])，页号是**成品**上的物理页（1 基），() 表示没有。
# 标 True 的走重排路线：保留项失踪关不适用（图表被画成图元/位图，源文本在成品里本就不存在）。
PAGES = {
    "Example Motor Operation Manual Rev B":  ((1,), (2, 3)),
    "Example Drilling Jar Service Manual":   ((1,), (2,)),
    "Example Technical Bulletin 12":         ((1,), (), True),
}

# 白名单：成品里合法保留的英文（商标、产品名、人名、地址、图号）。正则。
WL = (r"ACME|Example|Rev|Page|of|www\.|http|"
      r"\b[A-Z] [A-Z][a-z]+\b")             # 签署栏的缩写名 + 姓

# 明示豁免：{源 PDF 主名: [(关名前缀, 命中片段, 理由), …]} —— 凡豁免必须写清理由。
WAIVE = {
    "Example Motor Operation Manual Rev B": [
        ("H 封面对齐", "y≈410", "标题居中、其下列表左对齐是有意的版式选择"),
    ],
}
