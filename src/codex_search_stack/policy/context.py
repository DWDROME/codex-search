from dataclasses import dataclass, field
from typing import List

from ..contracts import SearchRequest

_SUPPORTED_MODES = {"fast", "deep", "answer"}
_SUPPORTED_RISK = {"low", "medium", "high"}
_SUPPORTED_MODEL_PROFILE = {"cheap", "balanced", "strong"}
_SUPPORTED_SOURCES = {"exa", "tavily", "grok", "auto"}


@dataclass
class SearchContext:
    query: str
    mode: str
    intent: str
    freshness: str
    risk_level: str
    model_profile: str
    requested_sources: List[str] = field(default_factory=lambda: ["auto"])
    limit: int = 5


def _clean_sources(sources: List[str]) -> List[str]:
    out: List[str] = []
    for item in sources:
        raw = (item or "").strip().lower()
        if not raw:
            continue
        if raw not in _SUPPORTED_SOURCES:
            continue
        if raw not in out:
            out.append(raw)
    if not out:
        return ["auto"]
    return out


def build_search_context(request: SearchRequest) -> SearchContext:
    mode = (request.mode or "deep").strip().lower()
    if mode not in _SUPPORTED_MODES:
        mode = "deep"

    risk_level = (request.risk_level or "medium").strip().lower()
    if risk_level not in _SUPPORTED_RISK:
        risk_level = "medium"

    model_profile = (request.model_profile or "balanced").strip().lower()
    if model_profile not in _SUPPORTED_MODEL_PROFILE:
        model_profile = "balanced"

    sources = _clean_sources(request.sources or ["auto"])

    return SearchContext(
        query=request.query,
        mode=mode,
        intent=(request.intent or "").strip().lower(),
        freshness=(request.freshness or "").strip().lower(),
        risk_level=risk_level,
        model_profile=model_profile,
        requested_sources=sources,
        limit=max(1, int(request.limit or 5)),
    )
