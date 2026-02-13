#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="${CI_REPORT_DIR:-$ROOT_DIR/.runtime/ci-reports}"
mkdir -p "$REPORT_DIR"

SNAPSHOT_FILE="$REPORT_DIR/masked_env_snapshot.json"
DECISION_FILE="$REPORT_DIR/ci_smoke_decision.json"
LOG_FILE="$REPORT_DIR/ci_smoke.log"
CONFIG_CHECK_FILE="$REPORT_DIR/config_check.json"

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

run_uv python "$ROOT_DIR/scripts/masked_env_snapshot.py" >"$SNAPSHOT_FILE"
echo "[info] masked env snapshot => $SNAPSHOT_FILE"

run_uv python "$ROOT_DIR/scripts/check_api_config.py" --json >"$CONFIG_CHECK_FILE"
echo "[info] api config check => $CONFIG_CHECK_FILE"

MODE="${CI_SMOKE_MODE:-auto}"
MODE="$(echo "$MODE" | tr '[:upper:]' '[:lower:]')"

read -r HAS_SEARCH_KEY HAS_EXTRACT_KEY <<EOF
$(run_uv python - "$CONFIG_CHECK_FILE" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
print(int(bool(payload.get("search_ready"))), int(bool(payload.get("extract_ready"))))
PY
)
EOF

ONLINE_READY=0
if [ "$HAS_SEARCH_KEY" -eq 1 ] && [ "$HAS_EXTRACT_KEY" -eq 1 ]; then
  ONLINE_READY=1
fi

RUN_MODE="offline"
if [ "$MODE" = "online" ]; then
  RUN_MODE="online"
elif [ "$MODE" = "offline" ]; then
  RUN_MODE="offline"
elif [ "$MODE" = "auto" ] && [ "$ONLINE_READY" -eq 1 ]; then
  RUN_MODE="online"
fi

cat >"$DECISION_FILE" <<JSON
{
  "mode_requested": "$MODE",
  "mode_selected": "$RUN_MODE",
  "online_ready": $ONLINE_READY,
  "has_search_key_or_pool": $HAS_SEARCH_KEY,
  "has_extract_key_or_token": $HAS_EXTRACT_KEY
}
JSON
echo "[info] smoke decision => $DECISION_FILE"

if [ "$RUN_MODE" = "online" ]; then
  echo "[run] online smoke"
  "$ROOT_DIR/scripts/smoke_phase6.sh" 2>&1 | tee "$LOG_FILE"
  exit "${PIPESTATUS[0]}"
fi

echo "[run] offline smoke (compile + cli help)"
{
  run_uv python -m compileall "$ROOT_DIR/src"
  run_uv python -m codex_search_stack.cli --help >/dev/null
  echo "offline smoke passed"
} 2>&1 | tee "$LOG_FILE"
