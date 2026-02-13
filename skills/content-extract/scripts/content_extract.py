#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_search_stack.config import load_settings
from codex_search_stack.extract.pipeline import run_extract_pipeline
from codex_search_stack.validators import is_high_risk_host, validate_extract_protocol

WHITELIST_PATH = PROJECT_ROOT / "skills" / "content-extract" / "references" / "domain-whitelist.md"


def _load_whitelist() -> set[str]:
    out: set[str] = set()
    if not WHITELIST_PATH.exists():
        return out
    for line in WHITELIST_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("- `") and line.endswith("`"):
            out.add(line[3:-1].strip().lower())
    return out

def main() -> int:
    parser = argparse.ArgumentParser(description="Codex content-extract wrapper")
    parser.add_argument("--url", required=True)
    parser.add_argument("--force-mineru", action="store_true")
    parser.add_argument("--strategy", choices=["auto", "tavily_first", "mineru_first", "tavily_only", "mineru_only"], default="auto")
    parser.add_argument("--max-chars", type=int, default=20000)
    args = parser.parse_args()

    err, normalized = validate_extract_protocol(url=args.url, max_chars=args.max_chars, strategy=args.strategy)
    if err:
        parser.error(err)

    host = str(normalized.get("host", "")) if normalized else ""
    normalized_max_chars = int(normalized.get("max_chars", args.max_chars)) if normalized else args.max_chars
    normalized_strategy = str(normalized.get("strategy", args.strategy)) if normalized else args.strategy
    whitelist = _load_whitelist()
    forced_by_policy = is_high_risk_host(host, whitelist)
    force_mineru = bool(args.force_mineru or forced_by_policy)

    settings = load_settings()
    out = run_extract_pipeline(
        url=args.url,
        settings=settings,
        force_mineru=force_mineru,
        max_chars=normalized_max_chars,
        strategy=normalized_strategy,
    )

    payload = out.to_dict()
    payload_notes = list(payload.get("notes") or [])

    if forced_by_policy and not args.force_mineru:
        payload_notes.append("protocol_enforced:high_risk_domain_force_mineru")

    if not payload.get("sources"):
        payload["sources"] = [args.url]

    if not payload.get("ok"):
        payload_notes.append("next_step:check_keys_or_retry_with_force_mineru")

    payload["notes"] = payload_notes
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
