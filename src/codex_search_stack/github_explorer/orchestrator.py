import base64
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from ..config import Settings
from ..extract.pipeline import run_extract_pipeline
from ..search.orchestrator import run_multi_source_search

_GITHUB_REPO_PATH = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
_RISKY_HOSTS = {
    "zhuanlan.zhihu.com",
    "www.zhihu.com",
    "zhihu.com",
    "mp.weixin.qq.com",
    "www.xiaohongshu.com",
    "xiaohongshu.com",
}
_OWNER_REPO_MENTION = re.compile(r"\b([a-z0-9_.-]+)/([a-z0-9_.-]+)\b", re.IGNORECASE)
_HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
_ARCH_RISK_RULES: Dict[str, List[str]] = {
    "架构": ["architecture", "architect", "design", "refactor", "模块", "架构", "设计"],
    "性能": ["performance", "latency", "slow", "throughput", "memory", "cpu", "性能", "耗时", "内存"],
    "稳定性": ["crash", "panic", "hang", "deadlock", "race", "稳定", "崩溃", "死锁"],
    "兼容性": ["compat", "breaking", "migration", "版本", "兼容", "upgrade", "deprecate"],
    "安全": ["security", "vulnerability", "cve", "auth", "权限", "注入", "越权"],
}
_COMMUNITY_DOMAINS = [
    "zhuanlan.zhihu.com",
    "zhihu.com",
    "mp.weixin.qq.com",
    "v2ex.com",
    "x.com",
    "twitter.com",
]
_PAPER_DOMAINS = ["arxiv.org"]
_INDEX_DOMAINS = ["deepwiki.com", "zread.ai", "zread.cc", "zread.net"]
_COMPETE_HINTS = ["alternative", "alternatives", "vs", "compare", "comparison", "替代", "对比", "竞品"]
_SOURCE_PRIORITY = {
    "deepwiki": 5,
    "zread": 5,
    "repo_seed": 4,
    "exa": 3,
    "grok": 2,
    "tavily": 1,
}
_SEARCH_SOURCE_ALLOWLIST = {"exa", "tavily", "grok"}
_FOLLOWUP_STOPWORDS = {
    "github",
    "https",
    "http",
    "issue",
    "issues",
    "repo",
    "repository",
    "project",
    "release",
    "releases",
    "readme",
    "code",
    "main",
    "wiki",
    "paper",
    "research",
    "using",
    "used",
    "with",
    "from",
    "about",
    "this",
    "that",
    "where",
    "what",
    "when",
    "have",
    "more",
}

_CONFIDENCE_PROFILES: Dict[str, Dict] = {
    "deep": {
        "display_name": "deep",
        "description": "尽调优先：偏重元数据、活跃度与提取可验证性",
        "weights": {
            "metadata": 30,
            "activity": 25,
            "external": 20,
            "extract": 15,
            "stability": 10,
        },
    },
    "quick": {
        "display_name": "quick",
        "description": "快扫优先：偏重外部覆盖与执行稳定性",
        "weights": {
            "metadata": 20,
            "activity": 18,
            "external": 34,
            "extract": 8,
            "stability": 20,
        },
    },
}


def _repo_from_url(url: str) -> Optional[Tuple[str, str]]:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if repo in {"issues", "pulls", "actions", "wiki", "releases"}:
        return None
    return owner, repo


def _repo_from_target(target: str) -> Optional[Tuple[str, str]]:
    value = target.strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return _repo_from_url(value)
    match = _GITHUB_REPO_PATH.match(value)
    if not match:
        return None
    return match.group(1), match.group(2)


def _github_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codex-search",
    }
    if token:
        headers["Authorization"] = "Bearer %s" % token
    return headers


def _infer_project_stage(pushed_at: Optional[str]) -> str:
    if not pushed_at:
        return "未知"
    try:
        dt = datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return "未知"
    delta_days = (datetime.now(timezone.utc) - dt).days
    if delta_days <= 14:
        return "快速迭代"
    if delta_days <= 60:
        return "稳定活跃"
    if delta_days <= 180:
        return "维护模式"
    return "低活跃/可能停滞"


def _trim_text(value: str, max_chars: int = 220) -> str:
    text = (value or "").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _is_maintainer_association(value: str) -> bool:
    return (value or "").strip().upper() in _MAINTAINER_ASSOCIATIONS


def _issue_risk_tags(title: str, body: str) -> List[str]:
    haystack = ("%s %s" % (title or "", body or "")).lower()
    tags: List[str] = []
    for tag, tokens in _ARCH_RISK_RULES.items():
        if any(token in haystack for token in tokens):
            tags.append(tag)
    return tags


