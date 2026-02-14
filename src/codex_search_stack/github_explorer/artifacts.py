import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from ..config import Settings
from ..search.orchestrator import run_multi_source_search

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _arxiv_pdf_url(url: str) -> str:
    host = _host(url)
    if "arxiv.org" not in host:
        return ""
    try:
        parsed = urlparse(url)
        path = parsed.path or ""
    except Exception:
        return ""
    if path.startswith("/pdf/"):
        if path.endswith(".pdf"):
            return "https://arxiv.org%s" % path
        return "https://arxiv.org%s.pdf" % path
    if path.startswith("/abs/"):
        paper_id = path.split("/abs/", 1)[1].strip("/")
        if not paper_id:
            return ""
        return "https://arxiv.org/pdf/%s.pdf" % paper_id
    return ""


def _direct_pdf_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ""
        path = (parsed.path or "").lower()
        if path.endswith(".pdf"):
            return url
    except Exception:
        return ""
    return ""


def _safe_filename(text: str, fallback: str) -> str:
    raw = _SAFE_NAME_RE.sub("_", (text or "").strip()).strip("._")
    if not raw:
        raw = fallback
    return raw[:120]


def _repo_slug(result: Dict[str, Any]) -> str:
    repo = result.get("repo") or {}
    full_name = (repo.get("full_name") or "").strip()
    if full_name:
        return _safe_filename(full_name.replace("/", "_"), "repo")
    return "repo"


def collect_book(result: Dict[str, Any], settings: Settings, max_items: int) -> Dict[str, Any]:
    max_items = max(0, int(max_items))
    book: Dict[str, Any] = {"papers": [], "deepwiki": [], "zread": [], "notes": []}
    if max_items == 0:
        return book

    seen_papers = set()
    seen_links = set()
    external = result.get("external") or []
    for item in external:
        url = item.get("url", "")
        host = _host(url)
        if not url:
            continue
        if "deepwiki.com" in host and url not in seen_links:
            seen_links.add(url)
            book["deepwiki"].append({"title": item.get("title", "DeepWiki"), "url": url, "source": item.get("source", "")})
        if "zread" in host and url not in seen_links:
            seen_links.add(url)
            book["zread"].append({"title": item.get("title", "zread"), "url": url, "source": item.get("source", "")})
        paper_pdf_url = _arxiv_pdf_url(url) or _direct_pdf_url(url)
        if paper_pdf_url:
            key = paper_pdf_url.rstrip("/")
            if key in seen_papers:
                continue
            seen_papers.add(key)
            book["papers"].append(
                {
                    "title": item.get("title", ""),
                    "url": url,
                    "source": item.get("source", ""),
                    "pdf_url": paper_pdf_url,
                }
            )

    coverage = result.get("index_coverage") or {}
    deepwiki = coverage.get("deepwiki") or {}
    if deepwiki.get("status") == "found" and deepwiki.get("url") and not book["deepwiki"]:
        book["deepwiki"].append({"title": "DeepWiki", "url": deepwiki.get("url"), "source": "index_coverage"})
    zread = coverage.get("zread") or {}
    if zread.get("status") == "found" and zread.get("url") and not book["zread"]:
        book["zread"].append({"title": "zread", "url": zread.get("url"), "source": "index_coverage"})

    if len(book["papers"]) < max_items and result.get("ok"):
        repo = result.get("repo") or {}
        full_name = (repo.get("full_name") or "").strip()
        repo_name = (repo.get("name") or "").strip()
        if full_name or repo_name:
            query = 'site:arxiv.org ("%s" OR "%s")' % (full_name or repo_name, repo_name or full_name)
            search = run_multi_source_search(
                query=query,
                settings=settings,
                mode="deep",
                limit=max(max_items * 3, 6),
                intent="resource",
                sources=["exa", "grok"],
                budget_max_calls=2,
                budget_max_latency_ms=max(int(getattr(settings, "search_timeout_seconds", 30) or 30), 1) * 2000,
            )
            book["notes"].extend(search.notes or [])
            for row in search.results:
                if len(book["papers"]) >= max_items:
                    break
                url = row.url or ""
                if "arxiv.org" not in _host(url):
                    continue
                key = url.rstrip("/")
                if key in seen_papers:
                    continue
                seen_papers.add(key)
                book["papers"].append(
                    {
                        "title": row.title or "",
                        "url": url,
                        "source": row.source or "",
                        "pdf_url": _arxiv_pdf_url(url),
                    }
                )
            book["notes"].append("book_arxiv_probe:%s" % len(book["papers"]))

    book["papers"] = book["papers"][:max_items]
    return book


