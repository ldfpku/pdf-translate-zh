# -*- coding: utf-8 -*-
"""打包技能：dist/pdf-translate-zh.zip —— 上传到 Claude.ai / Claude 桌面版（设置 → Skills）用。

    python3 tools/package.py [--out dist]

zip 内顶层就是 pdf-translate-zh/ 目录（SKILL.md 在其中），排除缓存与个人设置。
同时校验 SKILL.md 的 frontmatter（name 与目录同名、description ≤ 1024 字符）。
"""
import argparse
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "pdf-translate-zh"
SKILL = os.path.join(ROOT, "skills", NAME)
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}
EXCLUDE_FILES = {"config.json", ".DS_Store", "Thumbs.db"}
EXCLUDE_EXT = {".pyc", ".pyo", ".pth", ".onnx", ".part"}


def check_frontmatter():
    s = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n", s, re.S)
    if not m:
        sys.exit("SKILL.md 缺 frontmatter")
    fm = m.group(1)
    name = re.search(r"^name:\s*(.+)$", fm, re.M)
    desc = re.search(r"^description:\s*(.+)$", fm, re.M)
    if not name or name.group(1).strip() != NAME:
        sys.exit("frontmatter name 必须是 %s" % NAME)
    if not desc or len(desc.group(1).strip()) > 1024:
        sys.exit("frontmatter description 缺失或超过 1024 字符")
    if "<" in desc.group(1) or ">" in desc.group(1):
        sys.exit("description 里不能有尖括号")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    a = ap.parse_args()
    check_frontmatter()
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, NAME + ".zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(SKILL):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for f in sorted(files):
                if f in EXCLUDE_FILES or os.path.splitext(f)[1] in EXCLUDE_EXT:
                    continue
                p = os.path.join(root, f)
                arc = os.path.join(NAME, os.path.relpath(p, SKILL)).replace(os.sep, "/")
                z.write(p, arc)
                n += 1
    print("打包完成：%s（%d 个文件，%.0f KB）" % (out, n, os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main()