def _issue_quality_score(comments: int, maintainer_comment_count: int, risk_tags: List[str], updated_at: str) -> int:
    score = 0
    score += min(3, comments // 3 + (1 if comments > 0 else 0))
    if maintainer_comment_count > 0:
        score += min(3, 1 + maintainer_comment_count)
    score += min(2, len(risk_tags))
    if updated_at:
        score += 2
    return max(0, min(score, 10))


def _decode_github_readme(content: str, encoding: str) -> str:
    if not content:
        return ""
    if (encoding or "").lower() != "base64":
        return _trim_text(content, 600)
    try:
        raw = base64.b64decode(content.encode("utf-8"), validate=False).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return _trim_text(raw, 600)


def _domain_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_same_repo(owner: str, repo: str, candidate_owner: str, candidate_repo: str) -> bool:
    return owner.lower() == candidate_owner.lower() and repo.lower() == candidate_repo.lower()


def _maybe_competitor_score(owner: str, repo: str, title: str, snippet: str, url: str, query_tag: str) -> int:
    parsed = _repo_from_url(url)
    if parsed and _is_same_repo(owner, repo, parsed[0], parsed[1]):
        return 0
    text = " ".join([title or "", snippet or "", url or ""]).lower()
    score = 0
    if query_tag == "competitor":
        score += 2
    if any(token in text for token in _COMPETE_HINTS):
        score += 2
    if ("%s/%s" % (owner.lower(), repo.lower())) in text:
        score += 2
    if parsed:
        score += 1
    if score < 3:
        return 0
    return score


def _build_index_coverage(owner: str, repo: str, external: List[Dict], notes: List[str]) -> Dict[str, Dict[str, str]]:
    anchor = ("%s/%s" % (owner, repo)).lower()

    def status_for(name: str, domains: List[str]) -> Dict[str, str]:
        for item in external:
            url = item.get("url", "")
            host = _domain_of(url)
            if any(host == domain or host.endswith("." + domain) for domain in domains):
                return {"status": "found", "url": url}
        for note in notes:
            if note.startswith("%s_unavailable:" % name):
                return {"status": "unavailable", "url": ""}
        return {"status": "not_found", "url": ""}

    deepwiki = status_for("deepwiki", ["deepwiki.com"])
    if deepwiki["status"] == "found" and anchor not in (deepwiki["url"] or "").lower():
        deepwiki = {"status": "not_found", "url": ""}

    arxiv = status_for("arxiv", ["arxiv.org"])
    zread = status_for("zread", ["zread.ai", "zread.cc", "zread.net"])
    return {"deepwiki": deepwiki, "arxiv": arxiv, "zread": zread}


def _source_priority(source: str) -> int:
    return int(_SOURCE_PRIORITY.get((source or "").strip().lower(), 0))


def _policy_explore_external(settings: Settings) -> Dict[str, object]:
    policy = getattr(settings, "policy", {})
    if not isinstance(policy, dict):
        return {}
    explore = policy.get("explore") or {}
    if not isinstance(explore, dict):
        return {}
    external = explore.get("external") or {}
    if not isinstance(external, dict):
        return {}
    return external


def _normalize_sources(value: object, fallback: List[str]) -> List[str]:
    out: List[str] = []
    if isinstance(value, list):
        items = value
    else:
        items = []
    for item in items:
        token = str(item).strip().lower()
        if token in _SEARCH_SOURCE_ALLOWLIST and token not in out:
            out.append(token)
    return out or list(fallback)


def _external_timeout_seconds(settings: Settings) -> int:
    external_policy = _policy_explore_external(settings)
    raw = external_policy.get("timeout_seconds")
    if raw is None:
        return max(5, int(getattr(settings, "search_timeout_seconds", 30) or 30))
    try:
        value = int(raw)
    except Exception:
        value = int(getattr(settings, "search_timeout_seconds", 30) or 30)
    return max(5, min(value, 300))


def _external_model_profile(settings: Settings) -> str:
    external_policy = _policy_explore_external(settings)
    value = str(external_policy.get("model_profile") or "").strip().lower()
    if value in {"cheap", "balanced", "strong"}:
        return value
    return "strong"


def _external_followup_rounds(settings: Settings) -> int:
    external_policy = _policy_explore_external(settings)
    raw = external_policy.get("followup_rounds")
    if raw is None:
        return 2
    try:
        value = int(raw)
    except Exception:
        value = 2
    return max(0, min(value, 4))


def _external_fallback_source(settings: Settings) -> str:
    external_policy = _policy_explore_external(settings)
    value = str(external_policy.get("fallback_source") or "").strip().lower()
    if value in _SEARCH_SOURCE_ALLOWLIST:
        return value
    return "tavily"


def _preferred_sources_for_query(tag: str, settings: Settings) -> List[str]:
    # 稳定性优先：主源走可配置 source mix，空结果时再 fallback_source。
    _ = tag
    external_policy = _policy_explore_external(settings)
    configured = external_policy.get("primary_sources")
    if isinstance(configured, dict):
        per_tag = configured.get(tag)
        defaults = configured.get("default")
        if isinstance(per_tag, list):
            return _normalize_sources(per_tag, ["exa", "grok"])
        return _normalize_sources(defaults, ["exa", "grok"])
    return _normalize_sources(configured, ["exa", "grok"])


def _inject_seed_when_unstable(owner: str, repo: str, selected: List[Dict], external_limit: int, failed_count: int) -> List[Dict]:
    if external_limit <= 0:
        return selected
    if failed_count < 3:
        return selected

    existing = {(item.get("url") or "").strip().rstrip("/") for item in selected}
    out = list(selected)
    injected = 0
    for seed in _seed_repo_external(owner, repo, max(2, min(external_limit, 4))):
        key = (seed.get("url") or "").strip().rstrip("/")
        if not key or key in existing:
            continue
        out.append(seed)
        existing.add(key)
        injected += 1
        if len(out) >= external_limit:
            break
    if injected == 0:
        return selected
    ranked = sorted(
        out,
        key=lambda item: (
            _source_priority(item.get("source", "")),
            1 if item.get("published_date") else 0,
            item.get("published_date") or "",
        ),
        reverse=True,
    )
    return ranked[:external_limit]

def _is_same_repo_url(url: str, owner: str, repo: str) -> bool:
    parsed = _repo_from_url(url)
    if not parsed:
        return False
    return parsed[0].lower() == owner.lower() and parsed[1].lower() == repo.lower()


def _external_relevance_score(owner: str, repo: str, title: str, snippet: str, url: str) -> int:
    owner_l = owner.lower()
    repo_l = repo.lower()
    anchor = "%s/%s" % (owner_l, repo_l)
    text = " ".join([title or "", snippet or "", url or ""]).lower()

    score = 0
    if _is_same_repo_url(url, owner, repo):
        score += 8
    if anchor in text:
        score += 6
    if owner_l in text and repo_l in text:
        score += 2
    if repo_l in text:
        score += 1

    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host.endswith("github.com"):
        parsed = _repo_from_url(url)
        if parsed and not _is_same_repo_url(url, owner, repo):
            score -= 4

    mentions = _OWNER_REPO_MENTION.findall(text)
    if mentions:
        hit_target = any((o.lower() == owner_l and r.lower() == repo_l) for o, r in mentions)
        if not hit_target:
            score -= 2

    return max(0, score)


def _build_external_queries(owner: str, repo: str) -> List[Dict[str, object]]:
    anchor = "%s/%s" % (owner, repo)
    return [
        {
            "query": "site:github.com/%s/%s" % (owner, repo),
            "intent": "resource",
            "tag": "repo",
            "boost_domains": ["github.com"],
        },
        {
            "query": '"%s" release changelog issues' % anchor,
            "intent": "resource",
            "tag": "repo",
            "boost_domains": ["github.com"],
        },
        {
            "query": '"%s" 知乎 微信公众号 v2ex twitter x.com 使用体验' % anchor,
            "intent": "exploratory",
            "tag": "community",
            "boost_domains": list(_COMMUNITY_DOMAINS),
        },
        {
            "query": '"%s" arxiv paper research' % repo,
            "intent": "resource",
            "tag": "paper",
            "boost_domains": list(_PAPER_DOMAINS),
        },
        {
            "query": '"%s" zread deepwiki' % anchor,
            "intent": "resource",
            "tag": "index",
            "boost_domains": list(_INDEX_DOMAINS),
        },
        {
            "query": '"%s" alternatives vs comparison' % anchor,
            "intent": "comparison",
            "tag": "competitor",
            "boost_domains": ["github.com"],
        },
    ]


def _seed_repo_external(owner: str, repo: str, limit: int) -> List[Dict]:
    seed = [
        {
            "title": "%s/%s Repository" % (owner, repo),
            "url": "https://github.com/%s/%s" % (owner, repo),
            "snippet": "Repository homepage",
            "source": "repo_seed",
            "published_date": "",
        },
        {
            "title": "%s/%s Releases" % (owner, repo),
            "url": "https://github.com/%s/%s/releases" % (owner, repo),
            "snippet": "Repository release history",
            "source": "repo_seed",
            "published_date": "",
        },
        {
            "title": "%s/%s Issues" % (owner, repo),
            "url": "https://github.com/%s/%s/issues" % (owner, repo),
            "snippet": "Repository issues list",
            "source": "repo_seed",
            "published_date": "",
        },
        {
            "title": "%s/%s Pull Requests" % (owner, repo),
            "url": "https://github.com/%s/%s/pulls" % (owner, repo),
            "snippet": "Repository pull requests",
            "source": "repo_seed",
            "published_date": "",
        },
    ]
    return seed[: max(1, limit)]


def _title_from_html(content: str, fallback: str) -> str:
    match = _HTML_TITLE_RE.search(content or "")
    if not match:
        return fallback
    raw = re.sub(r"\s+", " ", match.group(1)).strip()
    if not raw:
        return fallback
    return _trim_text(raw, 120)


def _probe_index_page(
    name: str,
    url: str,
    owner: str,
    repo: str,
    settings: Settings,
    snippet: str,
    fallback_title: str,
) -> Tuple[Optional[Dict], str]:
    timeout = max(int(getattr(settings, "search_timeout_seconds", 30) or 30), 5)
    headers = {"User-Agent": "codex-search"}
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as exc:
        return None, "%s_unavailable:%s" % (name, exc)

    if response.status_code >= 400:
        if response.status_code == 404:
            return None, "%s_unavailable:not_indexed" % name
        return None, "%s_unavailable:http_%s" % (name, response.status_code)

    content = response.text or ""
    anchor = ("%s/%s" % (owner, repo)).lower()
    final_url = response.url or url
    if (anchor not in final_url.lower()) and (anchor not in content.lower()):
        return None, "%s_unavailable:not_indexed" % name

    item = {
        "title": _title_from_html(content, fallback_title),
        "url": final_url,
        "snippet": snippet,
        "source": name,
        "published_date": "",
    }
    return item, ""


def _collect_deepwiki(owner: str, repo: str, settings: Settings) -> Tuple[Optional[Dict], List[str]]:
    item, note = _probe_index_page(
        name="deepwiki",
        url="https://deepwiki.com/%s/%s" % (owner, repo),
        owner=owner,
        repo=repo,
        settings=settings,
        snippet="DeepWiki repository knowledge graph",
        fallback_title="%s/%s DeepWiki" % (owner, repo),
    )
    return item, ([note] if note else [])


def _collect_zread(owner: str, repo: str, settings: Settings) -> Tuple[Optional[Dict], List[str]]:
    candidates = [
        "https://zread.ai/%s/%s" % (owner, repo),
        "https://zread.ai/github/%s/%s" % (owner, repo),
        "https://zread.cc/%s/%s" % (owner, repo),
        "https://zread.net/%s/%s" % (owner, repo),
    ]
    errors: List[str] = []
    for url in candidates:
        item, note = _probe_index_page(
            name="zread",
            url=url,
            owner=owner,
            repo=repo,
            settings=settings,
            snippet="zread repository index",
            fallback_title="%s/%s zread" % (owner, repo),
        )
        if item:
            return item, []
        if note and (note not in errors):
            errors.append(note)
    if not errors:
        return None, ["zread_unavailable:not_indexed"]
    if any("not_indexed" in note for note in errors):
        return None, ["zread_unavailable:not_indexed"]
    return None, [errors[0]]


def _run_external_query(
    query: str,
    query_intent: str,
    query_tag: str,
    boost_domains: List[str],
    fetch_limit: int,
    settings: Settings,
    primary_sources: List[str],
    model_profile: str,
    timeout_seconds: int,
    fallback_source: str,
) -> Tuple[List, List[str], int]:
    notes: List[str] = []
    failed_count = 0
    primary_budget_ms = max(timeout_seconds, 1) * 1000 * max(1, len(primary_sources))
    result = run_multi_source_search(
        query=query,
        settings=settings,
        mode="deep",
        limit=fetch_limit,
        intent=query_intent,
        boost_domains=boost_domains,
        sources=primary_sources,
        model_profile=model_profile,
        budget_max_calls=max(1, len(primary_sources)),
        budget_max_latency_ms=primary_budget_ms,
    )
    notes.extend(result.notes)
    failed_count += len([item for item in (result.notes or []) if "_failed" in item])

    rows = list(result.results)
    if rows:
        return rows, notes, failed_count

    fallback_budget_ms = max(timeout_seconds, 1) * 1000
    fallback = run_multi_source_search(
        query=query,
        settings=settings,
        mode="deep",
        limit=fetch_limit,
        intent=query_intent,
        boost_domains=boost_domains,
        sources=[fallback_source],
        model_profile=model_profile,
        budget_max_calls=1,
        budget_max_latency_ms=fallback_budget_ms,
    )
    notes.extend(fallback.notes)
    failed_count += len([item for item in (fallback.notes or []) if "_failed" in item])
    if fallback.results:
        notes.append("external_query_fallback_%s:%s" % (fallback_source, query_tag))
    return list(fallback.results), notes, failed_count


def _followup_terms(owner: str, repo: str, merged: List[Dict]) -> List[str]:
    tokens: Dict[str, int] = {}
    owner_l = owner.lower()
    repo_l = repo.lower()
    for item in merged[:20]:
        text = " ".join([item.get("title", ""), item.get("snippet", "")])
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text):
            normalized = token.lower().strip("_-")
            if not normalized:
                continue
            if normalized in _FOLLOWUP_STOPWORDS:
                continue
            if normalized in {owner_l, repo_l}:
                continue
            if normalized.startswith("http"):
                continue
            tokens[normalized] = int(tokens.get(normalized, 0)) + 1
    ranked = sorted(tokens.items(), key=lambda item: item[1], reverse=True)
    return [item[0] for item in ranked[:3]]


