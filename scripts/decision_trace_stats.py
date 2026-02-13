#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_search_stack.config import load_settings  # noqa: E402
from codex_search_stack.observability import aggregate_decision_trace_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate persisted DecisionTrace JSONL")
    parser.add_argument("--path", default="", help="DecisionTrace JSONL path (default from config)")
    parser.add_argument("--limit", type=int, default=5000, help="Scan latest N lines")
    args = parser.parse_args()

    settings = load_settings()
    trace_path = (args.path or "").strip() or settings.decision_trace_jsonl_path
    payload = aggregate_decision_trace_jsonl(path=trace_path, limit=max(1, int(args.limit)))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

