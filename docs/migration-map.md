# Migration Map (Legacy -> Codex)

## Core mapping

- Legacy `search-layer/scripts/search.py`
  -> Codex `src/codex_search_stack/search/{sources,scoring,orchestrator}.py`
- Legacy `content-extract/scripts/content_extract.py`
  -> Codex `src/codex_search_stack/extract/pipeline.py`
- Legacy `mineru-extract/scripts/mineru_parse_documents.py`
  -> Codex `src/codex_search_stack/extract/mineru_adapter.py` (wrapper bridge)
- Legacy skill orchestration in `github-explorer/SKILL.md`
  -> Codex `src/codex_search_stack/github_explorer/{orchestrator,report}.py` + CLI `explore`

## Runtime differences

1. Legacy built-in tools are implicit (`web_search/web_fetch/browser`).
2. Codex migration makes API calls explicit in script layer.
3. MCP tools remain available, but this framework does not hard-bind to one agent runtime.

## Compatibility fixes included

- Python syntax adjusted to support Python 3.9+ (no `str | None` unions).
- Unified result contracts for easier agent chaining.
- Built-in Grok/Tavily key-pool retry path integrated into search/extract runtime.
- Brave source adapter has been removed; runtime now focuses on Exa/Tavily/Grok.

## Phase-6 delivered

1. Added confidence scoring for explorer report quality (`score/level/factors`).
2. Added smoke regression script (`scripts/smoke_phase6.sh`) covering compile/search/extract/explore.

## Phase-7 delivered

1. Added configurable confidence profiles (`deep` / `quick`) for explorer scoring.
2. Added CLI/env integration for confidence profile selection.
3. Extended smoke checks to validate profile behavior.

## Phase-8 delivered

1. Added CI smoke hook with masked env snapshot and auto online/offline decision.
2. Added GitHub Actions workflow to run smoke + upload reports.

## Next phase (planned)

1. Add optional platform-specific collectors (Reddit/X/GitHub Discussions).
2. Add profile-aware recommendation text in markdown report.
3. Add smoke matrix by profile (`deep` + `quick`) with stricter assertions.
