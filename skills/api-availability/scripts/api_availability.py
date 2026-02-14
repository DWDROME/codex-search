#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_search_stack.config import load_settings, resolve_config_path  # noqa: E402
from codex_search_stack.search.sources import search_exa, search_grok, search_tavily  # noqa: E402


def _mask(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "(empty)"
    if len(raw) <= 12:
        return "***"
    return "%s...%s" % (raw[:8], raw[-4:])


def _probe_exa(settings: Any, query: str, timeout: int, live: bool) -> Dict[str, Any]:
    key = (settings.exa_api_key or "").strip()
    if not key:
        return {"configured": False, "status": "missing_config"}
    if not live:
        return {"configured": True, "status": "skipped"}
    start = time.perf_counter()
    try:
        rows = search_exa(query, key, 1, timeout)
        return {
            "configured": True,
            "status": "ok",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "result_count": len(rows),
        }
    except Exception as exc:
        return {
            "configured": True,
            "status": "error",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }


def _probe_tavily(settings: Any, query: str, timeout: int, live: bool) -> Dict[str, Any]:
    key = (settings.tavily_api_key or "").strip()
    url = (settings.tavily_api_url or "").strip()
    if not key or not url:
        return {"configured": False, "status": "missing_config"}
    if not live:
        return {"configured": True, "status": "skipped"}
    start = time.perf_counter()
    try:
        payload = search_tavily(query, key, url, 1, timeout, False, None)
        return {
            "configured": True,
            "status": "ok",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "result_count": len(payload.get("results", [])),
        }
    except requests.HTTPError as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        status = "auth_failed" if code in {401, 403} else "error"
        return {
            "configured": True,
            "status": status,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "configured": True,
            "status": "error",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }


def _probe_grok(settings: Any, query: str, timeout: int, live: bool) -> Dict[str, Any]:
    key = (settings.grok_api_key or "").strip()
    url = (settings.grok_api_url or "").strip()
    model = (settings.grok_model or "").strip()
    if not key or not url:
        return {"configured": False, "status": "missing_config"}
    if not live:
        return {"configured": True, "status": "skipped"}
    start = time.perf_counter()
    try:
        rows = search_grok(query, url, key, model or "grok-4.1-thinking", 1, timeout, None)
        return {
            "configured": True,
            "status": "ok",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "result_count": len(rows),
        }
    except requests.HTTPError as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        status = "auth_failed" if code in {401, 403} else "error"
        return {
            "configured": True,
            "status": status,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "configured": True,
            "status": "error",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }


def _probe_github(settings: Any, timeout: int, live: bool) -> Dict[str, Any]:
    token = (settings.github_token or "").strip()
    configured = bool(token)
    if not live:
        return {"configured": configured, "status": "skipped" if configured else "missing_config"}
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codex-search-api-availability",
    }
    if token:
        headers["Authorization"] = "Bearer %s" % token
    start = time.perf_counter()
    try:
        resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=timeout)
        latency = int((time.perf_counter() - start) * 1000)
        if resp.status_code == 200:
            payload = resp.json()
            core = ((payload.get("resources") or {}).get("core") or {})
            status = "ok" if token else "ok_unauthenticated"
            return {
                "configured": configured,
                "status": status,
                "latency_ms": latency,
                "rate_limit_remaining": core.get("remaining"),
            }
        if resp.status_code in {401, 403}:
            return {
                "configured": configured,
                "status": "auth_failed",
                "latency_ms": latency,
                "error": "github_status_%s" % resp.status_code,
            }
        return {
            "configured": configured,
            "status": "error",
            "latency_ms": latency,
            "error": "github_status_%s" % resp.status_code,
        }
    except Exception as exc:
        return {
            "configured": configured,
            "status": "error",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }


def _probe_mineru(settings: Any, timeout: int, live: bool) -> Dict[str, Any]:
    token = (settings.mineru_token or "").strip()
    base = (settings.mineru_api_base or "").strip()
    configured = bool(token and base)
    if not configured:
        return {"configured": False, "status": "missing_config"}
    if not live:
        return {"configured": True, "status": "skipped"}
    url = base.rstrip("/") + "/api/v4/extract/task/not-a-real-task-id"
    start = time.perf_counter()
    try:
        resp = requests.get(
            url,
            headers={
                "Authorization": "Bearer %s" % token,
                "Accept": "application/json",
                "User-Agent": "codex-search-api-availability",
            },
            timeout=timeout,
        )
        latency = int((time.perf_counter() - start) * 1000)
        if resp.status_code in {200, 400, 404}:
            return {"configured": True, "status": "ok", "latency_ms": latency}
        if resp.status_code in {401, 403}:
            return {
                "configured": True,
                "status": "auth_failed",
                "latency_ms": latency,
                "error": "mineru_status_%s" % resp.status_code,
            }
        return {
            "configured": True,
            "status": "error",
            "latency_ms": latency,
            "error": "mineru_status_%s" % resp.status_code,
        }
    except Exception as exc:
        return {
            "configured": True,
            "status": "error",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }


def _build_report(*, live: bool, query: str, timeout: int) -> Dict[str, Any]:
    settings = load_settings()
    config_path = resolve_config_path()

    services = {
        "exa": _probe_exa(settings, query, timeout, live),
        "tavily": _probe_tavily(settings, query, timeout, live),
        "grok": _probe_grok(settings, query, timeout, live),
        "github": _probe_github(settings, timeout, live),
        "mineru": _probe_mineru(settings, timeout, live),
    }

    summary = {"ok": 0, "failed": 0, "skipped": 0, "missing_config": 0, "configured_services": 0, "bad_configured": 0}
    for payload in services.values():
        status = payload.get("status", "")
        configured = bool(payload.get("configured"))
        if configured:
            summary["configured_services"] += 1
        if status == "ok" or status == "ok_unauthenticated":
            summary["ok"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
        elif status == "missing_config":
            summary["missing_config"] += 1
        else:
            summary["failed"] += 1
            if configured:
                summary["bad_configured"] += 1

    readiness = {
        "search": bool((settings.exa_api_key or "").strip() or (settings.grok_api_key or "").strip() or (settings.tavily_api_key or "").strip()),
        "extract": bool((settings.tavily_api_key or "").strip() or (settings.mineru_token or "").strip()),
        "explore": True,
    }

    return {
        "ok": True,
        "live_probe": bool(live),
        "query": query,
        "config": {
            "config_path": str(config_path),
            "config_exists": config_path.exists(),
            "readiness": readiness,
            "masked": {
                "EXA_API_KEY": _mask(settings.exa_api_key or ""),
                "TAVILY_API_KEY": _mask(settings.tavily_api_key or ""),
                "GROK_API_KEY": _mask(settings.grok_api_key or ""),
                "GROK_API_URL": settings.grok_api_url or "(empty)",
                "GROK_MODEL": settings.grok_model or "(empty)",
                "GITHUB_TOKEN": _mask(settings.github_token or ""),
                "MINERU_TOKEN": _mask(settings.mineru_token or ""),
                "MINERU_API_BASE": settings.mineru_api_base or "(empty)",
            },
        },
        "services": services,
        "summary": summary,
    }


def _print_text(report: Dict[str, Any]) -> None:
    print("=== codex-search API 可用性体检 ===")
    print("config: %s (%s)" % (report["config"]["config_path"], "exists" if report["config"]["config_exists"] else "missing"))
    print("live_probe: %s" % report["live_probe"])
    print("")
    for name, payload in report["services"].items():
        line = "- %s: %s" % (name, payload.get("status", "unknown"))
        if payload.get("latency_ms") is not None:
            line += " (%sms)" % payload.get("latency_ms")
        if payload.get("error"):
            line += " | error=%s" % payload.get("error")
        print(line)
    print("")
    print(
        "summary: ok=%s failed=%s skipped=%s missing_config=%s configured=%s"
        % (
            report["summary"]["ok"],
            report["summary"]["failed"],
            report["summary"]["skipped"],
            report["summary"]["missing_config"],
            report["summary"]["configured_services"],
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check codex-search API availability")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    parser.add_argument(
        "--live",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable live API probes",
    )
    parser.add_argument("--query", default="OpenAI Codex", help="Probe query for search providers")
    parser.add_argument("--timeout", type=int, default=8, help="Per-probe timeout seconds")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when any configured service probe fails",
    )
    args = parser.parse_args()

    report = _build_report(live=bool(args.live), query=args.query, timeout=max(3, int(args.timeout)))
    if args.strict and report["summary"]["bad_configured"] > 0:
        report["ok"] = False

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
