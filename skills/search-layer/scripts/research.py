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
from codex_search_stack.research import run_research_loop
from codex_search_stack.validators import split_domain_boost, validate_search_protocol


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex search-layer research loop wrapper")
    parser.add_argument("query")
    parser.add_argument("--mode", choices=["fast", "deep", "answer"], default="deep")
    parser.add_argument(
        "--intent",
        choices=["factual", "status", "comparison", "tutorial", "exploratory", "news", "resource"],
        default="exploratory",
    )
    parser.add_argument("--freshness", choices=["pd", "pw", "pm", "py"], default="")
    parser.add_argument("--num", type=int, default=6)
    parser.add_argument("--domain-boost", default="")
    parser.add_argument("--model-profile", choices=["cheap", "balanced", "strong"], default="strong")
    parser.add_argument(
        "--protocol",
        choices=["codex_research_v1", "legacy"],
        default="codex_research_v1",
        help="默认 codex_research_v1（固定四轮）；legacy 为旧自适应流程。",
    )
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--extract-per-round", type=int, default=2)
    parser.add_argument("--extract-max-chars", type=int, default=1600)
    parser.add_argument(
        "--extract-strategy",
        choices=["auto", "tavily_first", "mineru_first", "tavily_only", "mineru_only"],
        default="auto",
    )

    args = parser.parse_args()
    domains = split_domain_boost(args.domain_boost)
    err, details = validate_search_protocol(
        queries=[args.query],
        intent=(args.intent or "").strip().lower(),
        freshness=(args.freshness or "").strip().lower(),
        num=args.num,
        domains=domains,
        comparison_queries=1,
        comparison_error_message="research wrapper expects single query",
        time_signal_error_message="time-sensitive query detected; please set --freshness (pd|pw|pm|py)",
    )
    if err:
        if err == "invalid domain_boost values" and details:
            parser.error("invalid --domain-boost value(s): %s" % ", ".join(details.get("invalid_domains", [])))
        if err == "intent status/news requires freshness":
            parser.error("--intent status/news requires --freshness (pd|pw|pm|py)")
        parser.error(err)

    settings = load_settings()
    payload = run_research_loop(
        query=args.query,
        settings=settings,
        mode=args.mode,
        intent=args.intent,
        freshness=(args.freshness or None),
        limit=max(1, int(args.num)),
        domain_boost=domains,
        model_profile=args.model_profile,
        max_rounds=max(1, int(args.max_rounds)),
        extract_per_round=max(0, int(args.extract_per_round)),
        extract_max_chars=max(200, int(args.extract_max_chars)),
        extract_strategy=args.extract_strategy,
        protocol=args.protocol,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