def _build_followup_queries(
    owner: str,
    repo: str,
    merged: List[Dict],
    competitors: List[Dict],
) -> List[Dict[str, object]]:
    anchor = "%s/%s" % (owner, repo)
    hosts = {_domain_of(item.get("url", "")) for item in merged}
    has_arxiv = any(host.endswith("arxiv.org") for host in hosts)
    has_zread = any(host.endswith("zread.ai") or host.endswith("zread.cc") or host.endswith("zread.net") for host in hosts)
    community_count = len([host for host in hosts if host in set(_COMMUNITY_DOMAINS)])
    terms = _followup_terms(owner, repo, merged)
    hint = " ".join('"%s"' % term for term in terms[:2]).strip()
    if not hint:
        hint = '"%s"' % repo

    queries: List[Dict[str, object]] = []
    if not has_arxiv:
        queries.append(
            {
                "query": 'site:arxiv.org ("%s" OR "%s") %s' % (anchor, repo, hint),
                "intent": "resource",
                "tag": "paper_followup",
                "boost_domains": list(_PAPER_DOMAINS),
            }
        )
    if not has_zread:
        queries.append(
            {
                "query": 'site:zread.ai ("%s" OR "%s") %s' % (anchor, repo, hint),
                "intent": "resource",
                "tag": "index_followup",
                "boost_domains": ["zread.ai", "zread.cc", "zread.net"],
            }
        )
    if community_count < 2:
        queries.append(
            {
                "query": '"%s" %s 评测 使用体验 踩坑' % (anchor, hint),
                "intent": "exploratory",
                "tag": "community_followup",
                "boost_domains": list(_COMMUNITY_DOMAINS),
            }
        )
    if not competitors:
        queries.append(
            {
                "query": '"%s" %s alternative comparison vs' % (anchor, hint),
                "intent": "comparison",
                "tag": "competitor_followup",
                "boost_domains": ["github.com"],
            }
        )
    return queries[:3]


