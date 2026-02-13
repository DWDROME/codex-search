# Phase-8 CI Smoke Hook + Masked Snapshot (2026-02-13)

## Goal

把 smoke 回归接到 CI，同时避免在日志里暴露敏感 key：

- 统一 CI 入口
- 环境可观测（脱敏）
- 凭据不足时自动降级离线 smoke

## Delivered

### 1) CI hook script

- File: `scripts/ci_smoke_hook.sh`
- Features:
  - 先生成脱敏环境快照
  - 自动判断在线条件（search key/pool + extract key/token）
  - 支持模式：
    - `CI_SMOKE_MODE=auto`（默认）
    - `CI_SMOKE_MODE=offline`
    - `CI_SMOKE_MODE=online`
  - 输出报告到 `.runtime/ci-reports`：
    - `masked_env_snapshot.json`
    - `config_check.json`
    - `ci_smoke_decision.json`
    - `ci_smoke.log`

### 2) Masked env snapshot generator

- File: `scripts/masked_env_snapshot.py`
- Snapshot 内容：
  - secret 是否存在、长度、sha256 前缀（不输出明文）
  - URL 配置
  - 文件型配置是否存在（如 `KEY_POOL_FILE`、`MINERU_TOKEN_FILE`）
  - 当前 CI smoke 模式与 confidence profile

### 3) GitHub Actions workflow

- File: `.github/workflows/ci-smoke.yml`
- Steps:
  1. checkout
  2. setup python 3.9
  3. `pip install -e .`
  4. run `./scripts/ci_smoke_hook.sh`
  5. upload `.runtime/ci-reports` artifact

## Local run

```bash
cd /path/to/codex-search
./scripts/ci_smoke_hook.sh
```

Force offline:

```bash
CI_SMOKE_MODE=offline ./scripts/ci_smoke_hook.sh
```

Force online:

```bash
CI_SMOKE_MODE=online ./scripts/ci_smoke_hook.sh
```
