# 代理端到端验证（agent eval）

`tests/smoke_test.py` 只验证**引擎**：内容层是仓库里现成的示例。这里验证的是**模型 + AI 工具**
能不能按 SKILL.md 自己把一份没见过的英文 PDF 做成合格的中文版。

## 用法

```bash
python tests/agent_eval/make_workspace.py <工作区目录>     # 放在远离本仓库的地方
```

然后在工作区里让 AI 工具执行 `PROMPT.md` 的任务：

- **Antigravity CLI（Windows）**：`powershell -ExecutionPolicy Bypass -File .\run_agy.ps1`
  （默认 `gemini-3.8-flash-medium`；换模型先设 `$env:AGY_MODEL`）。
- **其他工具**（Claude Code、Codex、Cursor、Antigravity IDE …）：打开工作区，选好模型，把 `PROMPT.md` 全文粘给代理。

代理完成后运行 `python grade.py`，结果写进 `grade.json` / `grade.log`。

## 评分项（`grade.py`）

| 项 | 判据 |
|---|---|
| 成品 | `docs/translated/<名>_中文_v*.pdf` 存在 |
| 可复现 | 重跑代理写的 `content/build.py`：返回 0、没有 FAIL |
| 附录分页 | 附录 A、B 齐全，各自另起一页，起始页标题上方没有正文 |
| 残留英文 / 缺字 | 正文页残留英文行（缺省白名单）、缺字 = 0 |
| 术语抽查 | 行业「外行必错」词用行业译名（jar→震击器、mandrel→芯轴） |
| 防抄 | 内容层里不得出现仓库示例的特征串 |

机器评分之外，还要**人工通读**译稿与附录：术语是否地道、勘误条目与正文是否一致。

## 留出集

`gen_holdout.py` 生成两份虚构文档（Borealis Downhole Systems 为虚构品牌），**没有任何现成译文**：

- `jar_field_guide.pdf`：650 液压钻井震击器现场操作指南，3 页，R 级（散文、步骤、两张表、矢量插图、危险/说明框）；
- `mandrel_drawing.pdf`：花键芯轴工程图，1 页横版，P 级（剖面线、尺寸、技术要求、明细栏、标题栏）。

## 教训

第一次验证把工作区放在仓库旁边、用的是仓库自带的样例文档：代理直接从 `examples/` 复制了
参考内容层，3 分钟「完成」，闸门全绿，REPORT.md 写得像是自己译的——一个字没译。
所以：**用留出集、工作区远离仓库、评分脚本查抄袭、人工抽读**，四样缺一不可。