def attach_book_to_result(result: Dict[str, Any], settings: Settings, max_items: int) -> None:
    if not result.get("ok"):
        return
    book = collect_book(result, settings=settings, max_items=max_items)
    result["book"] = book

    papers = list(book.get("papers") or [])
    if papers:
        coverage = result.get("index_coverage") or {}
        arxiv_cov = coverage.get("arxiv") or {}
        if str(arxiv_cov.get("status", "")).lower() != "found":
            coverage["arxiv"] = {"status": "found", "url": papers[0].get("url", ""), "source": "book_probe"}
            result["index_coverage"] = coverage
            result["notes"] = list(result.get("notes") or []) + ["arxiv_coverage_promoted_from_book"]

    if book.get("notes"):
        result["notes"] = list(result.get("notes") or []) + ["book_notes:%s" % len(book.get("notes") or [])]


def _download_binary(url: str, dest: Path, timeout: int) -> str:
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        with dest.open("wb") as fw:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    fw.write(chunk)
        return ""
    except Exception as exc:
        return str(exc)


def persist_explore_artifacts(
    result: Dict[str, Any],
    markdown_text: str,
    project_root: Path,
    out_dir: str,
    download_book: bool,
    timeout: int,
) -> Dict[str, Any]:
    if out_dir.strip():
        base_dir = Path(out_dir).expanduser()
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        base_dir = project_root / ".runtime" / "github-explorer" / ("%s_%s" % (_repo_slug(result), ts))
    base_dir.mkdir(parents=True, exist_ok=True)

    report_md = base_dir / "report.md"
    report_json = base_dir / "report.json"
    report_md.write_text(markdown_text, encoding="utf-8")
    report_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    book = result.get("book") or {}
    book_dir = base_dir / "book"
    papers_dir = book_dir / "papers"
    book_dir.mkdir(parents=True, exist_ok=True)
    papers_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    lines: List[str] = [
        "# Book 资料包",
        "",
        "- generated_at_utc: %s" % datetime.now(timezone.utc).isoformat(),
        "- download_enabled: %s" % str(bool(download_book)).lower(),
        "",
        "## 论文",
        "",
    ]
    papers = book.get("papers") or []
    if not papers:
        lines.append("- 未找到")
    else:
        for idx, paper in enumerate(papers, start=1):
            title = paper.get("title", "") or ("paper_%s" % idx)
            url = paper.get("url", "")
            pdf_url = paper.get("pdf_url", "") or _arxiv_pdf_url(url)
            lines.append("- [%s](%s)" % (title, url))
            if pdf_url:
                lines.append("  - pdf_url: %s" % pdf_url)
            if download_book and pdf_url:
                file_name = _safe_filename(title, "paper_%s" % idx) + ".pdf"
                file_path = papers_dir / file_name
                err = _download_binary(pdf_url, file_path, timeout=max(10, timeout))
                if err:
                    failed += 1
                    lines.append("  - download: failed (%s)" % err)
                else:
                    downloaded += 1
                    lines.append("  - download: ok -> papers/%s" % file_name)
            else:
                lines.append("  - download: skipped")

    for key, label in [("deepwiki", "DeepWiki"), ("zread", "zread")]:
        lines.append("")
        lines.append("## %s" % label)
        lines.append("")
        refs = book.get(key) or []
        if not refs:
            lines.append("- 未找到")
        else:
            for row in refs:
                lines.append("- [%s](%s)" % (row.get("title", label), row.get("url", "")))

    book_readme = book_dir / "README.md"
    book_readme.write_text("\n".join(lines), encoding="utf-8")
    return {
        "out_dir": str(base_dir),
        "report_markdown": str(report_md),
        "report_json": str(report_json),
        "book_readme": str(book_readme),
        "book_downloaded": downloaded,
        "book_download_failed": failed,
    }
