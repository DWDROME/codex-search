from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Dict, Iterable, List, Optional, Tuple

from ..config import Settings
from ..contracts import DecisionTrace, SearchRequest, SearchResponse, SearchResult
from ..key_pool import build_service_candidates, mask_key
from ..observability import collect_search_source_hits, persist_decision_trace_jsonl
from ..policy import build_search_context, build_search_plan
from .scoring import composite_score, normalize_url
from .sources import search_exa, search_grok, search_tavily


def _dedup(results: List[Dict]) -> List[Dict]:
    seen: Dict[str, Dict] = {}
    ordered: List[Dict] = []
    for item in results:
        key = normalize_url(item.get("url", ""))
        if key not in seen:
            seen[key] = item
            ordered.append(item)
        else:
            current_sources = seen[key].get("source", "")
            source = item.get("source", "")
            if source and source not in current_sources:
                seen[key]["source"] = current_sources + "," + source
    return ordered


def _execute_single_query(
    request: SearchRequest,
    settings: Settings,
    trace: DecisionTrace,
) -> Tuple[List[Dict], Optional[str], List[str]]:
    context = build_search_context(request)
    plan = build_search_plan(request, context, settings, trace)

    query = context.query
    mode = plan.mode
    limit = context.limit
    freshness = context.freshness or None
    notes: List[str] = []
    results: List[Dict] = []
    answer: Optional[str] = None
    notes.extend(plan.notes)
    if plan.source_timeouts:
        notes.append(
            "budget_timeout_applied:%s"
            % ",".join("%s:%s" % (name, timeout) for name, timeout in plan.source_timeouts.items())
        )

    grok_candidates = build_service_candidates(
        service="grok",
        primary_url=settings.grok_api_url,
        primary_key=settings.grok_api_key,
        pool_file=settings.key_pool_file,
        pool_enabled=settings.key_pool_enabled,
    )
    tavily_candidates = build_service_candidates(
        service="tavily",
        primary_url=settings.tavily_api_url,
        primary_key=settings.tavily_api_key,
        pool_file=settings.key_pool_file,
        pool_enabled=settings.key_pool_enabled,
    )

    def run_grok_with_pool() -> Tuple[List[Dict], List[str]]:
        local_notes: List[str] = []
        grok_timeout = plan.source_timeouts.get("grok", settings.search_timeout_seconds)
        for idx, candidate in enumerate(grok_candidates, start=1):
            try:
                rows = search_grok(
                    query,
                    candidate.url,
                    candidate.key,
                    plan.model,
                    limit,
                    grok_timeout,
                    freshness,
                )
                if idx > 1:
                    local_notes.append("grok_pool_rotated:%s" % mask_key(candidate.key))
                return rows, local_notes
            except Exception as exc:
                local_notes.append("grok_candidate_failed:%s:%s" % (mask_key(candidate.key), exc))
        return [], local_notes

    def run_tavily_with_pool(include_answer: bool) -> Tuple[Dict, List[str]]:
        local_notes: List[str] = []
        tavily_timeout = plan.source_timeouts.get("tavily", settings.search_timeout_seconds)
        for idx, candidate in enumerate(tavily_candidates, start=1):
            try:
                payload = search_tavily(
                    query,
                    candidate.key,
                    candidate.url,
                    limit,
                    tavily_timeout,
                    include_answer,
                    freshness,
                )
                if idx > 1:
                    local_notes.append("tavily_pool_rotated:%s" % mask_key(candidate.key))
                return payload, local_notes
            except Exception as exc:
                local_notes.append("tavily_candidate_failed:%s:%s" % (mask_key(candidate.key), exc))
        return {"results": [], "answer": None}, local_notes

    if mode == "fast":
        exa_timeout = plan.source_timeouts.get("exa", settings.search_timeout_seconds)
        if plan.use_exa and settings.exa_api_key:
            try:
                results.extend(search_exa(query, settings.exa_api_key, limit, exa_timeout))
            except Exception as exc:
                notes.append("exa_failed:%s" % exc)
        elif plan.use_grok and grok_candidates:
            rows, grok_notes = run_grok_with_pool()
            results.extend(rows)
            notes.extend(grok_notes)
        else:
            notes.append("no_source_available_for_fast")

    elif mode in ("deep", "answer"):
        with ThreadPoolExecutor(max_workers=plan.max_workers) as pool:
            futures = {}
            exa_timeout = plan.source_timeouts.get("exa", settings.search_timeout_seconds)
            if mode == "deep" and plan.use_exa and settings.exa_api_key:
                futures[pool.submit(search_exa, query, settings.exa_api_key, limit, exa_timeout)] = "exa"
            if plan.use_tavily and tavily_candidates:
                futures[pool.submit(run_tavily_with_pool, plan.include_answer)] = "tavily"
            if mode == "deep" and plan.use_grok and grok_candidates:
                futures[pool.submit(run_grok_with_pool)] = "grok"

            for future in as_completed(futures):
                source_name = futures[future]
                try:
                    output = future.result()
                    if source_name == "tavily":
                        payload, local_notes = output
                        notes.extend(local_notes)
                        results.extend(payload.get("results", []))
                        if payload.get("answer") and not answer:
                            answer = payload["answer"]
                    elif source_name == "grok":
                        payload, local_notes = output
                        notes.extend(local_notes)
                        results.extend(payload)
                    elif isinstance(output, dict):
                        results.extend(output.get("results", []))
                        if output.get("answer") and not answer:
                            answer = output["answer"]
                    else:
                        results.extend(output)
                except Exception as exc:
                    notes.append("%s_failed:%s" % (source_name, exc))

        if not futures:
            notes.append("no_source_available_for_mode_%s" % mode)

    else:
        notes.append("unknown_mode:%s" % mode)

    trace.add_event(
        stage="search.execute",
        decision="source_execution_done",
        reason="all source workers completed",
        metadata={
            "result_count_raw": str(len(results)),
            "answer_present": str(bool(answer)).lower(),
            "note_count": str(len(notes)),
        },
    )
    return results, answer, notes


