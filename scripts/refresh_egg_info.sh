#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX_DIR="${PREFIX_DIR:-$ROOT_DIR/.runtime/local-pip}"
CACHE_DIR="${PIP_CACHE_DIR:-$ROOT_DIR/.runtime/pip-cache}"
LOG_PATH="$ROOT_DIR/.runtime/refresh_egg_info.log"

mkdir -p "$PREFIX_DIR" "$CACHE_DIR" "$ROOT_DIR/.runtime"

if ! command -v uv >/dev/null 2>&1; then
  echo "[FAIL] uv 未安装，请先安装 uv 后再执行。"
  exit 1
fi

echo "[RUN] refresh egg-info metadata from README.md"
uv run python -m pip install \
  --ignore-installed \
  --no-deps \
  --editable "$ROOT_DIR" \
  --prefix "$PREFIX_DIR" \
  --cache-dir "$CACHE_DIR" \
  >"$LOG_PATH" 2>&1

LATEST_EGG_INFO="$(ls -td "$ROOT_DIR"/src/*.egg-info 2>/dev/null | head -n1 || true)"
PKG_INFO_PATH="${LATEST_EGG_INFO:-}/PKG-INFO"

if [ ! -f "$PKG_INFO_PATH" ]; then
  echo "[FAIL] missing $PKG_INFO_PATH"
  echo "See: $LOG_PATH"
  exit 1
fi

echo "[PASS] updated $PKG_INFO_PATH"
echo "Log: $LOG_PATH"
