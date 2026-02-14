import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

def _load_dotenv(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Settings:
    grok_api_url: Optional[str]
    grok_api_key: Optional[str]
    grok_model: str

    exa_api_key: Optional[str]
    tavily_api_key: Optional[str]
    tavily_api_url: str
    github_token: Optional[str]
    key_pool_file: Optional[str]
    key_pool_enabled: bool
    confidence_profile: str

    mineru_token: Optional[str]
    mineru_token_file: Optional[str]
    mineru_api_base: str
    mineru_wrapper_path: Optional[str]
    mineru_workspace: Optional[str]

    search_timeout_seconds: int = 60
    extract_timeout_seconds: int = 30
    policy: Dict[str, Any] = field(default_factory=dict)
    decision_trace_enabled: bool = True
    decision_trace_persist: bool = True
    decision_trace_jsonl_path: str = "./.runtime/decision-trace/decision_trace.jsonl"


def resolve_config_path(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parents[2]
    custom = (os.environ.get("CODEX_SEARCH_CONFIG") or "").strip()
    if custom:
        return Path(custom).expanduser()
    return root / "config" / "config.yaml"


def _read_secret_file(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        value = Path(path).expanduser().read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None
    return value or None


def _pick(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                continue
            return raw
        return value
    return None


def _to_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _cfg_get(data: Dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _load_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[2]
    config_path = resolve_config_path(project_root)
    _load_dotenv(project_root / ".env")
    config = _load_yaml_config(config_path)
    use_env_fallback = not config_path.exists()

    def env(name: str) -> Optional[str]:
        if not use_env_fallback:
            return None
        return os.environ.get(name)

    default_mineru_token_file = str((project_root.parent / "mineru_key.txt").resolve())
    default_mineru_workspace = str((project_root / ".runtime" / "codex-workspace").resolve())
    default_key_pool_file = str((project_root.parent.parent / "key-pool" / "pool.csv").resolve())
    default_decision_trace_path = str((project_root / ".runtime" / "decision-trace" / "decision_trace.jsonl").resolve())

    mineru_token_file = _pick(
        _cfg_get(config, "extract", "mineru", "token_file"),
        env("MINERU_TOKEN_FILE"),
        default_mineru_token_file,
    )
    mineru_token = _pick(
        _cfg_get(config, "extract", "mineru", "token"),
        env("MINERU_TOKEN"),
        _read_secret_file(mineru_token_file),
    )
    policy_config = _cfg_get(config, "policy")

    return Settings(
        grok_api_url=_pick(_cfg_get(config, "search", "grok", "api_url"), env("GROK_API_URL")),
        grok_api_key=_pick(_cfg_get(config, "search", "grok", "api_key"), env("GROK_API_KEY")),
        grok_model=_pick(_cfg_get(config, "search", "grok", "model"), env("GROK_MODEL"), "grok-4.1-thinking"),
        exa_api_key=_pick(_cfg_get(config, "search", "exa", "api_key"), env("EXA_API_KEY")),
        tavily_api_key=_pick(_cfg_get(config, "search", "tavily", "api_key"), env("TAVILY_API_KEY")),
        tavily_api_url=_pick(
            _cfg_get(config, "search", "tavily", "api_url"),
            env("TAVILY_API_URL"),
            "https://api.tavily.com",
        ),
        github_token=_pick(_cfg_get(config, "explore", "github_token"), env("GITHUB_TOKEN")),
        key_pool_file=_pick(
            _cfg_get(config, "search", "key_pool", "file"),
            env("KEY_POOL_FILE"),
            default_key_pool_file,
        ),
        key_pool_enabled=_to_bool(
            _pick(_cfg_get(config, "search", "key_pool", "enabled"), env("KEY_POOL_ENABLED")),
            True,
        ),
        confidence_profile=(
            _pick(_cfg_get(config, "runtime", "confidence_profile"), env("CONFIDENCE_PROFILE"), "deep")
            .strip()
            .lower()
        )
        or "deep",
        mineru_token=mineru_token,
        mineru_token_file=mineru_token_file,
        mineru_api_base=_pick(
            _cfg_get(config, "extract", "mineru", "api_base"),
            env("MINERU_API_BASE"),
            "https://mineru.net",
        ),
        mineru_wrapper_path=_pick(
            _cfg_get(config, "extract", "mineru", "wrapper_path"),
            env("MINERU_WRAPPER_PATH"),
        ),
        mineru_workspace=_pick(
            _cfg_get(config, "extract", "mineru", "workspace"),
            env("MINERU_WORKSPACE"),
            default_mineru_workspace,
        ),
        search_timeout_seconds=_to_int(
            _pick(_cfg_get(config, "runtime", "search_timeout_seconds"), env("SEARCH_TIMEOUT_SECONDS")),
            60,
        ),
        extract_timeout_seconds=_to_int(
            _pick(_cfg_get(config, "runtime", "extract_timeout_seconds"), env("EXTRACT_TIMEOUT_SECONDS")),
            30,
        ),
        policy=policy_config if isinstance(policy_config, dict) else {},
        decision_trace_enabled=_to_bool(
            _pick(
                _cfg_get(config, "observability", "decision_trace", "enabled"),
                env("DECISION_TRACE_ENABLED"),
            ),
            True,
        ),
        decision_trace_persist=_to_bool(
            _pick(
                _cfg_get(config, "observability", "decision_trace", "persist"),
                env("DECISION_TRACE_PERSIST"),
            ),
            True,
        ),
        decision_trace_jsonl_path=_pick(
            _cfg_get(config, "observability", "decision_trace", "path"),
            env("DECISION_TRACE_PATH"),
            default_decision_trace_path,
        ),
    )
