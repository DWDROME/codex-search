import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from ..config import Settings
from ..contracts import DecisionTrace, SearchResult
from ..extract.pipeline import run_extract_pipeline
from ..observability import collect_extract_source_hits, collect_search_source_hits, persist_decision_trace_jsonl
from ..search.orchestrator import run_multi_source_search
from ..search.scoring import normalize_url

_OFFICIAL_HOST_HINTS = [
    "github.com",
    "docs.",
    "developer.",
    "readthedocs.io",
    "arxiv.org",
]


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _trim(text: str, limit: int) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 3)] + "..."


def _is_official_like(host: str) -> bool:
    if not host:
        return False
    if any(token in host for token in _OFFICIAL_HOST_HINTS):
        return True
    return host.endswith(".org") or host.endswith(".edu")


def _merge_result(existing: Dict, item: SearchResult, round_idx: int) -> Dict:
    if not existing:
        return {
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet,
            "source": item.source,
            "published_date": item.published_date,
            "score": item.score if item.score is not None else 0.0,
            "first_seen_round": round_idx,
            "seen_count": 1,
        }
    existing["seen_count"] = int(existing.get("seen_count", 1)) + 1
    prior_source = str(existing.get("source") or "")
    if item.source and (item.source not in prior_source.split(",")):
        existing["source"] = ",".join([token for token in [prior_source, item.source] if token])
    prior_score = float(existing.get("score") or 0.0)
    if (item.score is not None) and float(item.score) > prior_score:
        existing["score"] = float(item.score)
        if item.title:
            existing["title"] = item.title
        if item.snippet:
            existing["snippet"] = item.snippet
        if item.published_date:
            existing["published_date"] = item.published_date
    elif not existing.get("published_date") and item.published_date:
        existing["published_date"] = item.published_date
    return existing


def _build_followup_query(
    *,
    base_query: str,
    intent: str,
    total_results: int,
    hosts: Set[str],
    has_recent: bool,
    has_arxiv: bool,
    asked: Set[str],
) -> Optional[str]:
    intent_key = (intent or "").strip().lower()
    now_year = datetime.now().year
    if total_results < 5:
        candidate = "%s official docs tutorial examples" % base_query
        if candidate not in asked:
            return candidate
    if intent_key in {"status", "news"} and not has_recent:
        candidate = "%s latest update %s changelog release notes" % (base_query, now_year)
        if candidate not in asked:
            return candidate
    if any("paper" in token for token in base_query.lower().split()) and not has_arxiv:
        candidate = "%s arxiv paper pdf" % base_query
        if candidate not in asked:
            return candidate
    if hosts and not any(_is_official_like(host) for host in hosts):
        candidate = '%s site:github.com OR site:arxiv.org OR site:docs.*' % base_query
        if candidate not in asked:
            return candidate
    return None