def _build_confidence(
    repo_block: Dict,
    issues: List[Dict],
    commits: List[Dict],
    external: List[Dict],
    notes: List[str],
    with_extract: bool,
    profile: str,
) -> Dict:
    profile_key = profile if profile in _CONFIDENCE_PROFILES else "deep"
    profile_config = _CONFIDENCE_PROFILES[profile_key]
    weights = profile_config["weights"]
    factors: List[Dict] = []

    def add_factor(name: str, raw_score: int, raw_max: int, weight: int, detail: str) -> int:
        if raw_max <= 0:
            safe_score = 0
        else:
            safe_score = int(round((max(0, min(raw_score, raw_max)) / float(raw_max)) * weight))
        factors.append(
            {
                "name": name,
                "score": safe_score,
                "max_score": weight,
                "raw_score": max(0, min(raw_score, raw_max)),
                "raw_max_score": raw_max,
                "detail": detail,
            }
        )
        return safe_score

    metadata_score = 0
    if repo_block.get("full_name"):
        metadata_score += 8
    if repo_block.get("description"):
        metadata_score += 6
    if repo_block.get("language"):
        metadata_score += 4
    if repo_block.get("topics"):
        metadata_score += 4
    if repo_block.get("license"):
        metadata_score += 2
    if repo_block.get("pushed_at"):
        metadata_score += 6
    metadata_detail = "描述=%s, 语言=%s, 主题=%s, 许可证=%s, 最近推送=%s" % (
        bool(repo_block.get("description")),
        bool(repo_block.get("language")),
        bool(repo_block.get("topics")),
        bool(repo_block.get("license")),
        bool(repo_block.get("pushed_at")),
    )
    metadata_points = add_factor("仓库元数据完整度", metadata_score, 30, weights["metadata"], metadata_detail)

    recency_map = {
        "快速迭代": 5,
        "稳定活跃": 4,
        "维护模式": 2,
        "低活跃/可能停滞": 1,
        "未知": 0,
    }
    stage = repo_block.get("project_stage") or "未知"
    activity_score = min(len(commits), 5) * 2 + min(len(issues), 5) * 2 + recency_map.get(stage, 0)
    activity_detail = "issues=%s, commits=%s, stage=%s" % (len(issues), len(commits), stage)
    activity_points = add_factor("活跃度证据", activity_score, 25, weights["activity"], activity_detail)

    source_count = len({(item.get("source") or "").strip() for item in external if (item.get("source") or "").strip()})
    external_score = int(min(len(external), 8) / 8.0 * 14) + min(source_count, 3) * 2
    external_detail = "external=%s, source_diversity=%s" % (len(external), source_count)
    external_points = add_factor("外部信号覆盖", external_score, 20, weights["external"], external_detail)

    if with_extract:
        extract_items = [item.get("extract") or {} for item in external if item.get("extract")]
        attempts = len(extract_items)
        success = len([item for item in extract_items if item.get("ok")])
        if attempts == 0:
            extract_score = 0
        else:
            extract_score = int(min(attempts, 3) / 3.0 * 5) + int(success / float(attempts) * 10)
        extract_detail = "enabled=true, attempts=%s, success=%s" % (attempts, success)
        extract_points = add_factor("内容提取可验证性", extract_score, 15, weights["extract"], extract_detail)
    else:
        extract_points = add_factor("内容提取可验证性", 8, 15, weights["extract"], "enabled=false, 跳过抓取，给中性分")

    error_count = len([note for note in notes if ("_failed" in note) or ("error" in note.lower())])
    if error_count == 0:
        stability_score = 10
    elif error_count <= 2:
        stability_score = 6
    elif error_count <= 4:
        stability_score = 3
    else:
        stability_score = 0
    stability_points = add_factor("执行稳定性", stability_score, 10, weights["stability"], "error_like_notes=%s" % error_count)

    score = metadata_points + activity_points + external_points + extract_points + stability_points
    if score >= 80:
        level = "高"
    elif score >= 60:
        level = "中"
    else:
        level = "低"

    return {
        "score": score,
        "level": level,
        "profile": profile_config["display_name"],
        "profile_desc": profile_config["description"],
        "factors": factors,
    }


