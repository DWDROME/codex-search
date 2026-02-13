# Intent Guide（Codex Search）

本指南用于在调用 `search-layer` 前快速判定 `intent/mode/freshness`。

## 七类意图速查

| intent | 典型问题 | mode | freshness | 排序偏向 |
|---|---|---|---|---|
| factual | 什么是 X | answer | - | 权威优先 |
| status | X 最新进展 | deep | pw/pm | 新鲜度优先 |
| comparison | X vs Y | deep | py | 关键词+权威 |
| tutorial | 如何使用 X | answer | py | 权威教程优先 |
| exploratory | 深入了解 X | deep | - | 覆盖面优先 |
| news | X 本周新闻 | deep | pd/pw | 新鲜度最高 |
| resource | X 官方文档/仓库 | fast | - | 精确匹配优先 |

## 判定规则

1. 先看强信号词：
   - `vs/对比/区别` → `comparison`
   - `最新/最近/进展` → `status` 或 `news`
   - `官网/文档/GitHub` → `resource`
2. 多意图冲突时优先级：`resource > news > status > comparison > tutorial > factual > exploratory`
3. 仍不确定时：`exploratory`

## 查询拆分建议

- `comparison`：建议拆 2-3 条子查询并行
- `exploratory`：建议按“概览/生态/实践”拆 2-3 条
- 中文技术词建议附英文变体作为补充查询

## 示例

- “Bun vs Deno 最新对比” → `intent=comparison`, `mode=deep`, `freshness=pw`
- “LangGraph 官方文档” → `intent=resource`, `mode=fast`
- “RAG 最近有什么新闻” → `intent=news`, `mode=deep`, `freshness=pw`
