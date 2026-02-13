#!/usr/bin/env python3
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_search_stack.config import load_settings, resolve_config_path  # noqa: E402


def _secret_value_meta(value: Optional[str]) -> Dict:
    value = (value or "").strip()
    if not value:
        return {"present": False}
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return {
        "present": True,
        "length": len(value),
        "sha256_prefix": digest,
    }


def _file_meta(raw: Optional[str]) -> Dict:
    raw = (raw or "").strip()
    if not raw:
        return {"present": False}
    path = str(Path(raw).expanduser())
    exists = Path(path).exists()
    return {
        "present": True,
        "path": path,
        "exists": exists,
    }


def main() -> int:
    settings = load_settings()
    config_path = resolve_config_path()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_file": str(config_path),
        "config_file_exists": config_path.exists(),
        "python_version": os.environ.get("PYTHON_VERSION", ""),
        "secrets": {
            "EXA_API_KEY": _secret_value_meta(settings.exa_api_key),
            "TAVILY_API_KEY": _secret_value_meta(settings.tavily_api_key),
            "GROK_API_KEY": _secret_value_meta(settings.grok_api_key),
            "GITHUB_TOKEN": _secret_value_meta(settings.github_token),
            "MINERU_TOKEN": _secret_value_meta(settings.mineru_token),
        },
        "urls": {
            "TAVILY_API_URL": {"present": bool(settings.tavily_api_url), "value": settings.tavily_api_url},
            "GROK_API_URL": {"present": bool(settings.grok_api_url), "value": settings.grok_api_url or ""},
        },
        "files": {
            "KEY_POOL_FILE": _file_meta(settings.key_pool_file),
            "MINERU_TOKEN_FILE": _file_meta(settings.mineru_token_file),
        },
        "config": {
            "CONFIDENCE_PROFILE": (settings.confidence_profile or "deep").strip().lower(),
            "CI_SMOKE_MODE": (os.environ.get("CI_SMOKE_MODE") or "auto").strip().lower(),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
