# Search 组件说明

## 组件定位

`search` 是多源检索编排层，负责把 Exa / Tavily / Grok 的结果统一聚合、去重和排序。

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
- `--domain-boost`: 域名加权，逗号分隔
- `--sources`: `auto` 或 `exa,tavily,grok`（请求级 source mix）
- `--model`: 请求级模型覆盖（优先于 profile）
- `--model-profile`: `cheap | balanced | strong`
- `--risk-level`: `low | medium | high`
- `--budget-max-calls / --budget-max-tokens / --budget-max-latency-ms`: 请求预算约束

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

1. 先构建 `SearchRequest`，再由 Policy 计算 `SearchPlan`（模型 + source mix + 并发）。
2. 依据 `mode` 和 `sources` 选择源：
   - `fast`：优先 Exa，其次 Grok
   - `deep`：并行 Exa + Tavily + Grok（按可用性）
   - `answer`：以 Tavily answer 能力为主
3. Grok 为必选源：即使请求未显式包含，也会强制纳入路由；若失败按 `policy.search.grok.retry_attempts` 重试（默认 3 次总尝试）。
4. Grok/Tavily 按 key pool 候选依次重试。
5. URL 归一化去重；若配置了 `intent`，做意图感知评分后排序。
6. 当设置 `budget-max-latency-ms` 时，会按启用 source 数量分摊为每源 timeout。
7. 输出统一 JSON（`SearchResponse`），可选包含 `decision_trace`。

默认情况下使用 `model_profile=strong`，可在请求级改为 `cheap/balanced` 以换取更低延迟。

---

## 常见问题

- 没有结果：先确认至少有一个搜索源 key 可用，或 `search.key_pool.file` 存在且可读。
- 结果质量一般：优先补 `--intent`，并加 `--domain-boost`。
- 某源频繁失败：看返回 `notes`（如 `*_failed` / `*_pool_rotated`）定位具体源与 key。

---

## 进阶：Research 闭环

当你需要“先搜一轮 -> 自动发现缺口 -> 继续追问补证”时，建议改用：

```bash
codex-search research "你的问题" --mode deep --intent exploratory --max-rounds 3
```

对应 skills 入口：

```bash
uv run python "skills/search-layer/scripts/research.py" "你的问题" --max-rounds 3
```
