from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlparse

from ..config import Settings
from ..contracts import DecisionTrace, ExtractRequest

_DEFAULT_ANTI_BOT_DOMAINS = {
    "mp.weixin.qq.com",
    "zhuanlan.zhihu.com",
    "www.zhihu.com",
    "zhihu.com",
    "www.xiaohongshu.com",
    "xiaohongshu.com",
}
_SUPPORTED_STRATEGIES = {"auto", "tavily_first", "mineru_first", "tavily_only", "mineru_only"}


@dataclass
class ExtractPlan:
    strategy: str
    first_engine: str
    fallback_engine: str
    tavily_timeout: int
    notes: List[str] = field(default_factory=list)

    @property
    def try_tavily(self) -> bool:
        return self.first_engine == "tavily" or self.fallback_engine == "tavily"

    @property
    def try_mineru(self) -> bool:
        return self.first_engine == "mineru" or self.fallback_engine == "mineru"


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _anti_bot_domains(settings: Settings) -> set:
    extract_policy = (settings.policy or {}).get("extract", {})
    if not isinstance(extract_policy, dict):
        return set(_DEFAULT_ANTI_BOT_DOMAINS)
    domains = extract_policy.get("anti_bot_domains")
    if isinstance(domains, list):
        out = {(str(item).strip().lower()) for item in domains if str(item).strip()}
        if out:
            return out
    return set(_DEFAULT_ANTI_BOT_DOMAINS)


def _default_strategy(settings: Settings) -> str:
    extract_policy = (settings.policy or {}).get("extract", {})
    if not isinstance(extract_policy, dict):
        return "auto"
    value = extract_policy.get("default_strategy")
    if not isinstance(value, str):
        return "auto"
    normalized = value.strip().lower()
    if normalized in _SUPPORTED_STRATEGIES:
        return normalized
    return "auto"


def build_extract_plan(request: ExtractRequest, settings: Settings, trace: DecisionTrace) -> ExtractPlan:
    host = _host(request.url)
    anti_bot_domains = _anti_bot_domains(settings)
    is_anti_bot = host in anti_bot_domains

    strategy = (request.strategy or "").strip().lower()
    if strategy not in _SUPPORTED_STRATEGIES:
        strategy = _default_strategy(settings)
    if strategy not in _SUPPORTED_STRATEGIES:
        strategy = "auto"

    notes: List[str] = []
    if request.force_mineru:
        strategy = "mineru_only"
        notes.append("force_mineru:true")

    if strategy == "auto":
        if is_anti_bot:
            strategy = "mineru_only"
            notes.append("auto_strategy_anti_bot:mineru_only")
        else:
            strategy = "tavily_first"

    if strategy == "tavily_first":
        first_engine = "tavily"
        fallback_engine = "mineru"
    elif strategy == "mineru_first":
        first_engine = "mineru"
        fallback_engine = "tavily"
    elif strategy == "tavily_only":
        first_engine = "tavily"
        fallback_engine = ""
    else:
        first_engine = "mineru"
        fallback_engine = ""

    tavily_timeout = max(1, int(settings.extract_timeout_seconds))
    trace.add_event(
        stage="extract.policy",
        decision="extract_plan_selected",
        reason="request-level extract routing applied",
        metadata={
            "host": host,
            "anti_bot": str(is_anti_bot).lower(),
            "strategy": strategy,
            "first_engine": first_engine,
            "fallback_engine": fallback_engine or "none",
            "tavily_timeout": str(tavily_timeout),
        },
    )

    return ExtractPlan(
        strategy=strategy,
        first_engine=first_engine,
        fallback_engine=fallback_engine,
        tavily_timeout=tavily_timeout,
        notes=notes,
    )
