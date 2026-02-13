# Phase-7 Confidence Profile (2026-02-13)

## Goal

Make explorer confidence scoring adaptable by scenario:

- quick scan（快速扫库）  
- deep due diligence（深入尽调）

## Delivered

### 1) Scoring profile model

- File: `src/codex_search_stack/github_explorer/orchestrator.py`
- Added `_CONFIDENCE_PROFILES`:
  - `deep`: metadata/activity/extract 权重更高
  - `quick`: external/stability 权重更高

Returned payload now includes:

```json
{
  "confidence": {
    "score": 0,
    "level": "低|中|高",
    "profile": "deep|quick",
    "profile_desc": "...",
    "factors": [
      {
        "name": "...",
        "score": 0,
        "max_score": 0,
        "raw_score": 0,
        "raw_max_score": 0,
        "detail": "..."
      }
    ]
  }
}
```

### 2) CLI and env support

- File: `src/codex_search_stack/cli.py`
  - Added `explore --confidence-profile {deep,quick}`
- File: `src/codex_search_stack/config.py`
  - Added `Settings.confidence_profile`
  - Env default: `CONFIDENCE_PROFILE=deep`
- File: `.env.example`
  - Added `CONFIDENCE_PROFILE=deep`

### 3) Markdown and smoke updates

- File: `src/codex_search_stack/github_explorer/report.py`
  - Confidence section now prints `profile` and raw score context.
- File: `scripts/smoke_phase6.sh`
  - Added `quick` profile JSON verification.
  - Markdown verification checks `profile=quick` rendering.

## Validation commands

```bash
uv run python -m compileall "/path/to/codex-search/src"
PYTHONPATH="/path/to/codex-search/src" \
uv run python -m codex_search_stack.cli explore "microsoft/graphrag" --confidence-profile quick --format json
./scripts/smoke_phase6.sh
```
