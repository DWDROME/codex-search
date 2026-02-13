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
from codex_search_stack.validators import validate_explore_protocol


_REPO_TITLE_RE = re.compile(r"^# \[[^\]]+\]\(https?://github\.com/[^)]+\)", re.MULTILINE)
_ISSUE_LINE_RE = re.compile(r"- \[#\d+ .+\]\(https?://github\.com/.+/issues/\d+\)")
_EXTERNAL_LINE_RE = re.compile(r"\[.+\]\(https?://[^)]+\)")

def _markdown_contract_violations(markdown_text: str) -> list[str]:
    violations: list[str] = []
    if not _REPO_TITLE_RE.search(markdown_text):
        violations.append("missing_repo_title_link")
    if "**🔥 精选 Issue**" not in markdown_text:
        violations.append("missing_issue_section")
    if not _ISSUE_LINE_RE.search(markdown_text):
        violations.append("missing_issue_links")
    if "**📰 外部信号**" not in markdown_text:
        violations.append("missing_external_section")
    if not _EXTERNAL_LINE_RE.search(markdown_text):
        violations.append("missing_external_links")
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

    if str(normalized.get("output_format", args.format)) == "markdown":
        markdown_text = render_markdown(result)
        violations = _markdown_contract_violations(markdown_text)
        if violations:
            markdown_text += "\n\n**⚠️ 协议校验告警**\n\n"
            for item in violations:
                markdown_text += "- %s\n" % item
        print(markdown_text)
        if not result.get("ok"):
            return 1
        return 2 if violations else 0

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
