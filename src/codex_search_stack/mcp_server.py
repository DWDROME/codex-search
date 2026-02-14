import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .config import load_settings, resolve_config_path
from .github_explorer import render_markdown, run_github_explorer
from .github_explorer.artifacts import attach_book_to_result, persist_explore_artifacts
from .research import run_research_loop
from .search.orchestrator import run_multi_source_search
from .extract.pipeline import run_extract_pipeline
from .validators import (
    coerce_int,
    extract_anti_bot_domains,
    is_high_risk_host,
    split_domain_boost,
    validate_explore_protocol,
    validate_extract_protocol,
    validate_search_protocol,
)

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - optional runtime dependency
    FastMCP = None  # type: ignore


def _split_sources(raw: str) -> List[str]:
    if not raw:
        return ["auto"]
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return items or ["auto"]


def _json_output(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _error_output(code: str, message: str, details: Optional[Dict] = None) -> str:
    payload = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        payload["error"]["details"] = details
    return _json_output(payload)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


if FastMCP is not None:
    mcp = FastMCP("codex-search")

    @mcp.tool(
        name="search",
        description="多源搜索（Exa/Tavily/Grok）并返回结构化 JSON，支持 mode/intent/freshness 与请求级策略参数。",
    )
    def mcp_search(
        query: str,
        mode: str = "deep",
        intent: str = "",
        freshness: str = "",
        num: int = 5,
        domain_boost: str = "",
        sources: str = "auto",
        model: str = "",
        model_profile: str = "strong",
        risk_level: str = "medium",
        budget_max_calls: int = 6,
        budget_max_tokens: int = 12000,
        budget_max_latency_ms: int = 30000,
    ) -> str:
        normalized_intent = (intent or "").strip().lower()
        normalized_freshness = (freshness or "").strip().lower()
        normalized_mode = (mode or "deep").strip().lower()
        normalized_num = coerce_int(num, 5)
        max_calls = coerce_int(budget_max_calls, 6)
        max_tokens = coerce_int(budget_max_tokens, 12000)
        max_latency_ms = coerce_int(budget_max_latency_ms, 30000)
        domains = split_domain_boost(domain_boost)
        err, details = validate_search_protocol(
            queries=[query],
            intent=normalized_intent,
            freshness=normalized_freshness,
            num=normalized_num,
            domains=domains,
            comparison_queries=1,
            comparison_error_message="comparison intent requires multi-query skill flow; use skills/search-layer/scripts/search.py with --queries",
            time_signal_error_message="time-sensitive query requires freshness",
        )
        if err:
            return _error_output(code="invalid_arguments", message=err, details=details)
        settings = load_settings()
        result = run_multi_source_search(
            query=query,
            settings=settings,
            mode=normalized_mode,
            limit=max(1, normalized_num),
            intent=normalized_intent or None,
            freshness=normalized_freshness or None,
            boost_domains=domains,
            sources=_split_sources(sources),
            model=(model or "").strip() or None,
            model_profile=(model_profile or "strong").strip().lower(),
            risk_level=(risk_level or "medium").strip().lower(),
            budget_max_calls=max(1, max_calls),
            budget_max_tokens=max(1, max_tokens),
            budget_max_latency_ms=max(1000, max_latency_ms),
        )
        return _json_output(result.to_dict())

    @mcp.tool(
        name="extract",
        description="URL 内容提取（Tavily + MinerU 策略路由），返回结构化 JSON，可用于反爬站点兜底。",
    )
    def mcp_extract(
        url: str,
        force_mineru: bool = False,
        max_chars: int = 20000,
        strategy: str = "auto",
    ) -> str:
        err, normalized = validate_extract_protocol(url=url, max_chars=max_chars, strategy=strategy)
        if err:
            return _error_output(code="invalid_arguments", message=err)
        normalized = normalized or {}
        settings = load_settings()
        host = str(normalized.get("host", ""))
        anti_bot_domains = extract_anti_bot_domains(getattr(settings, "policy", {}))
        if is_high_risk_host(host, anti_bot_domains):
            force_mineru = True
        result = run_extract_pipeline(
            url=url,
            settings=settings,
            force_mineru=force_mineru,
            max_chars=int(normalized.get("max_chars", 20000)),
            strategy=str(normalized.get("strategy", "auto")),
        )
        payload = result.to_dict()
        if not payload.get("sources"):
            payload["sources"] = [url]
        return _json_output(payload)

    @mcp.tool(
        name="explore",
        description="GitHub 项目解析与尽调，支持 JSON/Markdown 输出，并可自动产出 report/book 资料包。",
    )
    def mcp_explore(
        target: str,
        issues: int = 5,
        commits: int = 5,
        external_num: int = 8,
        extract_top: int = 2,
        with_extract: bool = True,
        confidence_profile: str = "",
        output_format: str = "json",
        with_artifacts: bool = True,
        out_dir: str = "",
        book_max: int = 5,
        download_book: bool = True,
    ) -> str:
        err, normalized = validate_explore_protocol(
            issues=issues,
            commits=commits,
            external_num=external_num,
            extract_top=extract_top,
            output_format=output_format,
        )
        if err:
            return _error_output("invalid_arguments", err)
        normalized = normalized or {}
        settings = load_settings()
        result = run_github_explorer(
            target=target,
            settings=settings,
            issues_limit=max(1, int(normalized.get("issues", 5))),
            commits_limit=max(1, int(normalized.get("commits", 5))),
            external_limit=max(1, int(normalized.get("external_num", 8))),
            extract_top=max(0, int(normalized.get("extract_top", 2))),
            with_extract=with_extract,
            confidence_profile=(confidence_profile or settings.confidence_profile).strip().lower(),
        )
        if result.get("ok"):
            attach_book_to_result(result, settings=settings, max_items=max(0, coerce_int(book_max, 5)))

        markdown_text = render_markdown(result)
        artifacts = None
        if with_artifacts:
            artifacts = persist_explore_artifacts(
                result=result,
                markdown_text=markdown_text,
                project_root=_PROJECT_ROOT,
                out_dir=out_dir or "",
                download_book=download_book,
                timeout=max(10, int(getattr(settings, "extract_timeout_seconds", 30) or 30)),
            )
            result["artifacts"] = artifacts

        if str(normalized.get("output_format", "json")) == "markdown":
            if artifacts:
                markdown_text += "\n\n**📁 输出目录**\n\n"
                markdown_text += "- %s\n" % artifacts.get("out_dir", "")
                markdown_text += "- book_downloaded=%s\n" % artifacts.get("book_downloaded", 0)
                markdown_text += "- book_download_failed=%s\n" % artifacts.get("book_download_failed", 0)
            return markdown_text
        return _json_output(result)

    @mcp.tool(
        name="research",
        description="多轮研究闭环（search -> extract -> critique -> follow-up），返回可追溯 JSON。",
    )
    def mcp_research(
        query: str,
        mode: str = "deep",
        intent: str = "",
        freshness: str = "",
        num: int = 6,
        domain_boost: str = "",
        model_profile: str = "strong",
        max_rounds: int = 3,
        extract_per_round: int = 2,
        extract_max_chars: int = 1600,
        extract_strategy: str = "auto",
    ) -> str:
        normalized_intent = (intent or "").strip().lower()
        normalized_freshness = (freshness or "").strip().lower()
        normalized_mode = (mode or "deep").strip().lower()
        normalized_num = coerce_int(num, 6)
        domains = split_domain_boost(domain_boost)
        err, details = validate_search_protocol(
            queries=[query],
            intent=normalized_intent,
            freshness=normalized_freshness,
            num=normalized_num,
            domains=domains,
            comparison_queries=1,
            comparison_error_message="research tool expects single query; comparison use search-layer --queries",
            time_signal_error_message="time-sensitive query requires freshness",
        )
        if err:
            return _error_output(code="invalid_arguments", message=err, details=details)
        settings = load_settings()
        payload = run_research_loop(
            query=query,
            settings=settings,
            mode=normalized_mode,
            intent=normalized_intent or None,
            freshness=normalized_freshness or None,
            limit=max(1, normalized_num),
            domain_boost=domains,
            model_profile=(model_profile or "strong").strip().lower(),
            max_rounds=max(1, coerce_int(max_rounds, 3)),
            extract_per_round=max(0, coerce_int(extract_per_round, 2)),
            extract_max_chars=max(200, coerce_int(extract_max_chars, 1600)),
            extract_strategy=(extract_strategy or "auto").strip().lower(),
        )
        return _json_output(payload)

    @mcp.tool(
        name="get_config_info",
        description="读取当前生效配置（脱敏）并返回各能力就绪状态。",
    )
    def mcp_get_config_info() -> str:
        settings = load_settings()

        def masked(value: str) -> str:
            if not value:
                return ""
            if len(value) <= 8:
                return "***"
            return value[:4] + "*" * (len(value) - 8) + value[-4:]

        payload = {
            "config_path": str(resolve_config_path()),
            "readiness": {
                "search": bool(settings.exa_api_key or (settings.grok_api_key and settings.grok_api_url) or settings.tavily_api_key),
                "extract": bool(settings.mineru_token or settings.tavily_api_key),
                "explore": True,
            },
            "search": {
                "exa_api_key": masked(settings.exa_api_key or ""),
                "grok_api_url": settings.grok_api_url or "",
                "grok_api_key": masked(settings.grok_api_key or ""),
                "grok_model": settings.grok_model,
                "tavily_api_url": settings.tavily_api_url or "",
                "tavily_api_key": masked(settings.tavily_api_key or ""),
            },
            "extract": {
                "mineru_api_base": settings.mineru_api_base,
                "mineru_token": masked(settings.mineru_token or ""),
                "mineru_workspace": settings.mineru_workspace or "",
            },
            "runtime": {
                "search_timeout_seconds": settings.search_timeout_seconds,
                "extract_timeout_seconds": settings.extract_timeout_seconds,
                "decision_trace_enabled": settings.decision_trace_enabled,
                "decision_trace_persist": settings.decision_trace_persist,
                "decision_trace_path": settings.decision_trace_jsonl_path,
            },
        }
        return _json_output(payload)


def main() -> int:
    if FastMCP is None:
        print(
            "mcp 依赖未安装（通常需要 Python>=3.10）。请先在 3.10+ 环境安装: python -m pip install \"mcp>=1.6.0\"",
            file=sys.stderr,
        )
        return 2
    mcp.run()  # type: ignore[name-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
