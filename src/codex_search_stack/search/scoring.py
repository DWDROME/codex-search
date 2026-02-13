import re
from datetime import datetime, timezone
from typing import Dict, Iterable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


INTENT_WEIGHTS: Dict[str, Dict[str, float]] = {
    "factual": {"keyword": 0.4, "freshness": 0.1, "authority": 0.5},
    "status": {"keyword": 0.3, "freshness": 0.5, "authority": 0.2},
    "comparison": {"keyword": 0.4, "freshness": 0.2, "authority": 0.4},
    "tutorial": {"keyword": 0.4, "freshness": 0.1, "authority": 0.5},
    "exploratory": {"keyword": 0.3, "freshness": 0.2, "authority": 0.5},
    "news": {"keyword": 0.3, "freshness": 0.6, "authority": 0.1},
    "resource": {"keyword": 0.5, "freshness": 0.1, "authority": 0.4},
}

AUTHORITY_MAP = {
    "github.com": 1.0,
    "stackoverflow.com": 1.0,
    "developer.mozilla.org": 1.0,
    "wikipedia.org": 1.0,
    "arxiv.org": 1.0,
    "news.ycombinator.com": 0.8,
    "dev.to": 0.8,
    "reddit.com": 0.8,
    "medium.com": 0.6,
    "juejin.cn": 0.6,
}


def normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        clean_qs = {
            k: v for k, v in parse_qs(parsed.query).items() if not k.startswith("utm_")
        }
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path.rstrip("/"),
                parsed.params,
                urlencode(clean_qs, doseq=True) if clean_qs else "",
                "",
            )
        )
    except Exception:
        return url.rstrip("/")


def authority_score(url: str) -> float:
    try:
        host = (urlparse(url).hostname or "").removeprefix("www.")
    except Exception:
        return 0.4

    for known, score in AUTHORITY_MAP.items():
        if host == known or host.endswith("." + known):
            return score
    return 0.4


def freshness_score(published_date: str, snippet: str = "") -> float:
    if not published_date:
        year_match = re.search(r"\b(202[0-9])\b", snippet)
        if not year_match:
            return 0.5
        year = int(year_match.group(1))
        delta = datetime.now(timezone.utc).year - year
        if delta <= 0:
            return 0.9
        if delta == 1:
            return 0.6
        if delta <= 3:
            return 0.4
        return 0.2

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    now = datetime.now(timezone.utc)
    for fmt in formats:
        try:
            dt = datetime.strptime(published_date.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (now - dt).days
            if days <= 1:
                return 1.0
            if days <= 7:
                return 0.9
            if days <= 30:
                return 0.7
            if days <= 90:
                return 0.5
            if days <= 365:
                return 0.3
            return 0.1
        except Exception:
            continue
    return 0.5


def keyword_score(query: str, title: str, snippet: str) -> float:
    terms = {t for t in query.lower().split() if len(t) > 2}
    if not terms:
        return 0.5
    text = (title + " " + snippet).lower()
    matched = sum(1 for t in terms if t in text)
    return min(1.0, matched / len(terms))


def composite_score(
    query: str,
    intent: str,
    url: str,
    title: str,
    snippet: str,
    published_date: str,
    boost_domains: Iterable[str],
) -> float:
    weights = INTENT_WEIGHTS.get(intent, INTENT_WEIGHTS["exploratory"])
    kw = keyword_score(query, title, snippet)
    fr = freshness_score(published_date, snippet)
    au = authority_score(url)

    try:
        host = (urlparse(url).hostname or "").removeprefix("www.")
        for boost in boost_domains:
            if host == boost or host.endswith("." + boost):
                au = min(1.0, au + 0.2)
                break
    except Exception:
        pass

    return round(
        weights["keyword"] * kw
        + weights["freshness"] * fr
        + weights["authority"] * au,
        4,
    )
