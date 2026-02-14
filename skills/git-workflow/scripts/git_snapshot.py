#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path
from typing import List


def _run_git(repo: Path, args: List[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git command failed")
    return proc.stdout.strip()


def _list_lines(repo: Path, args: List[str]) -> List[str]:
    out = _run_git(repo, args)
    if not out:
        return []
    return [line for line in out.splitlines() if line.strip()]


def _inside_worktree(repo: Path) -> bool:
    try:
        out = _run_git(repo, ["rev-parse", "--is-inside-work-tree"])
        return out.strip().lower() == "true"
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect git repository snapshot for codex skill workflow")
    parser.add_argument("--repo", default=".", help="git repository path, default current directory")
    parser.add_argument("--max-status", type=int, default=50, help="max status lines to output")
    parser.add_argument("--max-commits", type=int, default=10, help="max recent commits")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    payload = {
        "ok": False,
        "repo": str(repo),
        "inside_worktree": False,
        "branch": "",
        "upstream": "",
        "ahead": 0,
        "behind": 0,
        "clean": False,
        "status": {
            "staged": 0,
            "modified": 0,
            "untracked": 0,
            "lines": [],
        },
        "recent_commits": [],
        "notes": [],
    }

    if not _inside_worktree(repo):
        payload["notes"].append("not_a_git_repository")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    payload["inside_worktree"] = True

    try:
        payload["branch"] = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    except Exception as exc:
        payload["notes"].append(f"branch_error:{exc}")

    try:
        payload["upstream"] = _run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    except Exception:
        payload["upstream"] = ""

    try:
        status_lines = _list_lines(repo, ["status", "--porcelain=v1"])
        payload["status"]["lines"] = status_lines[: max(0, int(args.max_status))]
        payload["status"]["staged"] = sum(1 for line in status_lines if len(line) > 1 and line[0] != " ")
        payload["status"]["modified"] = sum(1 for line in status_lines if len(line) > 1 and line[1] != " ")
        payload["status"]["untracked"] = sum(1 for line in status_lines if line.startswith("??"))
        payload["clean"] = len(status_lines) == 0
    except Exception as exc:
        payload["notes"].append(f"status_error:{exc}")

    if payload["upstream"]:
        try:
            ahead_behind = _run_git(repo, ["rev-list", "--left-right", "--count", f"{payload['upstream']}...HEAD"])
            parts = ahead_behind.split()
            if len(parts) == 2:
                payload["behind"] = int(parts[0])
                payload["ahead"] = int(parts[1])
        except Exception as exc:
            payload["notes"].append(f"upstream_compare_error:{exc}")

    try:
        max_commits = max(1, int(args.max_commits))
        log_lines = _list_lines(repo, ["log", f"-n{max_commits}", "--pretty=format:%h\t%s\t%ad", "--date=short"])
        commits = []
        for line in log_lines:
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            commits.append({"sha": parts[0], "subject": parts[1], "date": parts[2]})
        payload["recent_commits"] = commits
    except Exception as exc:
        payload["notes"].append(f"log_error:{exc}")

    payload["ok"] = True
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
