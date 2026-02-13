# Phase-4 Built-in Key Pool Retry (2026-02-13)

## Goal

Embed Grok/Tavily key-pool behavior into Python runtime so CLI commands can auto-retry credentials without manually rotating config.

## Implemented

- Added `src/codex_search_stack/key_pool.py`
  - parses `service,url,key,weight` rows
  - strict CSV only (`service,url,key,weight`), invalid rows fail fast with line number
  - builds candidate lists with primary credential + pool credentials
- Search integration:
  - `search/orchestrator.py` now retries Grok/Tavily by candidate order
  - emits masked notes for failed/rotated candidates
- Extract integration:
  - `extract/pipeline.py` now retries Tavily extract by candidate order
  - falls back to MinerU after candidate attempts
- New config/env:
  - `KEY_POOL_FILE` (default `~/.codex/key-pool/pool.csv`)
  - `KEY_POOL_ENABLED` (default `true`)

## Usage

```bash
PYTHONPATH="other/codex-search/src" \
uv run python -m codex_search_stack.cli search "grok tavily key pool retry" --mode deep --num 3
```

```bash
PYTHONPATH="other/codex-search/src" \
uv run python -m codex_search_stack.cli explore "microsoft/graphrag" --format json
```

## Notes

- key is masked in runtime notes (only prefix/suffix shown).
- candidate ordering is deterministic: primary first, then pool entries by weight.

## Validation snapshots (2026-02-13)

- `search` path with invalid primary + valid pool candidate:
  - notes include `tavily_candidate_failed:...` and `tavily_pool_rotated:...`
- `extract` path with invalid primary + valid pool candidate:
  - `ok=true`, `engine=tavily_extract`
  - notes include `tavily_pool_rotated:...`