def _resolve_repo(target: str, settings: Settings) -> Tuple[Optional[str], Optional[str], List[str]]:
    notes: List[str] = []
    parsed = _repo_from_target(target)
    if parsed:
        return parsed[0], parsed[1], notes

    per_source_budget_ms = max(int(getattr(settings, "search_timeout_seconds", 30) or 30), 1) * 3000
    search = run_multi_source_search(
        query="site:github.com %s" % target,
        settings=settings,
        mode="deep",
        limit=8,
        intent="resource",
        budget_max_latency_ms=per_source_budget_ms,
    )
    for row in search.results:
        parsed_url = _repo_from_url(row.url)
        if parsed_url:
            notes.append("repo_resolved_by_search:%s" % row.url)
            return parsed_url[0], parsed_url[1], notes
    notes.extend(search.notes)
    notes.append("repo_not_resolved")
    return None, None, notes


def _collect_repo_data(
    owner: str,
    repo: str,
    settings: Settings,
    issues_limit: int,
    commits_limit: int,
) -> Tuple[Dict, List[Dict], List[Dict], List[str]]:
    notes: List[str] = []
    headers = _github_headers(settings.github_token)
    timeout = settings.search_timeout_seconds
    base = "https://api.github.com/repos/%s/%s" % (owner, repo)

    repo_info: Dict = {}
    issues: List[Dict] = []
    commits: List[Dict] = []

    try:
        repo_resp = requests.get(base, headers=headers, timeout=timeout)
        repo_resp.raise_for_status()
        repo_info = repo_resp.json()
    except Exception as exc:
        notes.append("repo_api_failed:%s" % exc)
        return repo_info, issues, commits, notes

    try:
        readme_resp = requests.get(base + "/readme", headers=headers, timeout=timeout)
        if readme_resp.status_code == 200:
            readme_payload = readme_resp.json()
            readme_excerpt = _decode_github_readme(
                readme_payload.get("content", ""),
                readme_payload.get("encoding", ""),
            )
            if readme_excerpt:
                repo_info["readme_excerpt"] = readme_excerpt
        else:
            notes.append("readme_api_skipped:http_%s" % readme_resp.status_code)
    except Exception as exc:
        notes.append("readme_api_failed:%s" % exc)

    try:
        issues_resp = requests.get(
            base + "/issues",
            headers=headers,
            params={"state": "open", "sort": "comments", "direction": "desc", "per_page": max(issues_limit * 2, 10)},
            timeout=timeout,
        )
        issues_resp.raise_for_status()
        raw_issues = issues_resp.json()
        for item in raw_issues:
            if "pull_request" in item:
                continue
            risk_tags = _issue_risk_tags(item.get("title", ""), item.get("body", "") or "")
            maintainer_comments = 0
            maintainer_logins: List[str] = []
            if _is_maintainer_association(item.get("author_association", "")):
                maintainer_comments += 1
                if item.get("user", {}).get("login"):
                    maintainer_logins.append(item["user"]["login"])

            comments_url = item.get("comments_url") or ""
            if item.get("comments", 0) and comments_url:
                try:
                    comments_resp = requests.get(
                        comments_url,
                        headers=headers,
                        params={"per_page": min(max(item.get("comments", 0), 5), 30)},
                        timeout=timeout,
                    )
                    if comments_resp.status_code == 200:
                        for comment in comments_resp.json():
                            if _is_maintainer_association(comment.get("author_association", "")):
                                maintainer_comments += 1
                                login = (comment.get("user") or {}).get("login", "")
                                if login and login not in maintainer_logins:
                                    maintainer_logins.append(login)
                    else:
                        notes.append("issue_comments_skipped:#%s:http_%s" % (item.get("number"), comments_resp.status_code))
                except Exception as exc:
                    notes.append("issue_comments_failed:#%s:%s" % (item.get("number"), exc))

            issues.append(
                {
                    "number": item.get("number"),
                    "title": item.get("title", ""),
                    "url": item.get("html_url", ""),
                    "comments": item.get("comments", 0),
                    "state": item.get("state", ""),
                    "updated_at": item.get("updated_at", ""),
                    "risk_tags": risk_tags,
                    "maintainer_participated": maintainer_comments > 0,
                    "maintainer_comment_count": maintainer_comments,
                    "maintainer_logins": maintainer_logins[:3],
                    "quality_score": _issue_quality_score(
                        comments=item.get("comments", 0),
                        maintainer_comment_count=maintainer_comments,
                        risk_tags=risk_tags,
                        updated_at=item.get("updated_at", ""),
                    ),
                }
            )
            if len(issues) >= issues_limit:
                break

        issues.sort(
            key=lambda node: (
                int(node.get("quality_score", 0)),
                int(node.get("comments", 0)),
                node.get("updated_at", ""),
            ),
            reverse=True,
        )
    except Exception as exc:
        notes.append("issues_api_failed:%s" % exc)

    try:
        commits_resp = requests.get(
            base + "/commits",
            headers=headers,
            params={"per_page": max(commits_limit, 1)},
            timeout=timeout,
        )
        commits_resp.raise_for_status()
        for item in commits_resp.json():
            commit = item.get("commit") or {}
            meta = commit.get("committer") or {}
            commits.append(
                {
                    "sha": (item.get("sha") or "")[:7],
                    "message": _trim_text(commit.get("message", ""), 140),
                    "date": meta.get("date", ""),
                    "url": item.get("html_url", ""),
                }
            )
    except Exception as exc:
        notes.append("commits_api_failed:%s" % exc)

    return repo_info, issues, commits, notes


