# Phase-6 Confidence + Smoke (2026-02-13)

## Goal

Close the migration loop for "可用性 + 可解释性":

- explorer 输出不仅给结果，还给可信度分层
- 提供一键 smoke 脚本覆盖核心链路（search/extract/explore）

## Delivered

### 1) Explorer confidence scoring

- File: `src/codex_search_stack/github_explorer/orchestrator.py`
- New field in `run_github_explorer` output:

```json
{
  "confidence": {
    "score": 0,
    "level": "低|中|高",
    "factors": [
      {
        "name": "仓库元数据完整度",
        "score": 0,
        "max_score": 30,
        "detail": "..."
      }
    ]
  }
}
```

- Current factors:
  - 仓库元数据完整度（0-30）
  - 活跃度证据（0-25）
  - 外部信号覆盖（0-20）
  - 内容提取可验证性（0-15）
  - 执行稳定性（0-10）

### 2) Markdown report confidence section

- File: `src/codex_search_stack/github_explorer/report.py`
- Added section: `✅ 结果置信度`
  - 综合分与级别
  - 各因子分项解释

### 3) Smoke regression script

- File: `scripts/smoke_phase6.sh`
- Coverage:
  1. `compileall`
  2. `cli --help`
  3. `search --mode deep`
  4. `extract` (normal page)
  5. `explore --format json` + confidence 字段校验
  6. `explore --format markdown` + 置信度段落校验

## Run

```bash
cd /path/to/codex-search
./scripts/smoke_phase6.sh
```

## Notes

- Script assumes env can provide at least one available source credential chain.
- `CODEX_WORKSPACE` defaults to `.runtime/codex-workspace` and can be overridden externally.
