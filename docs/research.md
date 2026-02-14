# Research 组件说明

## 组件定位

`research` 是在 `search + extract` 之上的多轮闭环：

- Round N：搜索
- Round N：抽取（可选）
- Round N：缺口评估（critique）
- Round N+1：自动 follow-up 查询

主入口：

- 代码：`src/codex_search_stack/research/orchestrator.py`
- CLI：`codex-search research ...`
- Skill：`skills/search-layer/scripts/research.py`
- MCP：`research` tool

---

## CLI 用法

```bash
codex-search research "FAST-LIVO2 架构风险与论文证据" \
  --mode deep --intent exploratory --max-rounds 3 --extract-per-round 2
```

---

## 输出结构

- `rounds[]`：每轮 query、新增结果数、缺口标签、follow-up query
- `results[]`：最终结果（含 `first_seen_round` / `seen_count` / 可选 `extract`）
- `stop_reason`：`no_more_gap | max_rounds_reached`
- `notes[]`：每轮执行注记
- `decision_trace`：完整可回放轨迹（若启用）

---

## 关键配置

- `runtime.search_timeout_seconds`：影响每轮预算
- `policy.models.grok.profiles`：控制 `model_profile` 映射
- `observability.decision_trace.*`：控制轨迹输出与落盘