def run_multi_source_search(
    query: str,
    settings: Settings,
    mode: str = "deep",
    limit: int = 5,
    intent: Optional[str] = None,
    freshness: Optional[str] = None,
    boost_domains: Optional[Iterable[str]] = None,
    sources: Optional[Iterable[str]] = None,
    model: Optional[str] = None,
    model_profile: str = "balanced",
    risk_level: str = "medium",
    budget_max_calls: int = 6,
    budget_max_tokens: int = 12000,
    budget_max_latency_ms: int = 30000,
) -> SearchResponse:
    started_at = time.perf_counter()
    boost = [d.strip() for d in (boost_domains or []) if d.strip()]
    request = SearchRequest(
        query=query,
        mode=mode,
        intent=intent,
        freshness=freshness,
        limit=limit,
        boost_domains=boost,
        sources=[item.strip().lower() for item in (sources or ["auto"]) if str(item).strip()],
        model=(model or "").strip() or None,
        model_profile=model_profile,
        risk_level=risk_level,
    )
    request.budget.max_calls = max(1, int(budget_max_calls))
    request.budget.max_tokens = max(1, int(budget_max_tokens))
    request.budget.max_latency_ms = max(1000, int(budget_max_latency_ms))
    trace = DecisionTrace()
    trace.add_event(
        stage="search.request",
        decision="request_received",
        reason="entry from orchestrator",
        metadata={
            "query_len": str(len(query)),
            "mode": request.mode,
            "intent": request.intent or "",
            "freshness": request.freshness or "",
        },
    )

    raw, answer, notes = _execute_single_query(request, settings, trace)
    deduped = _dedup(raw)
    trace.add_event(
        stage="search.postprocess",
        decision="dedup_completed",
        reason="normalized URL dedup finished",
        metadata={
            "raw_count": str(len(raw)),
            "dedup_count": str(len(deduped)),
        },
    )

    items: List[SearchResult] = []
    for row in deduped:
        score = None
        if intent:
            score = composite_score(
                query=query,
                intent=intent,
                url=row.get("url", ""),
                title=row.get("title", ""),
                snippet=row.get("snippet", ""),
                published_date=row.get("published_date", ""),
                boost_domains=boost,
            )
        items.append(
            SearchResult(
                title=row.get("title", ""),
                url=row.get("url", ""),
                snippet=row.get("snippet", ""),
                source=row.get("source", ""),
                published_date=row.get("published_date", ""),
                score=score,
            )
        )

    if intent:
        items.sort(key=lambda x: x.score if x.score is not None else -1.0, reverse=True)
        trace.add_event(
            stage="search.rank",
            decision="intent_scoring_applied",
            reason="intent was provided",
            metadata={"intent": intent},
        )

    response = SearchResponse(
        mode=mode,
        query=query,
        intent=intent,
        freshness=freshness,
        count=len(items),
        results=items,
        answer=answer,
        notes=notes,
        decision_trace=trace if settings.decision_trace_enabled else None,
    )
    if settings.decision_trace_enabled:
        trace.add_event(
            stage="search.response",
            decision="response_ready",
            reason="serialized response prepared",
            metadata={"count": str(response.count)},
        )
        if settings.decision_trace_persist and response.decision_trace is not None:
            error = persist_decision_trace_jsonl(
                trace=response.decision_trace,
                trace_kind="search",
                ok=bool(response.count > 0 or response.answer),
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                source_hits=collect_search_source_hits(response.results),
                path=settings.decision_trace_jsonl_path,
                metadata={
                    "mode": mode,
                    "intent": intent or "",
                    "freshness": freshness or "",
                },
            )
            if error:
                response.notes.append("decision_trace_persist_failed:%s" % error)
    return response
