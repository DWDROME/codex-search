#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="${CODEX_SEARCH_CONFIG:-$ROOT_DIR/config/config.yaml}"

export CODEX_SEARCH_CONFIG="$CONFIG_FILE"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export CODEX_WORKSPACE="${CODEX_WORKSPACE:-$ROOT_DIR/.runtime/codex-workspace}"
export MINERU_WORKSPACE="${MINERU_WORKSPACE:-$CODEX_WORKSPACE}"

if ! command -v uv >/dev/null 2>&1; then
  echo "[FAIL] uv 未安装，请先安装 uv 后再执行。"
  exit 1
fi

run_uv() {
  (cd "$ROOT_DIR" && uv run "$@")
}

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[FAIL] missing config file: $CONFIG_FILE"
  exit 1
fi

if [ -z "${MINERU_TOKEN:-}" ]; then
  MINERU_TOKEN_FROM_CONFIG="$(
    run_uv python - "$CONFIG_FILE" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except Exception:
    print("")
    raise SystemExit(0)

cfg_path = Path(sys.argv[1])
try:
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
except Exception:
    print("")
    raise SystemExit(0)

token = (
    cfg.get("extract", {})
    .get("mineru", {})
    .get("token", "")
)
print(token or "")
PY
  )"
  if [ -n "$MINERU_TOKEN_FROM_CONFIG" ]; then
    export MINERU_TOKEN="$MINERU_TOKEN_FROM_CONFIG"
  fi
fi

run_json_step() {
  local name="$1"
  shift

  local out_file
  out_file="$(mktemp)"
  local err_file
  err_file="$(mktemp)"

  echo "[RUN] $name"
  if "$@" >"$out_file" 2>"$err_file"; then
    if run_uv python - "$name" "$out_file" <<'PY'
import json
import sys
from pathlib import Path

name = sys.argv[1]
payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

if name == "search-layer":
    assert payload.get("ok") is True, "search-layer: ok != true"
    assert isinstance(payload.get("results"), list), "search-layer: missing results"
    assert int(payload.get("count", 0)) >= 1, "search-layer: count < 1"
elif name == "content-extract":
    assert payload.get("ok") is True, "content-extract: ok != true"
    assert payload.get("engine"), "content-extract: missing engine"
elif name == "github-explorer":
    assert payload.get("ok") is True, "github-explorer: ok != true"
    repo = payload.get("repo") or {}
    assert repo.get("full_name"), "github-explorer: missing repo full_name"
elif name == "mineru-extract":
    assert payload.get("ok") is True, "mineru-extract: ok != true"
    assert len(payload.get("items") or []) >= 1, "mineru-extract: no items"
else:
    raise AssertionError(f"unknown step: {name}")
print("verified")
PY
    then
      echo "[PASS] $name"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "[FAIL] $name (json verify failed)"
      sed -n "1,40p" "$out_file"
      FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
  else
    echo "[FAIL] $name"
    sed -n "1,40p" "$err_file"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  rm -f "$out_file" "$err_file"
}

run_json_step \
  "search-layer" \
  run_uv python "$ROOT_DIR/skills/search-layer/scripts/search.py" "OpenAI Codex 最新更新" --mode deep --intent status --freshness pw --num 2

run_json_step \
  "content-extract" \
  run_uv python "$ROOT_DIR/skills/content-extract/scripts/content_extract.py" --url "https://platform.openai.com/docs/guides/tools-web-search" --max-chars 800

run_json_step \
  "github-explorer" \
  run_uv python "$ROOT_DIR/skills/github-explorer/scripts/explore.py" "openai/codex" --format json --no-extract --issues 5 --commits 5 --external-num 3

if [ -n "${MINERU_TOKEN:-}" ]; then
  run_json_step \
    "mineru-extract" \
    run_uv python "$ROOT_DIR/skills/mineru-extract/scripts/mineru_parse_documents.py" --file-sources "https://zhuanlan.zhihu.com/p/619438846" --model-version MinerU-HTML --emit-markdown --max-chars 800
else
  echo "[SKIP] mineru-extract (MINERU_TOKEN is empty)"
  SKIP_COUNT=$((SKIP_COUNT + 1))
fi

echo
echo "===== Skill Smoke Summary ====="
echo "PASS: $PASS_COUNT"
echo "FAIL: $FAIL_COUNT"
echo "SKIP: $SKIP_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
