# Phase-2 MinerU Integration (2026-02-13)

## What changed

- Added `MINERU_TOKEN_FILE` support in config loading.
- Default token file is `other/mineru_key.txt` relative to this workspace.
- Added `MINERU_WORKSPACE` runtime path to avoid permission issues in restricted environments.
- `mineru_adapter` now injects `MINERU_TOKEN`, `MINERU_API_BASE`, `CODEX_WORKSPACE` into subprocess env.
- Improved MinerU error notes to include subprocess return code and wrapper JSON errors.

## Why

- The reused MinerU wrapper writes output under workspace cache directories.
- In Codex sandbox, writing outside project workspace can fail with permission errors.
- Setting workspace inside project keeps extraction artifacts writable and auditable.

## External reference

- MinerU API docs: https://mineru.net/apiManage/docs

## Expected env values

```bash
MINERU_TOKEN_FILE=~/.codex/secrets/mineru_key.txt
MINERU_API_BASE=https://mineru.net
MINERU_WORKSPACE=./.runtime/codex-workspace
```

## Validation command

```bash
PYTHONPATH="other/codex-search/src" \
python3 -m codex_search_stack.cli extract "https://zhuanlan.zhihu.com/p/619438846" --max-chars 3000
```

Observed on 2026-02-13:

- `ok=true`, `engine=mineru`
- Artifacts are written under:
  - `./.runtime/codex-workspace/mineru-cache/...`
