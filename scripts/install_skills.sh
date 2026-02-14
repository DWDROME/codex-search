#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
TARGET_ROOT="$CODEX_HOME/skills/codex-search"

mkdir -p "$TARGET_ROOT"

for skill in search-layer content-extract mineru-extract github-explorer api-availability git-workflow; do
  ln -sfn "$PROJECT_ROOT/skills/$skill" "$TARGET_ROOT/$skill"
  echo "linked: $TARGET_ROOT/$skill -> $PROJECT_ROOT/skills/$skill"
done

echo "done. you can now use skills under: $TARGET_ROOT"
