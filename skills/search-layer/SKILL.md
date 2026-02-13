---
name: search-layer
description: >
  Codex 多源搜索编排协议。用于深度调研、多来源交叉验证、时效性查询与对比分析。
  由 Agent 在调用前进行意图判定与参数选择，底层执行由本仓库 search 内核完成（Exa + Tavily + Grok）。
---

# search-layer（Codex 版）

## 触发时机

当用户需求满足任一条件时优先使用：

- 需要“多源搜索 / 交叉验证 / 深度调研”
- 需要“最新动态 / 本周新闻 / 近期进展”
- 需要“对比分析 / 教程聚合 / 官方资源定位”

## 执行流程（协议层）

```
用户查询
  ↓
[Phase 1] 意图判定（Agent）
  ↓
[Phase 2] 查询拆分/扩展（可选）
  ↓
[Phase 3] 调用 scripts/search.py（多源并行）
  ↓
[Phase 4] 去重、评分、结构化输出
```

> 说明：意图判定与查询拆分由 Agent 协议执行；`search.py` 负责检索、合并、排序与返回标准 JSON。

## Phase 1：意图判定

参考 `references/intent-guide.md`，从以下 7 类中选择：

- `factual` / `status` / `comparison` / `tutorial` / `exploratory` / `news` / `resource`

推荐映射：

- 不确定时默认 `exploratory`
- 包含“最新/最近/本周”优先 `status` 或 `news`
- 包含“vs/对比/区别”优先 `comparison`

## Phase 2：查询拆分（可选）

对比类与探索类建议拆成 2-3 个子查询并行：

```bash
python3 "skills/search-layer/scripts/search.py" \
  --queries "A vs B" "A 优势" "B 优势" \
  --mode deep --intent comparison --num 5
```

## Phase 3：执行命令模板

单查询：

```bash
python3 "skills/search-layer/scripts/search.py" "<query>" \
  --mode deep --intent exploratory --num 5
```

时效查询：

```bash
python3 "skills/search-layer/scripts/search.py" "<query>" \
  --mode deep --intent status --freshness pw --num 5
```

## 参数速查

- `--mode`: `fast | deep | answer`
- `--intent`: 7 类意图（不传则不做意图评分）
- `--freshness`: `pd | pw | pm | py`
- `--queries`: 多子查询并行
- `--domain-boost`: 域名加权（逗号分隔）
- `--num`: 每次返回条数

## 降级与容错

- 某一搜索源失败时继续使用其余源，不阻塞主流程。
- 无有效结果时，输出 `notes` 并建议调整：
  - 放宽 freshness
  - 改用 `deep`
  - 补充 `intent` / `domain-boost`

## 输出约定（必须）

- 输出必须带 URL 来源。
- 若多源结果冲突，必须显式标注冲突点与来源。
- 结论必须可追溯到结果条目，不得编造。

## 自检清单（输出前）

- 是否至少使用 2 个来源（若可用）？
- 是否为时效问题设置了 `--freshness`？
- 是否给出了来源 URL 与冲突说明？
