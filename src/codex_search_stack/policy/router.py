from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..config import Settings
from ..contracts import DecisionTrace, SearchRequest
from .context import SearchContext

_DEFAULT_MODE_SOURCES = {
    "fast": ["exa", "grok"],
    "deep": ["exa", "tavily", "grok"],
    "answer": ["tavily"],
}

_PROFILE_DEFAULTS = {
    "cheap": "grok-4.1-fast",
    "balanced": "grok-4.1",
    "strong": "grok-4.1-thinking",
}


def _dedupe_sources(items: List[str]) -> List[str]:
    out: List[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


@dataclass
class SearchPlan:
    mode: str
    model: str
    include_answer: bool
    use_exa: bool
    use_tavily: bool
    use_grok: bool
    source_order: List[str] = field(default_factory=list)
    source_timeouts: Dict[str, int] = field(default_factory=dict)
    max_workers: int = 3
    notes: List[str] = field(default_factory=list)


def _policy_model_map(settings: Settings) -> Dict[str, str]:
    models = (settings.policy or {}).get("models", {})
    grok_cfg = models.get("grok", {}) if isinstance(models, dict) else {}
    if not isinstance(grok_cfg, dict):
        return dict(_PROFILE_DEFAULTS)

    profiles = grok_cfg.get("profiles", {})
    out = dict(_PROFILE_DEFAULTS)
    if isinstance(profiles, dict):
        for key, value in profiles.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            out[key.strip().lower()] = value.strip()
    return out


def _default_model(settings: Settings) -> str:
    models = (settings.policy or {}).get("models", {})
    grok_cfg = models.get("grok", {}) if isinstance(models, dict) else {}
    if isinstance(grok_cfg, dict):
        value = (grok_cfg.get("default") or "").strip() if isinstance(grok_cfg.get("default"), str) else ""
        if value:
            return value
    return settings.grok_model


def _requested_sources(context: SearchContext, settings: Settings) -> List[str]:
    if context.requested_sources and "auto" not in context.requested_sources:
        return [item for item in context.requested_sources if item != "auto"]

    routing = (settings.policy or {}).get("routing", {})
    by_mode = routing.get("by_mode", {}) if isinstance(routing, dict) else {}
    candidate = by_mode.get(context.mode) if isinstance(by_mode, dict) else None
    if isinstance(candidate, list):
        values = [str(item).strip().lower() for item in candidate if str(item).strip()]
        if values:
            return values
    return list(_DEFAULT_MODE_SOURCES.get(context.mode, _DEFAULT_MODE_SOURCES["deep"]))


def build_search_plan(
    request: SearchRequest,
    context: SearchContext,
    settings: Settings,
    trace: DecisionTrace,
) -> SearchPlan:
    profile_map = _policy_model_map(settings)
    default_model = _default_model(settings)
    model = (request.model or "").strip() or profile_map.get(context.model_profile, default_model) or default_model

    sources = _requested_sources(context, settings)
    has_exa = bool(settings.exa_api_key)
    has_tavily = bool(settings.tavily_api_key)
    has_grok = bool(settings.grok_api_key and settings.grok_api_url)

    allowed = _dedupe_sources([source for source in sources if source in {"exa", "tavily", "grok"}])
    notes: List[str] = []
    if "grok" not in allowed:
        allowed.append("grok")
        notes.append("policy_source_forced:grok_required")

    use_exa = "exa" in allowed and has_exa
    use_tavily = "tavily" in allowed and has_tavily
    use_grok = "grok" in allowed and has_grok

    if "exa" in allowed and not has_exa:
        notes.append("policy_source_unavailable:exa")
    if "tavily" in allowed and not has_tavily:
        notes.append("policy_source_unavailable:tavily")
    if "grok" in allowed and not has_grok:
        notes.append("policy_source_unavailable:grok")
        notes.append("policy_source_required_unavailable:grok")

    if context.mode == "answer" and not use_tavily:
        notes.append("answer_mode_without_tavily")

    source_order: List[str] = []
    for source in allowed:
        if source == "exa" and use_exa:
            source_order.append(source)
        if source == "tavily" and use_tavily:
            source_order.append(source)
        if source == "grok" and use_grok:
            source_order.append(source)

    if context.mode == "fast" and not source_order and has_grok:
        use_grok = True
        source_order = ["grok"]
        notes.append("fast_mode_fallback:grok")

    if request.budget.max_calls > 0 and len(source_order) > request.budget.max_calls:
        source_order = source_order[: request.budget.max_calls]
        if "grok" in allowed and has_grok and "grok" not in source_order:
            if source_order:
                source_order[-1] = "grok"
            else:
                source_order = ["grok"]
            source_order = _dedupe_sources(source_order)
            notes.append("budget_trimmed_sources_preserve:grok")
        use_exa = "exa" in source_order
        use_tavily = "tavily" in source_order
        use_grok = "grok" in source_order
        notes.append("budget_trimmed_sources:max_calls")

    base_timeout = max(1, int(settings.search_timeout_seconds))
    source_timeouts: Dict[str, int] = {}
    if source_order:
        per_source_ms = max(1000, int(request.budget.max_latency_ms) // max(1, len(source_order)))
        per_source_timeout = max(1, per_source_ms // 1000)
        timeout_value = min(base_timeout, per_source_timeout)
        for source in source_order:
            source_timeouts[source] = timeout_value

    include_answer = context.mode == "answer"
    max_workers = max(1, min(len(source_order), 3, max(1, request.budget.max_calls)))

    trace.add_event(
        stage="policy.context",
        decision="request_normalized",
        reason="normalized mode/sources/model_profile for routing",
        metadata={
            "mode": context.mode,
            "intent": context.intent,
            "risk_level": context.risk_level,
            "model_profile": context.model_profile,
            "requested_sources": ",".join(context.requested_sources),
            "budget_max_calls": str(request.budget.max_calls),
            "budget_max_tokens": str(request.budget.max_tokens),
            "budget_max_latency_ms": str(request.budget.max_latency_ms),
        },
    )
    trace.add_event(
        stage="policy.router",
        decision="search_plan_selected",
        reason="request-level routing applied",
        metadata={
            "model": model,
            "sources": ",".join(source_order) or "none",
            "include_answer": str(include_answer).lower(),
            "max_workers": str(max_workers),
            "source_timeouts": ",".join("%s:%s" % (k, v) for k, v in source_timeouts.items()) or "none",
        },
    )

    return SearchPlan(
        mode=context.mode,
        model=model,
        include_answer=include_answer,
        use_exa=use_exa,
        use_tavily=use_tavily,
        use_grok=use_grok,
        source_order=source_order,
        source_timeouts=source_timeouts,
        max_workers=max_workers,
        notes=notes,
    )
