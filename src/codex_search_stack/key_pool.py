from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SUPPORTED_SERVICES = {"grok", "tavily"}


@dataclass
class KeyCandidate:
    service: str
    url: str
    key: str
    weight: int = 100
    source: str = "pool"


def mask_key(key: str) -> str:
    value = (key or "").strip()
    if len(value) <= 12:
        return "***"
    return "%s...%s" % (value[:8], value[-4:])


def _normalize_key(raw: str) -> str:
    value = (raw or "").strip()
    if "----" in value:
        value = value.split("----", 1)[1].strip()
    return value


def _to_int(raw: str, default: int = 100) -> int:
    try:
        value = int((raw or "").strip())
        return value if value > 0 else default
    except Exception:
        return default


def _pool_line_error(line_no: int, raw_line: str, reason: str) -> ValueError:
    sample = (raw_line or "").strip()
    return ValueError(
        "pool.csv line %d invalid format (%s), expected service,url,key,weight: %s"
        % (line_no, reason, sample)
    )


def _parse_pool_line(
    raw_line: str,
    default_urls: Dict[str, str],
    line_no: int = 0,
) -> Optional[KeyCandidate]:
    line = (raw_line or "").strip()
    if not line or line.startswith("#"):
        return None

    parts = [item.strip() for item in line.split(",", 3)]
    if len(parts) != 4:
        raise _pool_line_error(line_no, line, "column_count")
    service, url, key, weight = parts

    service = service.lower()
    if service not in SUPPORTED_SERVICES:
        raise _pool_line_error(line_no, line, "unsupported_service")

    norm_key = _normalize_key(key)
    if not norm_key:
        raise _pool_line_error(line_no, line, "empty_key")
    endpoint = (url or default_urls.get(service) or "").strip()
    if not endpoint:
        raise _pool_line_error(line_no, line, "empty_url")

    return KeyCandidate(
        service=service,
        url=endpoint,
        key=norm_key,
        weight=_to_int(weight, default=100),
        source="pool",
    )


def _sort_candidates(candidates: List[KeyCandidate]) -> List[KeyCandidate]:
    # stable deterministic order: higher weight first
    return sorted(candidates, key=lambda item: item.weight, reverse=True)


def load_pool_candidates(
    pool_file: Optional[str],
    default_urls: Dict[str, str],
) -> List[KeyCandidate]:
    if not pool_file:
        return []
    target = Path(pool_file).expanduser()
    if not target.exists() or not target.is_file():
        return []

    out: List[KeyCandidate] = []
    for line_no, line in enumerate(target.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        parsed = _parse_pool_line(line, default_urls, line_no=line_no)
        if parsed:
            out.append(parsed)
    return _sort_candidates(out)


def build_service_candidates(
    service: str,
    primary_url: Optional[str],
    primary_key: Optional[str],
    pool_file: Optional[str],
    pool_enabled: bool = True,
) -> List[KeyCandidate]:
    service_name = (service or "").lower().strip()
    if service_name not in SUPPORTED_SERVICES:
        return []

    default_urls = {
        "grok": (primary_url or "").strip(),
        "tavily": (primary_url or "").strip(),
    }
    pool_rows = load_pool_candidates(pool_file, default_urls) if pool_enabled else []

    out: List[KeyCandidate] = []
    if primary_url and primary_key:
        out.append(
            KeyCandidate(
                service=service_name,
                url=primary_url,
                key=_normalize_key(primary_key),
                weight=1000,
                source="primary",
            )
        )

    for row in pool_rows:
        if row.service == service_name:
            out.append(row)

    dedup: Dict[Tuple[str, str, str], KeyCandidate] = {}
    ordered: List[KeyCandidate] = []
    for item in out:
        key = (item.service, item.url, item.key)
        if key in dedup:
            continue
        dedup[key] = item
        ordered.append(item)
    return ordered
