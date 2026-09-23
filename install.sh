#!/usr/bin/env sh
# pdf-translate-zh 安装脚本（macOS / Linux）
#
# 用法（在克隆下来的仓库里）：
#   sh install.sh                      # 自动检测本机已装的 AI 工具，全部装上
#   sh install.sh --agent claude       # 只装给某一个：claude codex cursor copilot gemini opencode windsurf agents
#   sh install.sh --agent all          # 全部目录都装
#   sh install.sh --project .          # 装到当前项目（.claude/skills 与 .agents/skills）
#   sh install.sh --link               # 用符号链接（开发时改仓库即生效）
#   sh install.sh --bootstrap          # 装完顺手配好 Python 依赖与中文字体（不装也行，首次使用会自动配）
#   sh install.sh --uninstall          # 卸载
# 不克隆，一行安装：
#   curl -fsSL https://raw.githubusercontent.com/ldfpku/pdf-translate-zh/main/install.sh | sh -s -- --agent claude
set -e

NAME="pdf-translate-zh"
REPO="ldfpku/pdf-translate-zh"
REF="${PDF_ZH_REF:-main}"

AGENTS=""
PROJECT=""
LINK=0
BOOT=0
UNINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --agent|-a) AGENTS="$AGENTS $2"; shift 2 ;;
    --project|-p) PROJECT="$2"; shift 2 ;;
    --link) LINK=1; shift ;;
    --bootstrap) BOOT=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "未知参数：$1"; exit 2 ;;
  esac
done

# ---- 技能源：优先用脚本所在的仓库；管道运行时下载 GitHub 归档
SRC=""
if [ -n "${0:-}" ] && [ -f "$(dirname "$0")/skills/$NAME/SKILL.md" ]; then
  SRC="$(cd "$(dirname "$0")" && pwd)/skills/$NAME"
fi
if [ -z "$SRC" ] && [ "$UNINSTALL" = 0 ]; then
  TMP="$(mktemp -d)"
  echo "[install] 下载 $REPO@$REF …"
  curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REF" | tar -xz -C "$TMP"
  SRC="$(find "$TMP" -maxdepth 3 -type d -path "*/skills/$NAME" | head -1)"
  [ -f "$SRC/SKILL.md" ] || { echo "[install] 下载的归档里找不到 skills/$NAME"; exit 1; }
  LINK=0
fi

dir_of() {   # 全局安装目录
  case "$1" in
    claude)   echo "$HOME/.claude/skills" ;;
    codex)    echo "${CODEX_HOME:-$HOME/.codex}/skills" ;;
    cursor)   echo "$HOME/.cursor/skills" ;;
    copilot)  echo "$HOME/.copilot/skills" ;;
    gemini)   echo "$HOME/.gemini/skills" ;;
    opencode) echo "$HOME/.config/opencode/skills" ;;
    windsurf) echo "$HOME/.codeium/windsurf/skills" ;;
    agents)   echo "$HOME/.agents/skills" ;;
    *) echo "" ;;
  esac
}
home_of() {  # 用来判断该工具是否装过
  case "$1" in
    claude) echo "$HOME/.claude" ;; codex) echo "${CODEX_HOME:-$HOME/.codex}" ;;
    cursor) echo "$HOME/.cursor" ;; copilot) echo "$HOME/.copilot" ;;
    gemini) echo "$HOME/.gemini" ;; opencode) echo "$HOME/.config/opencode" ;;
    windsurf) echo "$HOME/.codeium/windsurf" ;; agents) echo "$HOME/.agents" ;;
  esac
}
ALL="claude codex cursor copilot gemini opencode windsurf agents"

TARGETS=""
if [ -n "$PROJECT" ]; then
  P="$(cd "$PROJECT" && pwd)"
  TARGETS="$P/.claude/skills $P/.agents/skills"
else
  case " $AGENTS " in *" all "*) AGENTS="$ALL" ;; esac
  if [ -z "$(echo $AGENTS)" ]; then
    for a in $ALL; do [ -d "$(home_of $a)" ] && AGENTS="$AGENTS $a"; done
    [ -z "$(echo $AGENTS)" ] && AGENTS="claude"
  fi
  for a in $AGENTS; do
    d="$(dir_of "$a")"
    [ -n "$d" ] || { echo "[install] 未知工具：$a（可选：$ALL all）"; exit 2; }
    TARGETS="$TARGETS $d"
  done
fi

for d in $TARGETS; do
  dst="$d/$NAME"
  if [ "$UNINSTALL" = 1 ]; then
    [ -e "$dst" ] || [ -L "$dst" ] && rm -rf "$dst" && echo "[install] 已卸载 $dst"
    continue
  fi
  mkdir -p "$d"
  rm -rf "$dst"
  if [ "$LINK" = 1 ]; then
    ln -s "$SRC" "$dst"
  else
    cp -R "$SRC" "$dst"
    find "$dst" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  fi
  echo "[install] 已安装 → $dst"
done

if [ "$UNINSTALL" = 0 ] && [ "$BOOT" = 1 ]; then
  first="$(echo $TARGETS | awk '{print $1}')/$NAME"
  sh "$first/setup.sh"
fi
[ "$UNINSTALL" = 0 ] && echo "[install] 完成。重启你的 AI 工具后对它说「把这份 PDF 翻译成中文版」即可触发；依赖会在首次使用时自动配置。"
exit 0