def run_research_loop(
    *,
    query: str,
    settings: Settings,
    mode: str = "deep",
    intent: Optional[str] = None,
    freshness: Optional[str] = None,
    limit: int = 6,
    domain_boost: Optional[List[str]] = None,
    model_profile: str = "strong",
    max_rounds: int = 3,
    extract_per_round: int = 2,
    extract_max_chars: int = 1600,
    extract_strategy: str = "auto",
) -> Dict:
    started_at = time.perf_counter()
    trace = DecisionTrace(policy_version="policy.research.v1")
    trace.add_event(
        stage="research.request",
        decision="request_received",
        reason="entry from research orchestrator",
        metadata={
            "mode": mode,
            "intent": (intent or "").strip().lower(),
            "freshness": (freshness or "").strip().lower(),
            "max_rounds": str(max_rounds),
            "extract_per_round": str(extract_per_round),
            "model_profile": model_profile,
        },
    )

    rounds: List[Dict] = []
    notes: List[str] = []
    evidence: Dict[str, Dict] = {}
    extracts: Dict[str, Dict] = {}
    asked_queries: Set[str] = set()
    current_query = (query or "").strip()
    stop_reason = "max_rounds_reached"

    for round_idx in range(1, max(1, int(max_rounds)) + 1):
        asked_queries.add(current_query)
        trace.add_event(
            stage="research.round",
            decision="search_started",
            reason="execute multi-source search",
            metadata={"round": str(round_idx), "query": current_query},
        )
        out = run_multi_source_search(
            query=current_query,
            settings=settings,
            mode=mode,
            limit=max(1, int(limit)),
            intent=intent,
            freshness=freshness,
            boost_domains=domain_boost or [],
            model_profile=model_profile,
            budget_max_calls=6,
            budget_max_tokens=12000,
            budget_max_latency_ms=max(1000, int(getattr(settings, "search_timeout_seconds", 60) or 60) * 3000),
        )

        round_notes = list(out.notes or [])
        notes.extend(round_notes)
        before_count = len(evidence)
        new_urls: List[str] = []
        for row in out.results:
            key = normalize_url(row.url or "")
            if not key:
                continue
            prior = evidence.get(key, {})
            evidence[key] = _merge_result(prior, row, round_idx)
            if not prior:
                new_urls.append(key)
        added_count = len(evidence) - before_count

        extract_results: List[Dict] = []
        if extract_per_round > 0:
            extract_targets = new_urls[: max(0, int(extract_per_round))]
            if not extract_targets:
                missing = [k for k in evidence.keys() if k not in extracts]
                extract_targets = missing[: max(0, int(extract_per_round))]
            for key in extract_targets:
                url = evidence.get(key, {}).get("url", "")
                if not url:
                    continue
                ex = run_extract_pipeline(
                    url=url,
                    settings=settings,
                    max_chars=max(200, int(extract_max_chars)),
                    strategy=extract_strategy,
                )
                extracts[key] = {
                    "url": url,
                    "ok": bool(ex.ok),
                    "engine": ex.engine,
                    "notes": list(ex.notes or []),
                    "summary": _trim(ex.markdown or "", 320),
                }
                extract_results.append(extracts[key])
                round_notes.extend(ex.notes or [])

        hosts = {_host(item.get("url", "")) for item in evidence.values()}
        has_recent = any(bool(item.get("published_date")) for item in evidence.values())
        has_arxiv = any("arxiv.org" in host for host in hosts if host)
        followup_query = _build_followup_query(
            base_query=query,
            intent=(intent or ""),
            total_results=len(evidence),
            hosts={h for h in hosts if h},
            has_recent=has_recent,
            has_arxiv=has_arxiv,
            asked=asked_queries,
        )
        gap_tags: List[str] = []
        if len(evidence) < 5:
            gap_tags.append("low_coverage")
        if ((intent or "").strip().lower() in {"status", "news"}) and not has_recent:
            gap_tags.append("missing_recency")
        if not any(_is_official_like(host) for host in hosts if host):
            gap_tags.append("missing_official")
        if ("paper" in query.lower()) and not has_arxiv:
            gap_tags.append("missing_paper")
        if not gap_tags:
            gap_tags.append("none")

        rounds.append(
            {
                "round": round_idx,
                "query": current_query,
                "result_count": len(out.results),
                "new_result_count": added_count,
                "sources": sorted({(item.source or "").strip() for item in out.results if (item.source or "").strip()}),
                "notes": round_notes,
                "gaps": gap_tags,
                "followup_query": followup_query or "",
                "extracts": extract_results,
            }
        )
        trace.add_event(
            stage="research.round",
            decision="round_completed",
            reason="search + extract + critique",
            metadata={
                "round": str(round_idx),
                "new_results": str(added_count),
                "gaps": ",".join(gap_tags),
                "has_followup": str(bool(followup_query)).lower(),
            },
        )

        if not followup_query:
            stop_reason = "no_more_gap"
            break
        current_query = followup_query
    else:
        stop_reason = "max_rounds_reached"

    ordered = sorted(
        evidence.values(),
        key=lambda item: (
            float(item.get("score") or 0.0),
            int(item.get("seen_count") or 0),
            -int(item.get("first_seen_round") or 999),
        ),
        reverse=True,
    )
    final_results = ordered[: max(1, int(limit))]
    final_results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "source": item.get("source", ""),
            "published_date": item.get("published_date", ""),
            "score": item.get("score", 0.0),
            "first_seen_round": item.get("first_seen_round", 0),
            "seen_count": item.get("seen_count", 0),
            "extract": extracts.get(normalize_url(item.get("url", "")), {}),
        }
        for item in final_results
    ]

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    trace.add_event(
        stage="research.response",
        decision="response_built",
        reason="research loop completed",
        metadata={
            "rounds": str(len(rounds)),
            "total_results": str(len(evidence)),
            "final_count": str(len(final_results)),
            "stop_reason": stop_reason,
        },
    )

    if getattr(settings, "decision_trace_persist", False):
        search_hits = collect_search_source_hits(
            [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    source=item.get("source", ""),
                    published_date=item.get("published_date", ""),
                    score=item.get("score"),
                )
                for item in final_results
            ]
        )
        extract_hits: Dict[str, int] = {}
        for item in extracts.values():
            one = collect_extract_source_hits(item.get("engine", ""))
            for name, count in one.items():
                extract_hits[name] = extract_hits.get(name, 0) + int(count)
        source_hits = dict(search_hits)
        for name, count in extract_hits.items():
            source_hits[name] = source_hits.get(name, 0) + count
        persist_err = persist_decision_trace_jsonl(
            trace=trace,
            trace_kind="research",
            ok=True,
            latency_ms=latency_ms,
            source_hits=source_hits,
            path=str(getattr(settings, "decision_trace_jsonl_path", "./.runtime/decision-trace/decision_trace.jsonl")),
            metadata={"query": query, "rounds": len(rounds), "stop_reason": stop_reason},
        )
        if persist_err:
            notes.append("decision_trace_persist_failed:%s" % persist_err)

    payload = {
        "ok": True,
        "query": query,
        "mode": mode,
        "intent": intent,
        "freshness": freshness,
        "max_rounds": max(1, int(max_rounds)),
        "stop_reason": stop_reason,
        "round_count": len(rounds),
        "rounds": rounds,
        "count": len(final_results),
        "results": final_results,
        "notes": notes,
    }
    if getattr(settings, "decision_trace_enabled", True):
        payload["decision_trace"] = trace.to_dict()
    return payload

