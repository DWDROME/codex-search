from typing import Dict, List, Optional
import time

import requests

from ..config import Settings
from ..contracts import DecisionTrace, ExtractRequest, ExtractionArtifacts, ExtractionResponse
from ..key_pool import build_service_candidates, mask_key
from ..observability import collect_extract_source_hits, persist_decision_trace_jsonl
from ..policy import build_extract_plan
from .mineru_adapter import run_mineru_wrapper

def _is_content_usable(markdown: Optional[str]) -> bool:
    if not markdown:
        return False
    text = markdown.strip()
    if len(text) < 400:
        return False
    # Only inspect the beginning of content to avoid false negatives
    # when normal articles mention words like "captcha".
    head = text[:1200].lower()
    bad_signals = [
        "environment abnormal",
        "请在微信客户端打开",
        "verify you are human",
        "access denied",
        "security verification",
        "complete the captcha",
    ]
    return not any(s in head for s in bad_signals)


def _extract_via_tavily_once(url: str, api_url: str, api_key: str, timeout: int) -> ExtractionResponse:
    endpoint = api_url.rstrip("/") + "/extract"
    payload: Dict = {
        "urls": [url],
        "api_key": api_key,
        "extract_depth": "advanced",
        "format": "markdown",
        "include_favicon": True,
    }
    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    results = data.get("results") or []
    if not results:
        return ExtractionResponse(
            ok=False,
            source_url=url,
            engine="tavily_extract",
            notes=["tavily_no_results"],
            sources=[url],
        )

    first = results[0]
    raw = first.get("raw_content") or ""
    if not _is_content_usable(raw):
        return ExtractionResponse(
            ok=False,
            source_url=url,
            engine="tavily_extract",
            markdown=raw,
            notes=["tavily_content_not_usable"],
            sources=[url],
        )

    return ExtractionResponse(
        ok=True,
        source_url=url,
        engine="tavily_extract",
        markdown=raw,
        artifacts=ExtractionArtifacts(),
        sources=[url],
        notes=["primary:tavily_extract"],
    )


def run_extract_pipeline(
    url: str,
    settings: Settings,
    force_mineru: bool = False,
    max_chars: int = 20000,
    strategy: str = "auto",
) -> ExtractionResponse:
    started_at = time.perf_counter()
    request = ExtractRequest(
        url=url,
        force_mineru=force_mineru,
        max_chars=max_chars,
        strategy=strategy,
    )
    trace = DecisionTrace()
    trace.add_event(
        stage="extract.request",
        decision="request_received",
        reason="entry from extract pipeline",
        metadata={
            "url_len": str(len(url)),
            "force_mineru": str(force_mineru).lower(),
            "strategy": strategy,
        },
    )
    plan = build_extract_plan(request, settings, trace)

    notes: List[str] = []
    notes.extend(plan.notes)

    def run_tavily_route() -> ExtractionResponse:
        candidates = build_service_candidates(
            service="tavily",
            primary_url=settings.tavily_api_url,
            primary_key=settings.tavily_api_key,
            pool_file=settings.key_pool_file,
            pool_enabled=settings.key_pool_enabled,
        )
        trace.add_event(
            stage="extract.execute",
            decision="try_tavily",
            reason="tavily extract route selected",
            metadata={
                "candidate_count": str(len(candidates)),
                "timeout": str(plan.tavily_timeout),
            },
        )

        if not candidates:
            return ExtractionResponse(
                ok=False,
                source_url=url,
                engine="tavily_extract",
                notes=["missing_tavily_api_key"],
                sources=[url],
            )

        primary = ExtractionResponse(
            ok=False,
            source_url=url,
            engine="tavily_extract",
            notes=[],
            sources=[url],
        )
        for idx, candidate in enumerate(candidates, start=1):
            try:
                attempt = _extract_via_tavily_once(
                    url=url,
                    api_url=candidate.url,
                    api_key=candidate.key,
                    timeout=plan.tavily_timeout,
                )
            except Exception as exc:
                primary.notes.append("tavily_candidate_failed:%s:%s" % (mask_key(candidate.key), exc))
                continue

            if attempt.ok:
                if idx > 1:
                    attempt.notes.append("tavily_pool_rotated:%s" % mask_key(candidate.key))
                return attempt

            primary = attempt
            primary.notes.append("tavily_candidate:%s" % mask_key(candidate.key))
            if "tavily_content_not_usable" in (attempt.notes or []):
                break
        return primary

    def run_mineru_route() -> ExtractionResponse:
        trace.add_event(
            stage="extract.execute",
            decision="try_mineru",
            reason="mineru route selected",
            metadata={"max_chars": str(max_chars)},
        )
        return run_mineru_wrapper(
            url=url,
            wrapper_path=settings.mineru_wrapper_path,
            token=settings.mineru_token,
            api_base=settings.mineru_api_base,
            workspace=settings.mineru_workspace,
            max_chars=max_chars,
            language="ch",
            model_version="MinerU-HTML",
        )

    def finalize(response: ExtractionResponse) -> ExtractionResponse:
        response.notes = list(notes)
        if settings.decision_trace_enabled:
            trace.add_event(
                stage="extract.response",
                decision="response_ready",
                reason="extract pipeline finished",
                metadata={
                    "ok": str(response.ok).lower(),
                    "engine": response.engine,
                    "note_count": str(len(response.notes)),
                },
            )
            response.decision_trace = trace
            if settings.decision_trace_persist and response.decision_trace is not None:
                error = persist_decision_trace_jsonl(
                    trace=response.decision_trace,
                    trace_kind="extract",
                    ok=response.ok,
                    latency_ms=int((time.perf_counter() - started_at) * 1000),
                    source_hits=collect_extract_source_hits(response.engine),
                    path=settings.decision_trace_jsonl_path,
                    metadata={
                        "strategy": strategy,
                        "force_mineru": str(force_mineru).lower(),
                    },
                )
                if error:
                    response.notes.append("decision_trace_persist_failed:%s" % error)
        return response

    if plan.first_engine == "tavily":
        first = run_tavily_route()
        notes.extend(first.notes or [])
        if first.ok or not plan.fallback_engine:
            return finalize(first)
        if plan.fallback_engine == "mineru":
            trace.add_event(
                stage="extract.execute",
                decision="fallback_triggered",
                reason="primary engine failed",
                metadata={"from": "tavily", "to": "mineru"},
            )
            second = run_mineru_route()
            notes.extend(second.notes or [])
            return finalize(second)
        return finalize(first)

    first = run_mineru_route()
    notes.extend(first.notes or [])
    if first.ok or not plan.fallback_engine:
        return finalize(first)
    if plan.fallback_engine == "tavily":
        trace.add_event(
            stage="extract.execute",
            decision="fallback_triggered",
            reason="primary engine failed",
            metadata={"from": "mineru", "to": "tavily"},
        )
        second = run_tavily_route()
        notes.extend(second.notes or [])
        return finalize(second)
    return finalize(first)
