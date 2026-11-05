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
- 改版本只改**一处**：`skills/pdf-translate-zh/SKILL.md` frontmatter 的 `metadata.version`（单一数据源），
  然后跑 `python tools/sync_version.py`，脚本会把它同步写入 `SKILL.md` 正文的版本展示行、`.claude-plugin/plugin.json`、
  `.claude-plugin/marketplace.json`。更新 `CHANGELOG.md`，打 `vX.Y.Z` 标签推送；Release 工作流会先 `sync_version.py --check --tag`
  校验四处与标签一致（不一致即发布失败），再自动打包上传。

## 样例与隐私

- **不要提交客户文档或其译稿**，也不要在代码、注释、参考文档里写客户名称、人名、内部编号。
- 需要样例时，在 `tests/gen_testdocs.py` 里用虚构内容生成。
- 字体、模型权重（`*.ttf` / `*.otf` / `*.pth` / `*.onnx`）不入库，由运行时自动获取。
