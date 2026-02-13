import argparse
import json
from typing import List

from .config import load_settings
from .extract.pipeline import run_extract_pipeline
from .github_explorer import render_markdown, run_github_explorer
from .observability import aggregate_decision_trace_jsonl
from .search.orchestrator import run_multi_source_search


def _split_domains(raw: str) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]

def _split_sources(raw: str) -> List[str]:
    if not raw:
        return ["auto"]
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return items or ["auto"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex-first multi-source search and extraction stack")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Run multi-source search")
    search.add_argument("query")
    search.add_argument("--mode", choices=["fast", "deep", "answer"], default="deep")
    search.add_argument("--intent", choices=["factual", "status", "comparison", "tutorial", "exploratory", "news", "resource"])
    search.add_argument("--freshness", choices=["pd", "pw", "pm", "py"])
    search.add_argument("--num", type=int, default=5)
    search.add_argument("--domain-boost", default="")
    search.add_argument("--sources", default="auto", help="auto 或 exa,tavily,grok")
    search.add_argument("--model", default="", help="请求级显式模型，优先级高于 profile")
    search.add_argument("--model-profile", choices=["cheap", "balanced", "strong"], default="balanced")
    search.add_argument("--risk-level", choices=["low", "medium", "high"], default="medium")
    search.add_argument("--budget-max-calls", type=int, default=6)
    search.add_argument("--budget-max-tokens", type=int, default=12000)
    search.add_argument("--budget-max-latency-ms", type=int, default=30000)

    extract = sub.add_parser("extract", help="Run extraction pipeline")
    extract.add_argument("url")
    extract.add_argument("--force-mineru", action="store_true")
    extract.add_argument("--max-chars", type=int, default=20000)
    extract.add_argument(
        "--strategy",
        choices=["auto", "tavily_first", "mineru_first", "tavily_only", "mineru_only"],
        default="auto",
    )

    explore = sub.add_parser("explore", help="Run GitHub explorer workflow")
    explore.add_argument("target", help="GitHub URL, owner/repo, or project name")
    explore.add_argument("--issues", type=int, default=5)
    explore.add_argument("--commits", type=int, default=5)
    explore.add_argument("--external-num", type=int, default=8)
    explore.add_argument("--extract-top", type=int, default=2)
    explore.add_argument("--no-extract", action="store_true")
    explore.add_argument("--confidence-profile", choices=["deep", "quick"])
    explore.add_argument("--format", choices=["markdown", "json"], default="markdown")

    trace_stats = sub.add_parser("trace-stats", help="Aggregate persisted DecisionTrace JSONL")
    trace_stats.add_argument("--path", default="", help="DecisionTrace JSONL path (default from config)")
    trace_stats.add_argument("--limit", type=int, default=5000, help="Scan latest N lines")
    trace_stats.add_argument("--format", choices=["json"], default="json")

    args = parser.parse_args()
    settings = load_settings()

    if args.command == "search":
        result = run_multi_source_search(
            query=args.query,
            settings=settings,
            mode=args.mode,
            limit=args.num,
            intent=args.intent,
            freshness=args.freshness,
            boost_domains=_split_domains(args.domain_boost),
            sources=_split_sources(args.sources),
            model=args.model,
            model_profile=args.model_profile,
            risk_level=args.risk_level,
            budget_max_calls=args.budget_max_calls,
            budget_max_tokens=args.budget_max_tokens,
            budget_max_latency_ms=args.budget_max_latency_ms,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "extract":
        result = run_extract_pipeline(
            url=args.url,
            settings=settings,
            force_mineru=args.force_mineru,
            max_chars=args.max_chars,
            strategy=args.strategy,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "explore":
        result = run_github_explorer(
            target=args.target,
            settings=settings,
            issues_limit=max(args.issues, 1),
            commits_limit=max(args.commits, 1),
            external_limit=max(args.external_num, 1),
            extract_top=max(args.extract_top, 0),
            with_extract=not args.no_extract,
            confidence_profile=(args.confidence_profile or settings.confidence_profile),
        )
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_markdown(result))
        return 0

    if args.command == "trace-stats":
        result = aggregate_decision_trace_jsonl(
            path=(args.path or "").strip() or settings.decision_trace_jsonl_path,
            limit=max(1, int(args.limit)),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
