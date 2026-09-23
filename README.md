# pdf-translate-zh

**工业技术 PDF → 出版级简体中文 PDF** 的 Agent Skill。
适用于 Claude Code、Claude.ai / Claude 桌面版，以及 Codex、Cursor、GitHub Copilot、Gemini CLI、OpenCode、Windsurf 等支持 [Agent Skills](https://agentskills.io) 标准的 AI 工具。

[![CI](https://github.com/ldfpku/pdf-translate-zh/actions/workflows/ci.yml/badge.svg)](https://github.com/ldfpku/pdf-translate-zh/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> English summary: an Agent Skill that turns English industrial / oil & gas / mechanical engineering PDFs (manuals, specs, drawings, fillable forms, slide handouts) into publication-grade Simplified Chinese PDFs. It classifies each page (reflow R / hybrid H / in-place overlay P / slides S), translates text inside figures, rebuilds tables on a true grid, adds TOC links and bookmarks, and runs machine QA gates (content reconciliation, residual English, missing glyphs). Works on Windows, macOS and Linux; Python dependencies and CJK fonts are set up automatically on first run.

---

## 它能做什么

- **先识别行业与版面级别**，再决定怎么译：说明书/规范走语义重排（R），图纸与可填写表单原位叠印（P），混合页（H）和 PPT 讲义（S）各有路线。
- **自带排版引擎**：中文断行禁则、字号取齐、表格真网格重建、图内文字（矢量 / 描边 / 位图烧死）替换、件号气泡重绘、低清插图超分。
- **目录与导航**：目录页码回填、跳转链接、PDF 书签。
- **机器闸门**：内容对账、残留英文、缺字、越界、叠字等检查，全部通过才出稿。
- **可追溯**：每份译稿附《译校勘误说明》与《中英术语对照表》。
- **零人工配置**：首次使用自动安装 Python 依赖（装进技能私有缓存，不碰系统 Python，无需管理员权限）、自动找/配中文字体；插图超分后端按需安装。

## 安装

任选一种。装好后**重启你的 AI 工具**，对它说「把这份 PDF 翻译成中文版」即可触发。

### 1. Claude Code 插件市场（推荐给 Claude Code 用户）

在 Claude Code 里执行：

```text
/plugin marketplace add ldfpku/pdf-translate-zh
/plugin install pdf-translate-zh@pdf-translate-zh
```

以后更新：`/plugin marketplace update pdf-translate-zh`。

### 2. `npx skills`（跨工具通用）

需要 Node.js 18+。一条命令装给多个工具：

```bash
npx skills add ldfpku/pdf-translate-zh -g                          # 交互选择要装到哪些工具
npx skills add ldfpku/pdf-translate-zh -g -a claude-code -y        # 只装给 Claude Code
npx skills add ldfpku/pdf-translate-zh -g -a claude-code cursor codex --copy -y
```

去掉 `-g` 则装到当前项目；`--copy` 复制文件而不是建符号链接（Windows 上推荐）。

### 3. 安装脚本

**macOS / Linux：**

```bash
curl -fsSL https://raw.githubusercontent.com/ldfpku/pdf-translate-zh/main/install.sh | sh -s -- --agent claude
```

**Windows（PowerShell）：**

```powershell
irm https://raw.githubusercontent.com/ldfpku/pdf-translate-zh/main/install.ps1 | iex
# 需要带参数时：
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/ldfpku/pdf-translate-zh/main/install.ps1))) -Agent claude
```

克隆仓库后也可以本地运行，参数更多：

| macOS / Linux | Windows | 作用 |
|---|---|---|
| `sh install.sh` | `.\install.ps1` | 自动检测本机装过的 AI 工具，全部装上（都没有则装给 Claude） |
| `--agent claude` | `-Agent claude` | 只装给某个工具：`claude codex cursor copilot gemini opencode windsurf agents all` |
| `--project .` | `-Project .` | 装到当前项目（`.claude/skills` 与 `.agents/skills`） |
| `--link` | `-Link` | 用符号链接 / 目录联接，改仓库立即生效（开发用） |
| `--bootstrap` | `-Bootstrap` | 装完顺手配好 Python 依赖与字体（不加也行，首次使用会自动配） |
| `--uninstall` | `-Uninstall` | 卸载 |

> Windows 若提示禁止运行脚本，用 `powershell -ExecutionPolicy Bypass -File install.ps1 …`。

### 4. Claude.ai / Claude 桌面版（上传 zip）

1. 从 [Releases](https://github.com/ldfpku/pdf-translate-zh/releases) 下载 `pdf-translate-zh.zip`（或本地 `python tools/package.py` 生成到 `dist/`）。
2. 打开 **设置 → Capabilities（功能）→ Skills**，上传该 zip 并启用。

> 该环境里依赖需要能访问 PyPI 或国内镜像；如网络受限，见下文「自定义镜像」。

### 5. 手动复制

把 `skills/pdf-translate-zh/` 整个目录复制到对应工具的技能目录：

| 工具 | 全局目录 | 项目目录 |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.codex/skills/`（新版也读 `~/.agents/skills/`） | `.agents/skills/` |
| Cursor | `~/.cursor/skills/` | `.agents/skills/` 或 `.cursor/skills/` |
| GitHub Copilot | `~/.copilot/skills/` | `.github/skills/` 或 `.agents/skills/` |
| Gemini CLI | `~/.gemini/skills/` | `.gemini/skills/` 或 `.agents/skills/` |
| OpenCode | `~/.config/opencode/skills/` | `.opencode/skills/` 或 `.agents/skills/` |
| Windsurf | `~/.codeium/windsurf/skills/` | `.windsurf/skills/` |
| 通用 | `~/.agents/skills/` | `.agents/skills/` |

Windows 下 `~` 即 `C:\Users\<用户名>`。各工具的目录约定在更新，以其官方文档为准；拿不准时用 `npx skills` 安装最省事。

## 运行环境

- **Python 3.9+**（Windows / macOS / Linux，x86_64 与 Apple Silicon 均可）。没有 Python 时，`setup.sh` / `setup.ps1` 会尝试用 Homebrew / winget / apt 自动装。
- 其余**全部自动**：
  - Python 依赖（PyMuPDF、reportlab、Pillow、numpy、fontTools、scipy）装进用户缓存下的私有目录，按 Python 版本和平台分开；系统里已有的包直接复用。下载源依次尝试 官方 PyPI → 清华 → 阿里云。
  - 中文字体：优先用系统字体（Windows 微软雅黑/宋体，macOS 苹方/华文，Linux Noto CJK）；Linux 缺字体时自动下载并转换。
  - 插图超分：只有检测到低清位图时才装后端——Apple Silicon 用 MPS 版 torch，NVIDIA 显卡用 CUDA 版，其他用 CPU 版（配置了 `sr_onnx_url` 时改用更轻的 ONNX Runtime）；装不上就退回高质量插值，不影响出稿。

缓存位置：Windows `%LOCALAPPDATA%\pdf-translate-zh\cache`，macOS / Linux `~/.cache/pdf-translate-zh`（可用 `PDF_ZH_CACHE` 改）。

想提前一次配好（可选）：

```bash
sh ~/.claude/skills/pdf-translate-zh/setup.sh          # macOS / Linux；加 --sr 同时装超分
```

```powershell
powershell -ExecutionPolicy Bypass -File $HOME\.claude\skills\pdf-translate-zh\setup.ps1
```

### 自定义镜像与开关

把技能目录里的 `config.example.json` 复制为 `config.json`，保留需要的键即可；它跟着技能目录走，换电脑不必重配。同名环境变量 `PDF_ZH_<键名大写>` 优先。

| 键 | 作用 |
|---|---|
| `pip_index` | 自己的 pip 源，排在默认源之前 |
| `torch_index` | torch 的下载源 |
| `sr_url` / `sr_onnx_url` / `sr_onnx_sha256` | 超分权重的下载地址（内网或自建镜像） |
| `sr_autoinstall` | `0` = 不自动装超分后端 |
| `no_autoinstall` | `1` = 完全不自动装依赖（离线环境自行准备） |
| `no_autofonts` | `1` = 不自动下载字体 |

## 使用

在 AI 工具里直接说，例如：

- 「把 `C:\docs\pump_manual.pdf` 翻译成中文版」
- 「把这份图纸汉化，保持原版式」
- "Translate this drilling specification PDF into Chinese"

技能会：识别行业 → 逐页定级 → 提取 → 翻译 → 重排或叠印 → 跑闸门 → 输出 `<原名>_中文_v01.pdf` 与勘误/术语附录。流程细节见 [`skills/pdf-translate-zh/SKILL.md`](skills/pdf-translate-zh/SKILL.md)。

`examples/` 里有两份完整的内容层示例（基于虚构文档，由 `tests/gen_testdocs.py` 生成源 PDF）：

- `examples/mud-motor-manual/`：R 级说明书（页眉、术语表、正文重排）
- `examples/stator-drawing/`：P 级工程图纸（原位叠印、白名单、字典）

## 验证安装

```bash
python tests/smoke_test.py        # Windows：py tests\smoke_test.py
```

它会：引擎自检 → 生成虚构样例 PDF → 定级（R/R/P）→ R 级示例出稿并过全部闸门 → P 级图纸叠印并过六道关。首次运行含依赖安装，约 1–3 分钟；之后约 20 秒。全部 PASS 即环境可用。

## 仓库结构

```text
.claude-plugin/          Claude Code 插件与市场清单
skills/pdf-translate-zh/ 技能本体（SKILL.md、references/、scripts/、setup.*）
examples/                完整内容层示例（虚构文档）
tests/                   样例 PDF 生成与端到端冒烟测试
tools/package.py         打包 dist/pdf-translate-zh.zip
install.sh / install.ps1 多工具安装脚本
```

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。改动技能后请跑 `python tests/smoke_test.py`，并同步 `SKILL.md`、`.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` 三处版本号。

## 许可

[Apache-2.0](LICENSE)。运行时按需下载的第三方组件（PyMuPDF 为 AGPL-3.0/商业双许可，Real-ESRGAN 权重为 BSD-3-Clause 等）不随本仓库分发，见 [NOTICE](NOTICE)。
