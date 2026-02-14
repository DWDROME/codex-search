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
    validate_explore_protocol,
    validate_extract_protocol,
    validate_search_protocol,
)

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - optional runtime dependency
    FastMCP = None  # type: ignore


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
        description="多源搜索（Exa/Tavily/Grok）并返回结构化 JSON（对外最小参数面）。",
    )
    def mcp_search(
        query: str,
        mode: str = "deep",
        intent: str = "",
        freshness: str = "",
        num: int = 5,
    ) -> str:
        normalized_intent = (intent or "").strip().lower()
        normalized_freshness = (freshness or "").strip().lower()
        normalized_mode = (mode or "deep").strip().lower()
        normalized_num = coerce_int(num, 5)
        domains: List[str] = []
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
            sources=["auto"],
            model=None,
            model_profile="strong",
            risk_level="medium",
            budget_max_calls=6,
            budget_max_tokens=12000,
            budget_max_latency_ms=30000,
        )
        return _json_output(result.to_dict())

    @mcp.tool(
        name="extract",
        description="URL 内容提取（Tavily + MinerU 策略路由），返回结构化 JSON（对外最小参数面）。",
    )
    def mcp_extract(
        url: str,
        strategy: str = "auto",
        max_chars: int = 20000,
    ) -> str:
        err, normalized = validate_extract_protocol(url=url, max_chars=max_chars, strategy=strategy)
        if err:
            return _error_output(code="invalid_arguments", message=err)
        normalized = normalized or {}
        settings = load_settings()
        host = str(normalized.get("host", ""))
        anti_bot_domains = extract_anti_bot_domains(getattr(settings, "policy", {}))
        force_mineru = False
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
        description="GitHub 项目解析与尽调（对外最小参数面）。",
    )
    def mcp_explore(
        target: str,
        output_format: str = "json",
        with_artifacts: bool = True,
    ) -> str:
        err, normalized = validate_explore_protocol(
            issues=5,
            commits=5,
            external_num=8,
            extract_top=2,
            output_format=output_format,
        )
        if err:
            return _error_output("invalid_arguments", err)
        normalized = normalized or {}
        settings = load_settings()
        result = run_github_explorer(
            target=target,
            settings=settings,
            issues_limit=5,
            commits_limit=5,
            external_limit=8,
            extract_top=2,
            with_extract=True,
            confidence_profile=settings.confidence_profile,
        )
        if result.get("ok"):
            attach_book_to_result(result, settings=settings, max_items=5)

        markdown_text = render_markdown(result)
        artifacts = None
        if with_artifacts:
            artifacts = persist_explore_artifacts(
                result=result,
                markdown_text=markdown_text,
                project_root=_PROJECT_ROOT,
                out_dir="",
                download_book=True,
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
        description="多轮研究闭环（search-layer 内部高级模式）。",
    )
    def mcp_research(
        query: str,
        intent: str = "",
        freshness: str = "",
        num: int = 6,
        max_rounds: int = 3,
        protocol: str = "codex_research_v1",
    ) -> str:
        normalized_intent = (intent or "").strip().lower()
        normalized_freshness = (freshness or "").strip().lower()
        normalized_num = coerce_int(num, 6)
        normalized_max_rounds = coerce_int(max_rounds, 3)
        if normalized_max_rounds < 1 or normalized_max_rounds > 8:
            return _error_output(
                code="invalid_arguments",
                message="max_rounds must be between 1 and 8",
            )
        domains: List[str] = []
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
            mode="deep",
            intent=normalized_intent or None,
            freshness=normalized_freshness or None,
            limit=max(1, normalized_num),
            domain_boost=domains,
            model_profile="strong",
            max_rounds=normalized_max_rounds,
            extract_per_round=2,
            extract_max_chars=1600,
            extract_strategy="auto",
            protocol=(protocol or "codex_research_v1").strip().lower(),
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
