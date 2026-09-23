# -*- coding: utf-8 -*-
"""搭一个「代理端到端验证」工作区：换一个模型 / AI 工具时，用它检验技能是否真的能用。

    python tests/agent_eval/make_workspace.py <工作区目录>

工作区里有：
  .agents/skills/pdf-translate-zh   技能（Antigravity / Codex / Cursor 等读这里）
  .claude/skills/pdf-translate-zh   同一份技能（Claude Code 读这里）
  docs/jar_field_guide.pdf          留出集：R 级手册（虚构 Borealis 650 震击器）
  docs/mandrel_drawing.pdf          留出集：P 级图纸（花键芯轴）
  PROMPT.md                         交给代理的任务（中文，像真实用户那样说）
  grade.py                          独立评分，不信代理自述
  run_agy.ps1                       Windows + Antigravity CLI 一键跑（其他工具手动粘贴 PROMPT.md）

⚠ 工作区**不要**放在本仓库旁边：代理有文件权限时会去翻 examples/ 直接抄参考译文
  （实测发生过，闸门全绿但一个字没译）。留出集没有任何现成译文，grade.py 还会查抄袭痕迹。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SKILL = os.path.join(ROOT, "skills", "pdf-translate-zh")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ws = os.path.abspath(sys.argv[1])
    if os.path.commonpath([ws, ROOT]) == ROOT or os.path.dirname(ws) == os.path.dirname(ROOT):
        print("提示：工作区离仓库太近，代理可能去抄 examples/。建议放到别处（如临时目录）。")
    os.makedirs(os.path.join(ws, "docs"), exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "config.json")
    for sub in (".agents", ".claude"):
        dst = os.path.join(ws, sub, "skills", "pdf-translate-zh")
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(SKILL, dst, ignore=ignore)
    for f in ("PROMPT.md", "grade.py", "run_agy.ps1"):
        shutil.copy(os.path.join(HERE, f), os.path.join(ws, f))
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import bootstrap
    bootstrap.ensure(quiet=True)
    subprocess.run([sys.executable, os.path.join(HERE, "gen_holdout.py"), os.path.join(ws, "docs")],
                   check=True)
    print("工作区就绪：", ws)
    print("下一步：在该目录用你的 AI 工具执行 PROMPT.md 的任务，完成后运行  python grade.py")


if __name__ == "__main__":
    main()
