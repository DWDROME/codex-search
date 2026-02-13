import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests


def _safe_results(items: List[Dict], source: str) -> List[Dict]:
    out: List[Dict] = []
    for item in items:
        url = item.get("url", "")
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                continue
        except Exception:
            continue

        out.append(
            {
                "title": item.get("title", ""),
                "url": url,
                "snippet": item.get("snippet", ""),
                "published_date": item.get("published_date", ""),
                "source": source,
            }
        )
    return out


def search_exa(query: str, api_key: str, limit: int, timeout: int) -> List[Dict]:
    response = requests.post(
        "https://api.exa.ai/search",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={"query": query, "numResults": limit, "type": "auto"},
        timeout=timeout,
    )
    response.raise_for_status()
    rows = []
    for item in response.json().get("results", []):
        rows.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("text", item.get("snippet", "")),
                "published_date": item.get("publishedDate", ""),
            }
        )
    return _safe_results(rows, "exa")


def search_tavily(
    query: str,
    api_key: str,
    api_url: str,
    limit: int,
    timeout: int,
    include_answer: bool,
    freshness: Optional[str],
) -> Dict:
    payload: Dict = {
        "api_key": api_key,
        "query": query,
        "max_results": limit,
        "include_answer": include_answer,
    }
    if freshness:
        days_map = {"pd": 1, "pw": 7, "pm": 30, "py": 365}
        if freshness in days_map:
            payload["days"] = days_map[freshness]

    response = requests.post(
        api_url.rstrip("/") + "/search",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    rows = []
    for item in data.get("results", []):
        rows.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "published_date": item.get("published_date", ""),
            }
        )
    return {
        "results": _safe_results(rows, "tavily"),
        "answer": data.get("answer"),
    }


def _extract_sse_content(raw: str) -> str:
    content = ""
    event_lines: List[str] = []
    for line in raw.split("\n"):
        striped = line.strip()
        if not striped:
            if event_lines:
                chunk = "".join(event_lines)
                event_lines = []
                try:
                    node = json.loads(chunk)
                    choice = (node.get("choices") or [{}])[0]
                    delta = choice.get("delta") or choice.get("message") or {}
                    text = delta.get("content") or choice.get("text") or ""
                    if text:
                        content += text
                except Exception:
                    pass
            continue

        if striped in ("data: [DONE]", "data:[DONE]"):
            continue

        if striped.startswith("data:"):
            event_lines.append(striped[5:].lstrip())

    if event_lines:
        try:
            node = json.loads("".join(event_lines))
            choice = (node.get("choices") or [{}])[0]
            delta = choice.get("delta") or choice.get("message") or {}
            text = delta.get("content") or choice.get("text") or ""
            if text:
                content += text
        except Exception:
            pass

    return content


def _strip_code_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _parse_result_payload(content: str) -> Dict:
    if not content:
        return {}
    normalized = _strip_code_fence(content)
    try:
        return json.loads(normalized)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", normalized)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def search_grok(
    query: str,
    api_url: str,
    api_key: str,
    model: str,
    limit: int,
    timeout: int,
    freshness: Optional[str],
) -> List[Dict]:
    time_keywords = ["current", "now", "today", "latest", "recent", "本周", "今天", "最新"]
    needs_time = any(k in query.lower() for k in time_keywords)
    time_context = ""
    if needs_time:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        time_context = "\n[Current time: %s]\n" % now

    freshness_hint = ""
    if freshness:
        hints = {"pd": "past 24 hours", "pw": "past week", "pm": "past month", "py": "past year"}
        freshness_hint = "\nFocus on results from the %s." % hints.get(freshness, "recent period")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a web search engine. Return ONLY valid JSON with format: "
                    "{\"results\":[{\"title\":\"...\",\"url\":\"...\","
                    "\"snippet\":\"...\",\"published_date\":\"YYYY-MM-DD or empty\"}]}"
                ),
            },
            {
                "role": "user",
                "content": time_context + "<query>" + query + "</query>" + freshness_hint,
            },
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
        "stream": False,
    }

    response = requests.post(
        api_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    text = response.text.strip()
    content = ""
    if "text/event-stream" in response.headers.get("content-type", "") or text.startswith("data:"):
        content = _extract_sse_content(text)
    else:
        node = json.loads(text)
        choices = node.get("choices") or []
        if not choices:
            return []
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or choice.get("text") or ""
        if isinstance(content, list):
            content = " ".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)

    data = _parse_result_payload(content)
    return _safe_results(data.get("results", []), "grok")[:limit]
