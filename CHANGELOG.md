# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.2] - 2026-09-24

### 变更
- **附录与译文分隔**：每份译稿在主体译文之后附《译校勘误说明》（附录 A）与《中英术语对照表》（附录 B），两份附件各自另起一页，任何一页都不同时承载正文与附录；页码单独编为「附录 A-n」「附录 B-n」。
- 叠印路线（P / S 级：图纸、表单、讲义）此前不生成附录，现与重排路线一致：`content/terms.py` 写附录数据，叠印正文后自动追加（A4 竖排）；H 级拼合后可用 `python scripts/appendix.py <成品.pdf> <terms.py>` 统一追加。
- 新成品闸门「附录分页」（`checks.check_appendix_pages`）：A、B 齐全，各自另起一页，标题是起始页版心里的第一段文字；`GLOSSARY` 为空导致附录 B 缺失时判失败。

### 新增
- 代理端到端验证 `tests/agent_eval/`：留出集文档（无现成译文）、任务提示、独立评分（可复现、附录分页、术语抽查、防抄）；README 新增「已验证的模型」：Gemini 3.8 Flash（Medium）+ Antigravity CLI 通过。
- 行业惯例补充：API 螺纹类型译名（REG 正规扣、IF 内平扣、FH 贯眼扣、NC 数字型扣）、工程图标题栏译法、商号整体保留原文。
- R 级骨架把 `terms.ERRATA_INTRO`（行业判定与依据）传进附录 A 引言（此前需手工改 build.py）。
- 安装脚本支持 Google Antigravity（`--agent antigravity` → `~/.gemini/config/skills`）。
- 冒烟测试独立复核 R 级与 P 级成品的附录分页；图纸示例补上 `terms.py`。

## [1.0.1] - 2026-09-24

### 新增
- README 顶部加入**数据合规声明**，并新增「本地模型方案」：用 Ollama 等本地服务驱动 Claude Code / Codex 等工具，敏感文档不出本机。
- SKILL.md 加入合规提示：遇到疑似保密、出口管制或含个人信息的文件时，开工前提醒用户一次。

### 修复
- 中文断行：行尾不能起行的标点（「）」「，」等）悬挂后仍超出版心时，改为把前一个字一起推到下一行，不再让标点落进右页边（无中文系统字体、用内置字体兜底时会触发，CI 的 Linux 冒烟测试因此失败）。
- 本机没有任何中文字体时，给出准确提示，不再误报「只有 CFF 版中文字体」。

## [1.0.0] - 2026-09-23

首个公开版本。

### 新增
- 工业技术 PDF → 出版级简体中文 PDF 的完整流程：行业识别、逐页定级（R / H / P / S）、提取、重排或原位叠印、图内文字、表格网格重建、目录链接与书签、插图超分与件号气泡、机器闸门、勘误与术语附录。
- 跨平台：Windows / macOS / Linux；字体解析 `fontkit`（系统字体 → 转换缓存 → PyMuPDF 内置字体兜底）。
- 环境自动配置 `bootstrap.py`：依赖装进私有缓存（多镜像回退、断点安全、文件锁），Linux 自动补中文字体，超分后端按显卡按需安装。
- 多工具安装：Claude Code 插件市场、`npx skills`、`install.sh` / `install.ps1`、Claude.ai zip 包。
- 虚构样例文档与端到端冒烟测试；三平台 CI。