def _collect_external(
    owner: str,
    repo: str,
    settings: Settings,
    external_limit: int,
    extract_top: int,
    with_extract: bool,
) -> Tuple[List[Dict], List[str], List[Dict], Dict[str, Dict[str, str]]]:
    notes: List[str] = []
    external_timeout = _external_timeout_seconds(settings)
    external_model = _external_model_profile(settings)
    fallback_source = _external_fallback_source(settings)
    followup_rounds = _external_followup_rounds(settings)
    notes.append(
        "external_search_profile:model=%s,timeout=%s,fallback=%s,followup_rounds=%s"
        % (external_model, external_timeout, fallback_source, followup_rounds)
    )
    deepwiki_item, deepwiki_notes = _collect_deepwiki(owner, repo, settings)
    notes.extend(deepwiki_notes)
    zread_item, zread_notes = _collect_zread(owner, repo, settings)
    notes.extend(zread_notes)
    queries = _build_external_queries(owner, repo)
    merged: List[Dict] = []
    competitor_scores: Dict[str, Dict[str, object]] = {}
    seen = set()
    fetch_limit = max(external_limit * 2, 8)
    failed_count = 0

    def append_rows(rows: List, query_tag: str) -> None:
        for row in rows:
            dedup_key = (row.url or "").strip().rstrip("/")
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            merged.append(
                {
                    "title": row.title,
                    "url": row.url,
                    "snippet": _trim_text(row.snippet, 220),
                    "source": row.source,
                    "published_date": row.published_date,
                    "_relevance": _external_relevance_score(owner, repo, row.title, row.snippet, row.url),
                }
            )

            comp_score = _maybe_competitor_score(owner, repo, row.title, row.snippet, row.url, query_tag)
            if comp_score > 0:
                parsed = _repo_from_url(row.url)
                if parsed:
                    label = "%s/%s" % (parsed[0], parsed[1])
                    canonical_url = "https://github.com/%s/%s" % (parsed[0], parsed[1])
                else:
                    label = _trim_text(row.title or row.url, 80)
                    canonical_url = row.url
                key = (canonical_url or "").strip().rstrip("/")
                prior = competitor_scores.get(key)
                if not prior or int(prior.get("score", 0)) < comp_score:
                    competitor_scores[key] = {
                        "repo": label,
                        "url": canonical_url,
                        "evidence_title": row.title,
                        "source": row.source,
                        "score": comp_score,
                    }

    for query_spec in queries:
        query = str(query_spec.get("query") or "").strip()
        query_intent = str(query_spec.get("intent") or "exploratory")
        query_tag = str(query_spec.get("tag") or "")
        boost_domains = [str(item).strip() for item in (query_spec.get("boost_domains") or []) if str(item).strip()]
        primary_sources = _preferred_sources_for_query(query_tag, settings)
        if not query:
            continue
        rows, query_notes, failed = _run_external_query(
            query=query,
            query_intent=query_intent,
            query_tag=query_tag,
            boost_domains=boost_domains,
            fetch_limit=fetch_limit,
            settings=settings,
            primary_sources=primary_sources,
            model_profile=external_model,
            timeout_seconds=external_timeout,
            fallback_source=fallback_source,
        )
        notes.extend(query_notes)
        failed_count += failed
        append_rows(rows, query_tag=query_tag)

    seen_followup_queries = set()
    for round_idx in range(1, followup_rounds + 1):
        followups = _build_followup_queries(owner, repo, merged, list(competitor_scores.values()))
        followups = [item for item in followups if str(item.get("query") or "").strip() not in seen_followup_queries]
        if not followups:
            break
        notes.append("external_followup_queries:%s" % len(followups))
        notes.append("external_followup_round:%s:queries:%s" % (round_idx, len(followups)))
        round_added = 0
        for query_spec in followups:
            query = str(query_spec.get("query") or "").strip()
            query_intent = str(query_spec.get("intent") or "exploratory")
            query_tag = str(query_spec.get("tag") or "followup")
            boost_domains = [str(item).strip() for item in (query_spec.get("boost_domains") or []) if str(item).strip()]
            primary_sources = _preferred_sources_for_query(query_tag, settings)
            if not query:
                continue
            seen_followup_queries.add(query)
            before = len(merged)
            rows, query_notes, failed = _run_external_query(
                query=query,
                query_intent=query_intent,
                query_tag=query_tag,
                boost_domains=boost_domains,
                fetch_limit=fetch_limit,
                settings=settings,
                primary_sources=primary_sources,
                model_profile=external_model,
                timeout_seconds=external_timeout,
                fallback_source=fallback_source,
            )
            notes.extend(query_notes)
            failed_count += failed
            append_rows(rows, query_tag=query_tag)
            delta = len(merged) - before
            round_added += max(0, delta)
            notes.append("external_followup_used:%s:%s" % (query_tag, len(rows)))
        if round_added <= 0:
            notes.append("external_followup_round:%s:no_new_rows" % round_idx)
            break

    ranked = sorted(
        merged,
        key=lambda item: (
            int(item.get("_relevance") or 0),
            _source_priority(item.get("source", "")),
            1 if item.get("published_date") else 0,
            item.get("published_date") or "",
        ),
        reverse=True,
    )
    strong = [item for item in ranked if int(item.get("_relevance") or 0) >= 3]
    if not strong:
        selected = _seed_repo_external(owner, repo, external_limit)
        notes.append("external_relevance_seeded_from_repo")
    else:
        selected = list(strong[:external_limit])
        selected_urls = {item.get("url") for item in selected}
        if len(selected) < external_limit:
            for item in ranked:
                if item.get("url") in selected_urls:
                    continue
                selected.append(item)
                selected_urls.add(item.get("url"))
                if len(selected) >= external_limit:
                    break
            notes.append("external_relevance_fallback_used:%s" % max(0, external_limit - len(strong)))
    notes.append("external_relevance_selected:%s/%s" % (len([i for i in selected if int(i.get("_relevance") or 0) >= 3]), len(selected)))

    if deepwiki_item:
        deepwiki_url = (deepwiki_item.get("url") or "").strip().rstrip("/")
        selected = [item for item in selected if (item.get("url") or "").strip().rstrip("/") != deepwiki_url]
        selected.insert(0, deepwiki_item)
        selected = selected[:external_limit]
        notes.append("external_deepwiki_prioritized")
    if zread_item:
        zread_url = (zread_item.get("url") or "").strip().rstrip("/")
        selected = [item for item in selected if (item.get("url") or "").strip().rstrip("/") != zread_url]
        insert_at = 1 if deepwiki_item else 0
        selected.insert(insert_at, zread_item)
        selected = selected[:external_limit]
        notes.append("external_zread_prioritized")

    stabilized = _inject_seed_when_unstable(owner, repo, selected, external_limit, failed_count)
    if len(stabilized) != len(selected) or any(a.get("url") != b.get("url") for a, b in zip(stabilized, selected)):
        notes.append("external_failure_seed_injected:%s" % failed_count)
    selected = stabilized

    for item in selected:
        item.pop("_relevance", None)

    coverage = _build_index_coverage(owner, repo, selected, notes)
    if coverage["arxiv"]["status"] != "found":
        notes.append("arxiv_unavailable:not_found_in_external")
    if coverage["zread"]["status"] != "found":
        notes.append("zread_unavailable:not_found_in_external")

    competitors = sorted(
        competitor_scores.values(),
        key=lambda item: (int(item.get("score", 0)), item.get("repo", "")),
        reverse=True,
    )
    competitors = competitors[:3]
    for item in competitors:
        item.pop("score", None)

    if with_extract and extract_top > 0:
        prioritized = sorted(
            selected,
            key=lambda item: 0 if (urlparse(item.get("url", "")).hostname or "").lower() in _RISKY_HOSTS else 1,
        )
        for item in prioritized[:extract_top]:
            out = run_extract_pipeline(url=item["url"], settings=settings, max_chars=1200)
            item["extract"] = {
                "ok": out.ok,
                "engine": out.engine,
                "notes": out.notes,
                "summary": _trim_text(out.markdown or "", 280),
            }
    return selected, notes, competitors, coverage


