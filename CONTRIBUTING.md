# 参与贡献

欢迎提交 Issue 与 Pull Request。

## 本地开发

```bash
git clone https://github.com/ldfpku/pdf-translate-zh.git
cd pdf-translate-zh
sh install.sh --agent claude --link        # Windows: .\install.ps1 -Agent claude -Link
python tests/smoke_test.py                  # Windows: py tests\smoke_test.py
```

`--link` 让已安装的技能直接指向仓库，改完即生效。

## 提交前

- `python tests/smoke_test.py` 全部 PASS。
- `python tools/package.py` 能打包（顺带校验 SKILL.md frontmatter）。
- 改了流程或规则、或想登记新模型：按 `tests/agent_eval/README.md` 跑一次代理端到端验证，把结果补进 README「已验证的模型」。
- 新规则写进对应的 `references/*.md`，并在 `SKILL.md` 的分册表里能找到入口；`SKILL.md` 正文保持精简。
- 发版时同步三处版本号：`skills/pdf-translate-zh/SKILL.md`（`metadata.version`）、`.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`，并更新 `CHANGELOG.md`。打 `vX.Y.Z` 标签后 Release 工作流会自动打包上传。

## 样例与隐私

- **不要提交客户文档或其译稿**，也不要在代码、注释、参考文档里写客户名称、人名、内部编号。
- 需要样例时，在 `tests/gen_testdocs.py` 里用虚构内容生成。
- 字体、模型权重（`*.ttf` / `*.otf` / `*.pth` / `*.onnx`）不入库，由运行时自动获取。
