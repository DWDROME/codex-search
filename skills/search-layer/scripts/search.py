#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_search_stack.config import load_settings
from codex_search_stack.search.orchestrator import run_multi_source_search
from codex_search_stack.search.scoring import normalize_url
from codex_search_stack.validators import split_domain_boost, validate_search_protocol


def _merge_results(per_query: List[Dict], topk: int) -> List[Dict]:
    merged: List[Dict] = []
    seen = set()
    for block in per_query:
        for row in block.get("results", []):
            key = normalize_url(row.get("url", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged[:topk]


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex search-layer wrapper")
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--queries", nargs="+")
    parser.add_argument("--mode", choices=["fast", "deep", "answer"], default="deep")
    parser.add_argument(
        "--intent",
        choices=["factual", "status", "comparison", "tutorial", "exploratory", "news", "resource"],
    )
    parser.add_argument("--freshness", choices=["pd", "pw", "pm", "py"])
    parser.add_argument("--num", type=int, default=5)
    parser.add_argument("--domain-boost", default="")

    args = parser.parse_args()
    queries = list(args.queries or [])
    if args.query:
        queries.append(args.query)
    if not queries:
        parser.error("Provide query or --queries")

    domains = split_domain_boost(args.domain_boost)
    err, details = validate_search_protocol(
        queries=queries,
        intent=(args.intent or "").strip().lower(),
        freshness=(args.freshness or "").strip().lower(),
        num=args.num,
        domains=domains,
        comparison_queries=len(queries),
        comparison_error_message="comparison intent requires --queries with at least 2 sub-queries",
        time_signal_error_message="time-sensitive query detected; please set --freshness (pd|pw|pm|py)",
    )
    if err:
        if err == "invalid domain_boost values" and details:
            parser.error("invalid --domain-boost value(s): %s" % ", ".join(details.get("invalid_domains", [])))
        if err == "intent status/news requires freshness":
            parser.error("--intent status/news requires --freshness (pd|pw|pm|py)")
        parser.error(err)

    settings = load_settings()

    per_query: List[Dict] = []
    all_notes: List[str] = []

    for q in queries:
        out = run_multi_source_search(
            query=q,
            settings=settings,
            mode=args.mode,
            limit=max(args.num, 1),
            intent=args.intent,
            freshness=args.freshness,
            boost_domains=domains,
        )
        payload = out.to_dict()
        per_query.append(payload)
        all_notes.extend(payload.get("notes", []))

    merged = _merge_results(per_query, topk=max(args.num, 1))
    if not merged:
        all_notes.append("protocol_hint:no_results_try_adjust_intent_freshness_or_mode")

    result = {
        "ok": True,
        "mode": args.mode,
        "intent": args.intent,
        "freshness": args.freshness,
        "queries": queries,
        "count": len(merged),
        "results": merged,
        "per_query": per_query,
        "notes": all_notes,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
