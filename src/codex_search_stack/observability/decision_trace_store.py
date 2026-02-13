import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..contracts import DecisionTrace, SearchResult


def _normalized_source(raw: str) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return ""
    if text in {"tavily", "tavily_extract"}:
        return "tavily"
    if text in {"grok", "grok_search"}:
        return "grok"
    if text in {"exa"}:
        return "exa"
    if text in {"mineru", "mineru_extract", "mineru_parse_documents"}:
        return "mineru"
    return text


def collect_search_source_hits(results: Iterable[SearchResult]) -> Dict[str, int]:
    hits: Dict[str, int] = {}
    for item in results:
        source = (item.source or "").strip()
        for raw in source.split(","):
            name = _normalized_source(raw)
            if not name:
                continue
            hits[name] = hits.get(name, 0) + 1
    return hits


def collect_extract_source_hits(engine: str) -> Dict[str, int]:
    name = _normalized_source(engine)
    if not name:
        return {}
    return {name: 1}


def persist_decision_trace_jsonl(
    *,
    trace: DecisionTrace,
    trace_kind: str,
    ok: bool,
    latency_ms: int,
    source_hits: Dict[str, int],
    path: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    target = Path(path).expanduser()
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": (trace_kind or "").strip().lower(),
        "ok": bool(ok),
        "latency_ms": max(0, int(latency_ms)),
        "source_hits": {k: int(v) for k, v in (source_hits or {}).items() if str(k).strip() and int(v) > 0},
        "metadata": metadata or {},
        "trace": trace.to_dict(),
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - filesystem edge cases
        return str(exc)
    return None


def _percentile(values: List[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(len(ordered) * p))
    return ordered[rank - 1]


def _metric(latencies: List[int], failures: int) -> Dict[str, Any]:
    total = len(latencies)
    success = max(0, total - failures)
    return {
        "total": total,
        "success": success,
        "failed": failures,
        "failure_rate": round((failures / total), 4) if total else 0.0,
        "latency_ms": {
            "avg": int(sum(latencies) / total) if total else 0,
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies) if latencies else 0,
        },
    }


def aggregate_decision_trace_jsonl(path: str, limit: int = 5000) -> Dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists():
        return {
            "path": str(target),
            "exists": False,
            "records_used": 0,
            "invalid_lines": 0,
            "window_limit": max(1, int(limit)),
            "overall": _metric([], 0),
            "by_kind": {},
            "source_hits": {},
            "time_range": {"first": "", "last": ""},
        }

    raw_lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    window = max(1, int(limit))
    lines = raw_lines[-window:]

    invalid = 0
    records: List[Dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            invalid += 1
            continue
        if isinstance(payload, dict):
            records.append(payload)
        else:
            invalid += 1

    overall_latencies: List[int] = []
    overall_failures = 0
    by_kind_latencies: Dict[str, List[int]] = {}
    by_kind_failures: Dict[str, int] = {}
    source_hits: Dict[str, int] = {}
    times: List[str] = []

    for row in records:
        latency = int(row.get("latency_ms") or 0)
        ok = bool(row.get("ok"))
        kind = str(row.get("kind") or "unknown").strip().lower() or "unknown"
        created_at = str(row.get("created_at") or "").strip()

        overall_latencies.append(latency)
        by_kind_latencies.setdefault(kind, []).append(latency)
        if not ok:
            overall_failures += 1
            by_kind_failures[kind] = by_kind_failures.get(kind, 0) + 1
        else:
            by_kind_failures.setdefault(kind, by_kind_failures.get(kind, 0))

        for name, count in (row.get("source_hits") or {}).items():
            key = _normalized_source(str(name))
            if not key:
                continue
            source_hits[key] = source_hits.get(key, 0) + int(count or 0)

        if created_at:
            times.append(created_at)

    by_kind = {
        kind: _metric(latencies, by_kind_failures.get(kind, 0))
        for kind, latencies in sorted(by_kind_latencies.items())
    }
    times_sorted = sorted(times)
    return {
        "path": str(target),
        "exists": True,
        "records_used": len(records),
        "invalid_lines": invalid,
        "window_limit": window,
        "overall": _metric(overall_latencies, overall_failures),
        "by_kind": by_kind,
        "source_hits": dict(sorted(source_hits.items(), key=lambda item: (-item[1], item[0]))),
        "time_range": {
            "first": times_sorted[0] if times_sorted else "",
            "last": times_sorted[-1] if times_sorted else "",
        },
    }