def run_github_explorer(
    target: str,
    settings: Settings,
    issues_limit: int = 5,
    commits_limit: int = 5,
    external_limit: int = 8,
    extract_top: int = 2,
    with_extract: bool = True,
    confidence_profile: str = "deep",
) -> Dict:
    owner, repo, resolve_notes = _resolve_repo(target, settings)
    if not owner or not repo:
        return {
            "ok": False,
            "target": target,
            "notes": resolve_notes,
            "error": "无法解析 GitHub 仓库，请直接传入 URL 或 owner/repo",
        }

    repo_info, issues, commits, repo_notes = _collect_repo_data(owner, repo, settings, issues_limit, commits_limit)
    external, external_notes, competitors, index_coverage = _collect_external(
        owner, repo, settings, external_limit, extract_top, with_extract
    )
    all_notes = resolve_notes + repo_notes + external_notes

    repo_url = "https://github.com/%s/%s" % (owner, repo)
    repo_block = {
        "owner": owner,
        "name": repo,
        "full_name": repo_info.get("full_name", "%s/%s" % (owner, repo)),
        "url": repo_info.get("html_url", repo_url),
        "description": repo_info.get("description", ""),
        "readme_excerpt": repo_info.get("readme_excerpt", ""),
        "language": repo_info.get("language", ""),
        "topics": repo_info.get("topics") or [],
        "license": ((repo_info.get("license") or {}).get("spdx_id") or ""),
        "stars": repo_info.get("stargazers_count", 0),
        "forks": repo_info.get("forks_count", 0),
        "open_issues": repo_info.get("open_issues_count", 0),
        "updated_at": repo_info.get("updated_at", ""),
        "pushed_at": repo_info.get("pushed_at", ""),
        "project_stage": _infer_project_stage(repo_info.get("pushed_at")),
    }
    confidence = _build_confidence(
        repo_block=repo_block,
        issues=issues,
        commits=commits,
        external=external,
        notes=all_notes,
        with_extract=with_extract,
        profile=confidence_profile,
    )
    report = {
        "ok": True,
        "repo": repo_block,
        "issues": issues,
        "commits": commits,
        "external": external,
        "comparisons": competitors,
        "index_coverage": index_coverage,
        "confidence": confidence,
        "notes": all_notes,
    }
    return report
