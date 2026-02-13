# Phase-3 GitHub Explorer Migration (2026-02-13)

## Goal

Port legacy `github-explorer` orchestration into Codex runtime while reusing:

- `search` layer (`run_multi_source_search`)
- `extract` layer (`run_extract_pipeline`)
- MinerU fallback path for anti-bot pages

## Delivered

- New CLI command: `explore`
- Repo resolution strategy:
  - GitHub URL / `owner/repo` direct parse
  - fallback: multi-source search with `site:github.com ...`
- Data collection:
  - GitHub repo metadata (`/repos/{owner}/{repo}`)
  - top issues by comments
  - recent commits
  - external signals from multi-source search
- Optional extraction on top external links (`--extract-top`, default 2)

## Command

```bash
PYTHONPATH="other/codex-search/src" \
uv run python -m codex_search_stack.cli explore "microsoft/graphrag" --format markdown
```

Optional:

```bash
PYTHONPATH="other/codex-search/src" \
uv run python -m codex_search_stack.cli explore "langchain-ai/langchain" \
  --issues 5 --commits 5 --external-num 8 --extract-top 2 --format json
```

## Notes

- `GITHUB_TOKEN` is optional but recommended for higher GitHub API rate limits.
- Without `GITHUB_TOKEN`, anonymous rate limits apply.
