# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-09-23

首个公开版本。

### 新增
- 工业技术 PDF → 出版级简体中文 PDF 的完整流程：行业识别、逐页定级（R / H / P / S）、提取、重排或原位叠印、图内文字、表格网格重建、目录链接与书签、插图超分与件号气泡、机器闸门、勘误与术语附录。
- 跨平台：Windows / macOS / Linux；字体解析 `fontkit`（系统字体 → 转换缓存 → PyMuPDF 内置字体兜底）。
- 环境自动配置 `bootstrap.py`：依赖装进私有缓存（多镜像回退、断点安全、文件锁），Linux 自动补中文字体，超分后端按显卡按需安装。
- 多工具安装：Claude Code 插件市场、`npx skills`、`install.sh` / `install.ps1`、Claude.ai zip 包。
- 虚构样例文档与端到端冒烟测试；三平台 CI。
