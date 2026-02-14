#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_search_stack.config import load_settings
from codex_search_stack.github_explorer import render_markdown, run_github_explorer
from codex_search_stack.github_explorer.artifacts import attach_book_to_result, persist_explore_artifacts
from codex_search_stack.validators import validate_explore_protocol


_REPO_TITLE_RE = re.compile(r"^# \[[^\]]+\]\(https?://github\.com/[^)]+\)", re.MULTILINE)
_ISSUE_LINE_RE = re.compile(r"- \[#\d+ .+\]\(https?://github\.com/.+/issues/\d+\)")
_COMMIT_LINE_RE = re.compile(r"- \[`[0-9a-f]{7}`\]\(https?://github\.com/.+/commit/[0-9a-f]+\)")
_EXTERNAL_LINE_RE = re.compile(r"^- \[[^\]]+\]\(https?://[^)]+\) \| source=", re.MULTILINE)
_COMPETITOR_LINE_RE = re.compile(r"^- \[[^\]]+\]\(https?://[^)]+\) \| source=", re.MULTILINE)
_LINK_LINE_RE = re.compile(r"^- \[[^\]]+\]\(https?://[^)]+\)", re.MULTILINE)
_MIN_COMMUNITY_SIGNALS = 6
_MIN_COMPETITORS = 4
_MIN_NEGATIVE_EVIDENCE = 2


def _section_body(markdown_text: str, header: str) -> str:
    idx = markdown_text.find(header)
    if idx < 0:
        return ""
    tail = markdown_text[idx + len(header) :]
    next_idx = tail.find("\n**")
    if next_idx < 0:
        return tail
    return tail[:next_idx]


def _section_between(markdown_text: str, start_header: str, end_header: str) -> str:
    start_idx = markdown_text.find(start_header)
    if start_idx < 0:
        return ""
    body_start = start_idx + len(start_header)
    end_idx = markdown_text.find(end_header, body_start)
    if end_idx < 0:
        end_idx = len(markdown_text)
    return markdown_text[body_start:end_idx]


def _count_link_rows(section_text: str) -> int:
    return len(_LINK_LINE_RE.findall(section_text or ""))


