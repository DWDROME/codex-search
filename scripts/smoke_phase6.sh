#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export CODEX_WORKSPACE="${CODEX_WORKSPACE:-$ROOT_DIR/.runtime/codex-workspace}"
export MINERU_WORKSPACE="${MINERU_WORKSPACE:-$CODEX_WORKSPACE}"

PASS_COUNT=0
FAIL_COUNT=0

run_step() {
  local name="$1"
  shift

  local out_file
  out_file="$(mktemp)"
  local err_file
  err_file="$(mktemp)"

  echo "[RUN] $name"
  if "$@" >"$out_file" 2>"$err_file"; then
    echo "[PASS] $name"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "[FAIL] $name"
    sed -n "1,30p" "$err_file"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  rm -f "$out_file" "$err_file"
}

run_json_step() {
  local name="$1"
  local verify_py="$2"
  shift 2

  local out_file
  out_file="$(mktemp)"
  local err_file
  err_file="$(mktemp)"

  echo "[RUN] $name"
  if "$@" >"$out_file" 2>"$err_file"; then
    if python3 - "$out_file" <<PY
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
$verify_py
print("verified")
PY
    then
      echo "[PASS] $name"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "[FAIL] $name (json verify failed)"
      sed -n "1,30p" "$out_file"
      FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
  else
    echo "[FAIL] $name"
    sed -n "1,30p" "$err_file"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  rm -f "$out_file" "$err_file"
}

run_step "compileall" python3 -m compileall "$ROOT_DIR/src"
run_step "cli_help" python3 -m codex_search_stack.cli --help

run_json_step \
  "search_deep" \
  'assert isinstance(payload.get("results"), list), "missing results"' \
  python3 -m codex_search_stack.cli search "codex 多源搜索 号池 回退" --mode deep --intent exploratory --num 3

run_json_step \
  "extract_basic" \
  'assert payload.get("ok") is True, "extract not ok"; assert payload.get("engine"), "missing engine"' \
  python3 -m codex_search_stack.cli extract "https://en.wikipedia.org/wiki/Web_scraping" --max-chars 2000

run_json_step \
  "explore_json" \
  'assert payload.get("ok") is True, "explore not ok"; conf = payload.get("confidence") or {}; assert isinstance(conf.get("score"), int), "missing confidence score"; assert conf.get("level") in {"高", "中", "低"}, "invalid confidence level"; assert conf.get("profile") in {"deep", "quick"}, "invalid confidence profile"' \
  python3 -m codex_search_stack.cli explore "microsoft/graphrag" --issues 3 --commits 3 --external-num 4 --extract-top 1 --format json

run_json_step \
  "explore_json_quick_profile" \
  'assert payload.get("ok") is True, "explore not ok"; conf = payload.get("confidence") or {}; assert conf.get("profile") == "quick", "profile not quick"' \
  python3 -m codex_search_stack.cli explore "microsoft/graphrag" --issues 3 --commits 3 --external-num 4 --extract-top 1 --confidence-profile quick --format json

run_step \
  "explore_markdown" \
  bash -lc 'python3 -m codex_search_stack.cli explore "microsoft/graphrag" --issues 3 --commits 3 --external-num 4 --extract-top 1 --confidence-profile quick --format markdown | grep -q "profile=quick"'

echo
echo "===== Smoke Summary ====="
echo "PASS: $PASS_COUNT"
echo "FAIL: $FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
