#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_search_stack.config import load_settings, resolve_config_path  # noqa: E402
from codex_search_stack.key_pool import load_pool_candidates  # noqa: E402


def _mask(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return "(empty)"
    if len(raw) <= 12:
        return "***"
    return "%s...%s" % (raw[:8], raw[-4:])


def _ok(flag: bool) -> str:
    return "OK" if flag else "MISSING"


def _exists(path: Optional[str]) -> bool:
    if not path:
        return False
    return Path(path).expanduser().exists()


def _build_report() -> Dict:
    settings = load_settings()
    config_path = resolve_config_path()
    pool_file = settings.key_pool_file
    mineru_file = settings.mineru_token_file

    pool_enabled = bool(settings.key_pool_enabled)
    pool_exists = _exists(pool_file)
    mineru_file_exists = _exists(mineru_file)
    mineru_token_present = bool((settings.mineru_token or "").strip())

    pool_error = None
    pool_count = 0
    if pool_enabled and pool_exists and pool_file:
        try:
            rows = load_pool_candidates(
                pool_file=pool_file,
                default_urls={
                    "grok": (settings.grok_api_url or "").strip(),
                    "tavily": (settings.tavily_api_url or "").strip(),
                },
            )
            pool_count = len(rows)
        except Exception as exc:
            pool_error = str(exc)

    search_ready = bool(
        (settings.exa_api_key or "").strip()
        or (settings.grok_api_key or "").strip()
        or (settings.tavily_api_key or "").strip()
        or (pool_enabled and pool_exists and pool_error is None and pool_count > 0)
    )
    extract_ready = bool((settings.tavily_api_key or "").strip() or mineru_token_present or mineru_file_exists)

    return {
        "project_root": str(ROOT_DIR),
        "config_file": str(config_path),
        "config_file_exists": config_path.exists(),
        "search_ready": search_ready,
        "extract_ready": extract_ready,
        "settings": {
            "EXA_API_KEY": _mask(settings.exa_api_key),
            "GROK_API_URL": settings.grok_api_url or "(empty)",
            "GROK_API_KEY": _mask(settings.grok_api_key),
            "GROK_MODEL": settings.grok_model,
            "TAVILY_API_URL": settings.tavily_api_url,
            "TAVILY_API_KEY": _mask(settings.tavily_api_key),
            "GITHUB_TOKEN": _mask(settings.github_token),
            "MINERU_API_BASE": settings.mineru_api_base,
            "MINERU_TOKEN": _mask(settings.mineru_token),
            "MINERU_TOKEN_FILE": str(Path(mineru_file).expanduser()) if mineru_file else "(empty)",
            "MINERU_TOKEN_FILE_EXISTS": mineru_file_exists,
            "KEY_POOL_ENABLED": pool_enabled,
            "KEY_POOL_FILE": str(Path(pool_file).expanduser()) if pool_file else "(empty)",
            "KEY_POOL_FILE_EXISTS": pool_exists,
            "KEY_POOL_VALID": pool_error is None,
            "KEY_POOL_CANDIDATES": pool_count,
            "KEY_POOL_ERROR": pool_error or "",
        },
    }


def _print_text(report: Dict) -> None:
    settings = report["settings"]
    print("=== codex-search API 配置体检 ===")
    print("project: %s" % report["project_root"])
    print("config : %s (%s)" % (report["config_file"], "exists" if report["config_file_exists"] else "missing"))
    print("search : %s" % _ok(report["search_ready"]))
    print("extract: %s" % _ok(report["extract_ready"]))
    print("")
    print("[Search]")
    print("EXA_API_KEY      : %s" % settings["EXA_API_KEY"])
    print("GROK_API_URL     : %s" % settings["GROK_API_URL"])
    print("GROK_API_KEY     : %s" % settings["GROK_API_KEY"])
    print("GROK_MODEL       : %s" % settings["GROK_MODEL"])
    print("TAVILY_API_URL   : %s" % settings["TAVILY_API_URL"])
    print("TAVILY_API_KEY   : %s" % settings["TAVILY_API_KEY"])
    print("KEY_POOL_ENABLED : %s" % settings["KEY_POOL_ENABLED"])
    print("KEY_POOL_FILE    : %s" % settings["KEY_POOL_FILE"])
    print("KEY_POOL_EXISTS  : %s" % settings["KEY_POOL_FILE_EXISTS"])
    print("KEY_POOL_VALID   : %s" % settings["KEY_POOL_VALID"])
    print("KEY_POOL_ROWS    : %s" % settings["KEY_POOL_CANDIDATES"])
    if settings["KEY_POOL_ERROR"]:
        print("KEY_POOL_ERROR   : %s" % settings["KEY_POOL_ERROR"])
    print("")
    print("[Extract + Explore]")
    print("MINERU_API_BASE  : %s" % settings["MINERU_API_BASE"])
    print("MINERU_TOKEN     : %s" % settings["MINERU_TOKEN"])
    print("MINERU_TOKEN_FILE: %s" % settings["MINERU_TOKEN_FILE"])
    print("MINERU_FILE_OK   : %s" % settings["MINERU_TOKEN_FILE_EXISTS"])
    print("GITHUB_TOKEN     : %s" % settings["GITHUB_TOKEN"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Check effective API configuration")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    report = _build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
