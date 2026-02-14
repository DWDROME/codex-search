---
name: search-layer
description: >
  Multi-source search and deduplication layer with intent-aware routing for codex-search.
  Integrates Exa, Tavily, and Grok; supports fast/deep/answer modes plus an internal
  research loop. Use for deep search, multi-source verification, and high-confidence evidence synthesis.
---

# search-layer — 多源检索与研究闭环入口

目标：把“快查 / 深搜 / 多轮补证”统一到一个可追溯入口，避免调用混乱。

---

## 触发与路由

满足任一条件就优先使用本 skill：

- 需要多源交叉验证（而不是单一结论）
- 需要时效信息（最新进展、近期变化、状态跟踪）
- 需要深度研究（包含证据缺口补齐、风险与替代方案）

路由规则（默认）：

- **fast**：快速答疑、概念澄清、作业中“先搞懂再深入”
- **deep**：常规深搜、多源核验、需要结构化证据
- **research**：多轮闭环（search -> extract -> critique -> follow-up）

---

## 执行流程（Decision Tree）

输入：`query`

1. **先判定意图**（`factual/status/comparison/tutorial/exploratory/news/resource`）
2. **再选模式**（`fast/deep/answer/research`）
3. **执行检索**（Exa + Tavily + Grok，按策略并行/降级）
4. **去重与加权**（URL 归一化 + 意图评分 + 域名权威度）
5. **输出结果合同**（带来源、notes、冲突标记）

> 参考意图规则：`references/intent-guide.md`

---

## 命令模板（最小可用）

快速查询：

```bash
uv run python "skills/search-layer/scripts/search.py" "<query>" \
  --mode fast --intent factual --num 5
```

深度检索：

```bash
uv run python "skills/search-layer/scripts/search.py" "<query>" \
  --mode deep --intent exploratory --num 6
```

时效问题：

```bash
uv run python "skills/search-layer/scripts/search.py" "<query>" \
  --mode deep --intent status --freshness pw --num 6
```

多轮研究闭环：

```bash
uv run python "skills/search-layer/scripts/research.py" "<query>" \
  --protocol codex_research_v1 --extract-per-round 2
```

---

## research 约定（内部高级模式）

- `research` 是 `search-layer` 的内部模式，不单独对外暴露为新能力名。
- `codex_research_v1`：固定四轮（稳定、可复现、减少“临场调参”）。
- `legacy`：按 `max_rounds` 动态多轮（MCP `research.max_rounds` 允许 `1..8`）。
- 默认优先 `codex_research_v1`；仅在确有必要时切到 `legacy`。

---

## 失败恢复与降级（强制）

- 任一来源失败，不得阻塞整轮：继续其余来源并在 `notes` 标注失败原因。
- Grok 失败必须重试：**首次 + 额外两次重试**；仍失败再降级（与实现一致）。
- Linux.do 等锁帖/权限页：标记 `source_unavailable:*` 并跳过，不做无限重试。
- 无结果时必须返回下一步建议（如：放宽 `freshness`、切 `deep`、补 `intent`、增加 `domain-boost`）。

---

## Result Contract（输出合同）

`search.py` / `research.py` 输出需满足：

- `results[]`：每条含 `title/url/snippet/source`（可含评分字段）
- `notes[]`：失败、降级、重试、策略决策等可审计信息
- `sources`：可追溯来源集合（最终回答必须引用）
- `answer`（可选）：answer 模式或 Tavily 回答摘要

要求：

- 结论必须可追溯到 `results` 或抽取证据
- 冲突信息必须显式标注“冲突点 + 来源”
- 禁止无来源断言

---

## 本 skill 不做什么

- 不绕过登录、验证码、会员权限
- 不将私有/受限页面当作“可验证公开证据”
- 不在 skill 文档里复制底层实现细节（实现以 `src/codex_search_stack` 为准）
