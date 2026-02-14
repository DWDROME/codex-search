#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


PATTERNS: List[Tuple[str, str, str]] = [
    ("bearer_token", r"Bearer\s+[A-Za-z0-9_\-]{20,}", "high"),
    ("api_key_prefix", r"\b(?:sk|tvly)-[A-Za-z0-9_\-]{16,}\b", "high"),
    (
        "env_secret_assignment",
        r"\b(?:EXA_API_KEY|GROK_API_KEY|TAVILY_API_KEY|GITHUB_TOKEN|MINERU_TOKEN)\s*=\s*[^\s#]+",
        "high",
    ),
    ("local_home_path", r"/home/[A-Za-z0-9._-]+/", "medium"),
    ("key_pool_path", r"(?:~|/home/[A-Za-z0-9._-]+)/\.codex/key-pool/pool\.csv", "medium"),
]


def _run_git(repo: Path, args: List[str], *, allow_error: bool = False) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0 and not allow_error:
        raise RuntimeError(proc.stderr.strip() or "git command failed")
    return (proc.stdout or "").strip()


def _inside_worktree(repo: Path) -> bool:
    try:
        out = _run_git(repo, ["rev-parse", "--is-inside-work-tree"])
    except Exception:
        return False
    return out.lower() == "true"


def _collect_target_files(repo: Path, scope: str, max_files: int) -> List[Path]:
    files: List[Path] = []
    if scope == "staged":
        raw = _run_git(repo, ["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
    else:
        raw = _run_git(repo, ["status", "--porcelain=v1"])
        lines = []
        for line in raw.splitlines():
            if len(line) < 4:
                continue
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            lines.append(path.strip())

    seen = set()
    for rel in lines:
        path = (repo / rel).resolve()
        if path in seen:
            continue
        seen.add(path)
        if not path.exists() or not path.is_file():
            continue
        files.append(path)
        if len(files) >= max_files:
            break
    return files


def _is_text_blob(data: bytes) -> bool:
    return b"\x00" not in data


def _scan_file(path: Path, max_bytes: int) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    try:
        raw = path.read_bytes()
    except Exception:
        return findings

    if len(raw) > max_bytes:
        return findings
    if not _is_text_blob(raw):
        return findings

    text = raw.decode("utf-8", errors="ignore")
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for rule, pattern, severity in PATTERNS:
            if re.search(pattern, line):
                findings.append(
                    {
                        "path": str(path),
                        "line": str(idx),
                        "rule": rule,
                        "severity": severity,
                        "snippet": stripped[:200],
                    }
                )
    return findings


def _remote_findings(repo: Path) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    raw = _run_git(repo, ["remote", "-v"], allow_error=True)
    for line in raw.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        name, url = parts[0], parts[1]
        if re.search(r"https?://[^\s/@]+:[^\s@]+@", url):
            findings.append(
                {
                    "path": "(git remote)",
                    "line": "0",
                    "rule": "remote_embedded_credentials",
                    "severity": "high",
                    "snippet": f"{name} {url}",
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-commit/pre-push guardrails for git-workflow skill")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--scope", choices=["staged", "changed"], default="staged")
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--max-bytes", type=int, default=512000)
    parser.add_argument("--max-findings", type=int, default=100)
    parser.add_argument("--allow-findings", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    payload = {
        "ok": False,
        "repo": str(repo),
        "inside_worktree": False,
        "scope": args.scope,
        "files_scanned": 0,
        "findings_count": 0,
        "findings": [],
        "notes": [],
    }

    if not _inside_worktree(repo):
        payload["notes"].append("not_a_git_repository")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    payload["inside_worktree"] = True
    target_files = _collect_target_files(repo, args.scope, max(1, int(args.max_files)))
    payload["files_scanned"] = len(target_files)

    findings: List[Dict[str, str]] = []
    for path in target_files:
        findings.extend(_scan_file(path, max(1024, int(args.max_bytes))))
        if len(findings) >= args.max_findings:
            payload["notes"].append("max_findings_reached")
            break

    findings.extend(_remote_findings(repo))

    payload["findings"] = findings[: max(1, int(args.max_findings))]
    payload["findings_count"] = len(findings)
    payload["ok"] = True

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if findings and not args.allow_findings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