def _markdown_contract_violations(markdown_text: str) -> list[str]:
    violations: list[str] = []
    if not _REPO_TITLE_RE.search(markdown_text):
        violations.append("missing_repo_title_link")
    if "**🔥 精选 Issue**" not in markdown_text:
        violations.append("missing_issue_section")
    issue_body = _section_body(markdown_text, "**🔥 精选 Issue**")
    if issue_body and (not _ISSUE_LINE_RE.search(issue_body)) and ("- 未找到" not in issue_body):
        violations.append("missing_issue_links")
    if "**🛠 最近提交**" not in markdown_text:
        violations.append("missing_commit_section")
    commit_body = _section_body(markdown_text, "**🛠 最近提交**")
    if commit_body and (not _COMMIT_LINE_RE.search(commit_body)) and ("- 未找到" not in commit_body):
        violations.append("missing_commit_links")
    if "**📰 外部信号**" not in markdown_text:
        violations.append("missing_external_section")
    external_body = _section_body(markdown_text, "**📰 外部信号**")
    if external_body and (not _EXTERNAL_LINE_RE.search(external_body)) and ("- 未找到" not in external_body):
        violations.append("missing_external_links")
    if "**🧭 收录与索引**" not in markdown_text:
        violations.append("missing_index_section")
    if "**📚 Book 资料包**" not in markdown_text:
        violations.append("missing_book_section")
    if "**🆚 竞品对比**" not in markdown_text:
        violations.append("missing_competitor_section")
    competitor_body = _section_body(markdown_text, "**🆚 竞品对比**")
    if competitor_body and (not _COMPETITOR_LINE_RE.search(competitor_body)) and ("- 未找到" not in competitor_body):
        violations.append("missing_competitor_links")
    if "**📰 社区声量**" not in markdown_text:
        violations.append("missing_community_section")
    else:
        community_body = _section_between(markdown_text, "**📰 社区声量**", "**🧭 收录与索引**")
        community_count = _count_link_rows(community_body)
        if community_count < _MIN_COMMUNITY_SIGNALS:
            violations.append("community_signals_insufficient:%s" % community_count)
    if "**🆚 竞品对比**" in markdown_text:
        competitor_body_full = _section_between(markdown_text, "**🆚 竞品对比**", "**❎ 反对证据**")
        competitor_count = _count_link_rows(competitor_body_full)
        if competitor_count < _MIN_COMPETITORS:
            violations.append("competitors_insufficient:%s" % competitor_count)
    if "**❎ 反对证据**" not in markdown_text:
        violations.append("missing_negative_evidence_section")
    else:
        negative_body = _section_between(markdown_text, "**❎ 反对证据**", "**💬 我的判断**")
        negative_count = _count_link_rows(negative_body)
        if negative_count < _MIN_NEGATIVE_EVIDENCE:
            violations.append("negative_evidence_insufficient:%s" % negative_count)
    if "**💬 我的判断**" not in markdown_text:
        violations.append("missing_judgement_section")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex github-explorer wrapper")
    parser.add_argument("target", help="GitHub URL, owner/repo, or project keyword")
    parser.add_argument("--issues", type=int, default=5)
    parser.add_argument("--commits", type=int, default=5)
    parser.add_argument("--external-num", type=int, default=8)
    parser.add_argument("--extract-top", type=int, default=2)
    parser.add_argument("--no-extract", action="store_true")
    parser.add_argument("--confidence-profile", choices=["deep", "quick"], default="")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--book-max", type=int, default=5)
    parser.add_argument("--no-book-download", action="store_true")
    parser.add_argument("--no-artifacts", action="store_true")
    parser.add_argument(
        "--hard-fail-contract",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When true, markdown contract violations return non-zero and fail the run.",
    )

    args = parser.parse_args()
    err, normalized = validate_explore_protocol(
        issues=args.issues,
        commits=args.commits,
        external_num=args.external_num,
        extract_top=args.extract_top,
        output_format=args.format,
    )
    if err:
        err_map = {
            "issues must be between 3 and 20": "--issues must be between 3 and 20",
            "commits must be between 3 and 20": "--commits must be between 3 and 20",
            "external_num must be between 2 and 30": "--external-num must be between 2 and 30",
            "extract_top must be between 0 and external_num": "--extract-top must be between 0 and --external-num",
        }
        if err in err_map:
            parser.error(err_map[err])
        parser.error(err)
    normalized = normalized or {}

    settings = load_settings()

    result = run_github_explorer(
        target=args.target,
        settings=settings,
        issues_limit=max(1, int(normalized.get("issues", args.issues))),
        commits_limit=max(1, int(normalized.get("commits", args.commits))),
        external_limit=max(1, int(normalized.get("external_num", args.external_num))),
        extract_top=max(0, int(normalized.get("extract_top", args.extract_top))),
        with_extract=not args.no_extract,
        confidence_profile=(args.confidence_profile or settings.confidence_profile).strip().lower(),
    )

    if result.get("ok"):
        attach_book_to_result(result, settings=settings, max_items=max(0, args.book_max))

    markdown_text = render_markdown(result)
    artifacts = None
    if not args.no_artifacts:
        artifacts = persist_explore_artifacts(
            result=result,
            markdown_text=markdown_text,
            project_root=PROJECT_ROOT,
            out_dir=args.out_dir,
            download_book=(not args.no_book_download),
            timeout=max(10, int(getattr(settings, "extract_timeout_seconds", 30) or 30)),
        )
        result["artifacts"] = artifacts

    if str(normalized.get("output_format", args.format)) == "markdown":
        violations = _markdown_contract_violations(markdown_text)
        if artifacts:
            markdown_text += "\n\n**📁 输出目录**\n\n"
            markdown_text += "- %s\n" % artifacts.get("out_dir", "")
            markdown_text += "- book_downloaded=%s\n" % artifacts.get("book_downloaded", 0)
            markdown_text += "- book_download_failed=%s\n" % artifacts.get("book_download_failed", 0)
        if violations:
            markdown_text += "\n\n**⚠️ 协议校验告警**\n\n"
            for item in violations:
                markdown_text += "- %s\n" % item
        print(markdown_text)
        if not result.get("ok"):
            return 1
        if violations:
            return 3 if args.hard_fail_contract else 2
        return 0

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
