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

    search = run_multi_source_search(
        query="site:github.com %s" % target,
        settings=settings,
        mode="deep",
        limit=8,
        intent="resource",
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
            issues.append(
                {
                    "number": item.get("number"),
                    "title": item.get("title", ""),
                    "url": item.get("html_url", ""),
                    "comments": item.get("comments", 0),
                    "state": item.get("state", ""),
                }
            )
            if len(issues) >= issues_limit:
                break
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
) -> Tuple[List[Dict], List[str]]:
    notes: List[str] = []
    queries = [
        '"%s/%s" review' % (owner, repo),
        "%s 评测 使用体验" % repo,
    ]
    merged: List[Dict] = []
    seen = set()
    for query in queries:
        result = run_multi_source_search(
            query=query,
            settings=settings,
            mode="deep",
            limit=max(external_limit, 5),
            intent="exploratory",
        )
        notes.extend(result.notes)
        for row in result.results:
            if row.url in seen:
                continue
            seen.add(row.url)
            merged.append(
                {
                    "title": row.title,
                    "url": row.url,
                    "snippet": _trim_text(row.snippet, 220),
                    "source": row.source,
                    "published_date": row.published_date,
                }
            )
            if len(merged) >= external_limit:
                break
        if len(merged) >= external_limit:
            break

    if with_extract and extract_top > 0:
        prioritized = sorted(
            merged,
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
    return merged, notes


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
    external, external_notes = _collect_external(owner, repo, settings, external_limit, extract_top, with_extract)
    all_notes = resolve_notes + repo_notes + external_notes

    repo_url = "https://github.com/%s/%s" % (owner, repo)
    repo_block = {
        "owner": owner,
        "name": repo,
        "full_name": repo_info.get("full_name", "%s/%s" % (owner, repo)),
        "url": repo_info.get("html_url", repo_url),
        "description": repo_info.get("description", ""),
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
        "confidence": confidence,
        "notes": all_notes,
    }
    return report
