import re
from typing import Any, Dict, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

_TIME_SIGNAL_RE = re.compile(
    r"(latest|recent|this week|this month|current|today|新闻|最新|最近|本周|本月|近期)",
    re.IGNORECASE,
)
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
EXTRACT_STRATEGIES = {"auto", "tavily_first", "mineru_first", "tavily_only", "mineru_only"}
DEFAULT_ANTI_BOT_DOMAINS = {
    "mp.weixin.qq.com",
    "zhuanlan.zhihu.com",
    "www.zhihu.com",
    "zhihu.com",
    "www.xiaohongshu.com",
    "xiaohongshu.com",
}


def coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def split_domain_boost(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def invalid_domain_boost_values(domains: Sequence[str]) -> list[str]:
    return [domain for domain in domains if not _DOMAIN_RE.match(domain)]


def has_time_signal(queries: Sequence[str]) -> bool:
    for query in queries:
        if _TIME_SIGNAL_RE.search(query or ""):
            return True
    return False


def validate_search_protocol(
    *,
    queries: Sequence[str],
    intent: str,
    freshness: str,
    num: int,
    domains: Sequence[str],
    comparison_queries: int,
    comparison_error_message: str,
    time_signal_error_message: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    invalid_domains = invalid_domain_boost_values(domains)
    if invalid_domains:
        return "invalid domain_boost values", {"invalid_domains": invalid_domains}
    if num < 1 or num > 20:
        return "num must be between 1 and 20", None
    if intent in {"status", "news"} and not freshness:
        return "intent status/news requires freshness", None
    if intent == "comparison" and comparison_queries < 2:
        return comparison_error_message, None
    if has_time_signal(queries) and not freshness:
        return time_signal_error_message, None
    return None, None


def validate_extract_protocol(*, url: str, max_chars: int, strategy: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "url must be a valid http(s) URL", None

    normalized_max_chars = coerce_int(max_chars, 20000)
    if normalized_max_chars < 500 or normalized_max_chars > 200000:
        return "max_chars must be between 500 and 200000", None

    normalized_strategy = (strategy or "auto").strip().lower()
    if normalized_strategy not in EXTRACT_STRATEGIES:
        return "strategy must be one of auto/tavily_first/mineru_first/tavily_only/mineru_only", None

    return (
        None,
        {
            "host": (parsed.hostname or "").lower(),
            "max_chars": normalized_max_chars,
            "strategy": normalized_strategy,
            "url": url,
        },
    )


def is_high_risk_host(host: str, anti_bot_domains: Sequence[str]) -> bool:
    if not host:
        return False
    for domain in anti_bot_domains:
        d = (domain or "").strip().lower()
        if not d:
            continue
        if host == d or host.endswith("." + d):
            return True
    return False


def extract_anti_bot_domains(policy: Any) -> Set[str]:
    if not isinstance(policy, dict):
        return set(DEFAULT_ANTI_BOT_DOMAINS)
    extract_policy = policy.get("extract", {})
    if not isinstance(extract_policy, dict):
        return set(DEFAULT_ANTI_BOT_DOMAINS)
    domains = extract_policy.get("anti_bot_domains", [])
    if not isinstance(domains, list):
        return set(DEFAULT_ANTI_BOT_DOMAINS)
    out = {str(item).strip().lower() for item in domains if str(item).strip()}
    return out or set(DEFAULT_ANTI_BOT_DOMAINS)


def validate_explore_protocol(
    *,
    issues: int,
    commits: int,
    external_num: int,
    extract_top: int,
    output_format: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    normalized_issues = coerce_int(issues, 5)
    normalized_commits = coerce_int(commits, 5)
    normalized_external = coerce_int(external_num, 8)
    normalized_extract_top = coerce_int(extract_top, 2)
    normalized_format = (output_format or "json").strip().lower()

    if normalized_issues < 3 or normalized_issues > 20:
        return "issues must be between 3 and 20", None
    if normalized_commits < 3 or normalized_commits > 20:
        return "commits must be between 3 and 20", None
    if normalized_external < 2 or normalized_external > 30:
        return "external_num must be between 2 and 30", None
    if normalized_extract_top < 0 or normalized_extract_top > normalized_external:
        return "extract_top must be between 0 and external_num", None
    if normalized_format not in {"json", "markdown"}:
        return "output_format must be json or markdown", None

    return (
        None,
        {
            "issues": normalized_issues,
            "commits": normalized_commits,
            "external_num": normalized_external,
            "extract_top": normalized_extract_top,
            "output_format": normalized_format,
        },
    )
