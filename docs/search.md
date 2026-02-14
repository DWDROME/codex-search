# Search 组件说明

## 组件定位

`search` 是多源检索编排层，负责把 Exa / Tavily / Grok 的结果统一聚合、去重和排序。

统一调用章法见：`docs/call-protocol.md`

主入口：

- 代码：`src/codex_search_stack/search/orchestrator.py`
- CLI：`codex-search search ...`

---

## CLI 用法

```bash
codex-search search "RAG framework comparison" --mode deep --intent exploratory --num 5
```

参数：

- `--mode`: `fast | deep | answer`
- `--intent`: `factual | status | comparison | tutorial | exploratory | news | resource`
- `--freshness`: `pd | pw | pm | py`
- `--num`: 返回条数

> 其余高级参数（sources/model/budget 等）已内收为内部调试项，默认调用不建议显式传入。

---

## 配置项（YAML）

默认读取 `config/config.yaml`（可用 `CODEX_SEARCH_CONFIG` 覆盖路径）：

- `search.exa.api_key`
- `search.tavily.api_url` / `search.tavily.api_key`
- `search.grok.api_url` / `search.grok.api_key` / `search.grok.model`
- `search.key_pool.file` / `search.key_pool.enabled`（Grok/Tavily 候选重试）
- `runtime.search_timeout_seconds`
- `policy.models.grok.default/profiles`（模型档位路由）
- `policy.routing.by_mode`（mode 默认 source mix）
- `policy.search.grok.retry_attempts`（Grok 每个候选 key 的总尝试次数，默认 3）
- `observability.decision_trace.enabled`（是否输出决策轨迹）

---

## 运行逻辑（简版）

1. 读取查询与最小参数（`mode/intent/freshness/num`）。
2. 按策略层自动选择可用搜索源并执行（Exa/Tavily/Grok）。
3. 失败源自动降级与重试，不阻断整体结果返回。
4. 对结果做去重、评分、排序，输出统一 JSON。
5. 如启用可观测，会附带 `decision_trace` 供回放。

---

## 常见问题

- 没有结果：先确认至少有一个搜索源 key 可用，或 `search.key_pool.file` 存在且可读。
- 结果质量一般：优先补 `--intent`，必要时改写查询词并增加上下文关键词。
- 某源频繁失败：看返回 `notes`（如 `*_failed` / `*_pool_rotated`）定位具体源与 key。

---

## 进阶：search-layer 内部多轮补证

当单轮搜索证据不足时，可启用 search-layer 的内部高级模式：

```bash
uv run python "skills/search-layer/scripts/research.py" "你的问题" \
  --protocol codex_research_v1 --extract-per-round 2
```

说明：该模式属于 search-layer 的内部能力扩展，不作为独立对外能力名称。
