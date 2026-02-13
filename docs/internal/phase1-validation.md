# Phase-1 Validation (2026-02-13)

## 1) Syntax / startup checks

Commands:

```bash
uv run python -m compileall "other/codex-search/src"
PYTHONPATH="other/codex-search/src" uv run python -m codex_search_stack.cli --help
```

Result:

- compileall passed
- CLI help output is available through module run

## 2) Smoke checks (with current grok-search env)

Commands:

```bash
PYTHONPATH="/path/to/codex-search/src" \
uv run python -m codex_search_stack.cli search "号池 高级实现 例子" --mode deep --num 3

PYTHONPATH="/path/to/codex-search/src" \
uv run python -m codex_search_stack.cli extract "https://en.wikipedia.org/wiki/Web_scraping"
```

Observed:

- `search` returns mixed results from Tavily + Grok
- `extract` succeeds on Tavily path (`engine=tavily_extract`)

## 3) Fixes applied during validation

- `config.py`: fixed dotenv quote parsing bug
- `search/sources.py`:
  - fixed broken string literals
  - added robust Grok payload parsing (SSE + fenced JSON + JSON block fallback)
  - added content-list handling for chat responses
- `cli.py`: added `if __name__ == "__main__": ...` entrypoint
- `extract/pipeline.py`:
  - aligned Tavily payload to `urls: [url]`
  - reduced false-negative risk in anti-bot heuristics

## 4) Known gaps (next phase)

- MinerU is fallback-only right now; wrapper path and token still need integration validation in this project
- Search-layer intent routing and weighted scoring are available, but GitHub-explorer orchestration is not migrated yet
- Tavily/Grok key pool auto-rotation is currently external (existing zsh scripts), not yet bound into this Python CLI
