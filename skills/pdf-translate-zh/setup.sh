#!/usr/bin/env sh
# pdf-translate-zh 一键环境配置（macOS / Linux）：找到或装好 Python 3.9+，然后交给 bootstrap.py 全自动完成。
#   sh setup.sh          核心依赖 + 中文字体 + 自检
#   sh setup.sh --sr     另外装插图超分后端并下载权重
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

find_py() {
  for c in "$PDF_ZH_PYTHON" python3 python python3.12 python3.11 python3.13 python3.10; do
    [ -n "$c" ] || continue
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      echo "$c"; return 0
    fi
  done
  return 1
}

PY="$(find_py || true)"
if [ -z "$PY" ]; then
  echo "[setup] 没找到 Python 3.9+，尝试自动安装…"
  if [ "$(uname)" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then brew install python; else
      echo "[setup] 请先装 Python：https://www.python.org/downloads/macos/ （或装 Homebrew 后重跑本脚本）"; exit 1; fi
  elif command -v apt-get >/dev/null 2>&1; then
    sudo -n apt-get install -y python3 python3-pip || { echo "[setup] 需要管理员权限：sudo apt-get install -y python3 python3-pip"; exit 1; }
  elif command -v dnf >/dev/null 2>&1; then
    sudo -n dnf install -y python3 python3-pip || { echo "[setup] 需要管理员权限：sudo dnf install -y python3 python3-pip"; exit 1; }
  else
    echo "[setup] 请先安装 Python 3.10+"; exit 1
  fi
  PY="$(find_py)"
fi
echo "[setup] 使用 $("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
exec "$PY" "$DIR/scripts/bootstrap.py" "$@"
