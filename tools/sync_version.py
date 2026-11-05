# -*- coding: utf-8 -*-
"""版本号单一数据源同步。

真值 = skills/pdf-translate-zh/SKILL.md 的 frontmatter `metadata.version`。
把它同步写入：
  1. SKILL.md 正文的 <!-- VERSION:AUTO --> 标记行（用户/模型可见的版本展示）；
  2. .claude-plugin/plugin.json 的 version；
  3. .claude-plugin/marketplace.json 的 plugins[0].version。

用法：
    python tools/sync_version.py            # 写入：把三处同步成 frontmatter 的版本
    python tools/sync_version.py --check     # 只校验：三处是否都等于 frontmatter，不一致 exit 1
    python tools/sync_version.py --check --tag v1.3.0
                                             # 发布时用：再校验 frontmatter 是否等于标签（去掉前缀 v）

设计意图：发布时推送 `v*` 标签 → CI 先 `--check --tag`，不一致直接失败；
平时改版本只改 frontmatter 一处，跑一次本脚本（无 --check）即全仓同步，推送即一致。
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_MD = os.path.join(ROOT, "skills", "pdf-translate-zh", "SKILL.md")
PLUGIN = os.path.join(ROOT, ".claude-plugin", "plugin.json")
MARKET = os.path.join(ROOT, ".claude-plugin", "marketplace.json")

# 正文里的版本展示行：<!-- VERSION:AUTO -->**版本 v1.3.0** · ...
BODY_RE = re.compile(r"(<!-- VERSION:AUTO -->\*\*版本 v)([^*]+)(\*\*)")
# frontmatter 内的 metadata.version（缩进的 version:，区别于顶层 version 字段）
FM_VERSION_RE = re.compile(r"(?m)^\s+version:\s*\"?([^\"\n]+)\"?\s*$")
# plugin.json / marketplace.json 里的 "version": "x.y.z"（两文件各仅一处，精确替换值、不动格式）
JSON_VERSION_RE = re.compile(r"(\"version\"\s*:\s*\")([^\"]+)(\")")


def read_source_version():
    s = open(SKILL_MD, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n", s, re.S)
    if not m:
        sys.exit("SKILL.md 缺 frontmatter")
    mv = FM_VERSION_RE.search(m.group(1))
    if not mv:
        sys.exit("frontmatter 的 metadata.version 没找到")
    return mv.group(1).strip()


def _json_version(path):
    m = JSON_VERSION_RE.search(open(path, encoding="utf-8").read())
    return m.group(2) if m else None


def current_values():
    body = BODY_RE.search(open(SKILL_MD, encoding="utf-8").read())
    return {
        "SKILL.md 正文": body.group(2).strip() if body else None,
        "plugin.json": _json_version(PLUGIN),
        "marketplace.json": _json_version(MARKET),
    }


def _sub_in_file(path, pattern, ver, label):
    s = open(path, encoding="utf-8").read()
    if not pattern.search(s):
        sys.exit("%s 缺少可写入的版本字段" % label)
    s = pattern.sub(lambda m: m.group(1) + ver + m.group(3), s, count=1)
    open(path, "w", encoding="utf-8", newline="\n").write(s)


def write_all(ver):
    # 只替换版本值本身，保留三个文件原有格式（避免 json 重排产生无关 diff）
    _sub_in_file(SKILL_MD, BODY_RE, ver, "SKILL.md 正文 <!-- VERSION:AUTO --> 标记行")
    _sub_in_file(PLUGIN, JSON_VERSION_RE, ver, "plugin.json")
    _sub_in_file(MARKET, JSON_VERSION_RE, ver, "marketplace.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验不写入")
    ap.add_argument("--tag", help="发布标签（如 v1.3.0），校验 frontmatter 是否与之一致")
    a = ap.parse_args()

    ver = read_source_version()

    if a.tag:
        tag = a.tag.lstrip("v")
        if tag != ver:
            sys.exit("frontmatter 版本 %s 与标签 %s 不一致" % (ver, a.tag))

    if a.check:
        bad = {k: v for k, v in current_values().items() if v != ver}
        if bad:
            sys.exit("以下位置与真值 %s 不一致（请跑 python tools/sync_version.py 同步）：%s" % (ver, bad))
        print("版本一致：全仓均为", ver)
        return

    write_all(ver)
    print("已同步全仓版本为", ver)


if __name__ == "__main__":
    main()
