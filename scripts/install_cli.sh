#!/usr/bin/env bash
# 将 codewisp / codewisp-api 安装到用户 PATH，任意目录可直接调用（无需 source venv）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$ROOT/.venv/bin"
TARGET_DIR="${CODEWISP_BIN_DIR:-$HOME/.local/bin}"

if [[ ! -x "$VENV_BIN/codewisp" ]]; then
  echo "未找到 $VENV_BIN/codewisp"
  echo "请先："
  echo "  cd \"$ROOT\" && python3 -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\""
  exit 1
fi

mkdir -p "$TARGET_DIR"
ln -sfn "$VENV_BIN/codewisp" "$TARGET_DIR/codewisp"
ln -sfn "$VENV_BIN/codewisp-api" "$TARGET_DIR/codewisp-api"

echo "已安装："
echo "  $TARGET_DIR/codewisp -> $VENV_BIN/codewisp"
echo "  $TARGET_DIR/codewisp-api -> $VENV_BIN/codewisp-api"

# 确保 ~/.local/bin 在 PATH 中（zsh / bash）
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.zprofile"; do
  if [[ -f "$rc" ]] || [[ "$rc" == "$HOME/.zshrc" ]]; then
    touch "$rc"
    if ! grep -qF '.local/bin' "$rc" 2>/dev/null; then
      {
        echo ""
        echo "# CodeWisp CLI"
        echo "$PATH_LINE"
      } >> "$rc"
      echo "已写入 PATH 到 $rc"
    fi
  fi
done

echo ""
echo "请执行：  source ~/.zshrc"
echo "然后在任意项目目录：  codewisp"
