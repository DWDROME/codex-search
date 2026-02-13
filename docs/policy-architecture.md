# Policy 架构草案（Core-first + 参数驱动）

## 核心目标

- Core 保持稳定：`search/orchestrator.py`、`extract/pipeline.py`、`github_explorer/orchestrator.py`
- 策略外置：将模型选择、source mix、预算约束放入请求级 Policy
- 可解释：每次请求输出 `DecisionTrace`

## Core 契约（已落地）

- `SearchRequest`
  - `mode/intent/freshness/sources/model/model_profile/risk_level/budget`
- `ExtractRequest`
  - `strategy/force_mineru/max_chars`
- `SearchResponse`
  - 新增 `decision_trace`
- `ExtractionResponse`
  - 新增 `decision_trace`
- `DecisionTrace`
  - `request_id/policy_version/events[]`

代码位置：

- `src/codex_search_stack/contracts.py`
- `src/codex_search_stack/policy/context.py`
- `src/codex_search_stack/policy/router.py`
- `src/codex_search_stack/policy/extract_router.py`

## YAML 策略模板

```yaml
policy:
  models:
    grok:
      default: "grok-4.1"
      profiles:
        cheap: "grok-4.1-fast"
        balanced: "grok-4.1"
        strong: "grok-4.1-thinking"
  routing:
    by_mode:
      fast: ["exa", "grok"]
      deep: ["exa", "tavily", "grok"]
      answer: ["tavily"]

observability:
  decision_trace:
    enabled: true
```

## CLI 参数映射

- `--sources` -> `SearchRequest.sources`
- `--model` -> `SearchRequest.model`
- `--model-profile` -> `SearchRequest.model_profile`
- `--risk-level` -> `SearchRequest.risk_level`
- `--budget-max-calls` -> `SearchRequest.budget.max_calls`
- `--budget-max-tokens` -> `SearchRequest.budget.max_tokens`
- `--budget-max-latency-ms` -> `SearchRequest.budget.max_latency_ms`
- `extract --strategy` -> `ExtractRequest.strategy`

说明：`budget.max_latency_ms` 当前用于“按 source 数量分摊 timeout”，并传入 Exa/Tavily/Grok 请求超时参数。

## 已落地补充

1. `DecisionTrace` JSONL 落盘与聚合统计（失败率、延迟、命中源）
   - 落盘：`src/codex_search_stack/observability/decision_trace_store.py`
   - 聚合：`scripts/decision_trace_stats.py` 或 `codex-search trace-stats`
2. MCP 端到端回归（工具注册 + 请求示例 + 失败注入）
   - 测试：`tests/test_mcp_server.py`
