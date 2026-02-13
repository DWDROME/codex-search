---
name: github-explorer
description: >
  GitHub 项目深度分析 Skill。用于“帮我看看这个仓库/这个项目怎么样/值不值得用”类请求。
  按固定流程完成仓库定位、多源证据采集、结构化研判与可追溯输出。
---

# github-explorer（Codex 版）

> 原则：不只看 README；重点看 Issues、Commits、外部讨论与可验证证据。

## 触发时机

出现以下意图时，优先使用本 Skill：

- “分析一下这个 GitHub 项目”
- “这个仓库靠谱吗/值不值得用”
- “帮我做竞品对比/项目尽调”
- “给我一个结构化项目评估报告”

## 标准流程（必须按序执行）

### Phase 1：定位仓库

1. 优先识别 `owner/repo` 或 GitHub URL。
2. 若只有项目名：
   - 先用 `search-layer` 定位候选仓库，再确认主仓。
3. 记录候选冲突（同名仓库）并在 `notes` 标注。

### Phase 2：采集证据（并行）

1. 主证据（必选）：
   - Repo 元数据、Issues、Commits（由内核 `explore` 完成）
2. 外部证据（按需）：
   - 技术评测/新闻/社区讨论：调用 `search-layer`
3. 反爬页面（知乎/微信/小红书等）：
   - 调 `content-extract`，必要时自动降级 `mineru-extract`

推荐命令：

```bash
uv run python "skills/github-explorer/scripts/explore.py" "owner/repo" --format markdown
```

深度尽调：

```bash
uv run python "skills/github-explorer/scripts/explore.py" "owner/repo" \
  --issues 8 --commits 8 --external-num 10 --extract-top 3 \
  --confidence-profile deep --format markdown
```

外部补证（示例）：

```bash
uv run python "skills/search-layer/scripts/search.py" \
  --queries "<project> review" "<project> discussion" \
  --mode deep --intent exploratory --num 5
```

### Phase 3：研判

至少回答以下问题：

1. 项目处于哪个阶段（快速成长/成熟稳定/维护模式）？
2. Top Issues 暴露了什么真实风险？
3. 与主流替代方案差异在哪？
4. 哪些场景适合用，哪些不适合？

### Phase 4：结构化输出

- 默认按 `references/report-template.md` 输出。
- 每个结论都要有来源链接或仓库证据。
- 找不到信息时明确写“未找到”，不得编造。

## 精选 Issue 评分标准（强制）

从候选 Issues 中选 Top 3-5，按以下规则打分并优先展示：

- `讨论热度`（0-3）：评论数、参与者多样性
- `维护者参与`（0-3）：是否有 maintainer/core contributor 明确回应
- `风险价值`（0-2）：是否涉及架构缺陷、稳定性、数据安全、性能瓶颈
- `可执行性`（0-2）：是否有复现、修复方案、里程碑或关闭结论

总分 `0-10`，优先展示总分高者；同分时优先近期（最近 90 天）且已形成结论的问题。

每条 Issue 输出格式必须是：

- `[#编号 标题](URL) — 争议点 / 维护者结论 / 当前状态`

## 社区声量引用格式（强制）

社区信息必须“可追溯 + 有观点”，统一格式：

- `[平台: 标题](URL)（YYYY-MM-DD）— 具体观点/实测结论`

约束：

- 不允许只有“热度高/评价不错”这类空话
- 至少给出 2 条外部引用；不足时写“未找到更多可验证讨论”
- 优先引用一手讨论（作者帖、Issue、论坛原帖），避免二手搬运

## 输出质量红线（强制）

- 必须有可点击仓库标题链接：`# [name](url)`
- 必须包含精选 Issue（有链接）
- 竞品必须附链接
- 外部观点必须附来源 URL 与日期
- 禁止空话（如“热度很高”）但无证据

## 降级策略

- 外部搜索源失败：保留 GitHub 主证据并在 `notes` 记录失败源。
- 反爬内容抓取失败：切换 `content-extract` / `mineru-extract`。
- 目标无法解析：要求用户提供明确 `owner/repo`。

## 依赖关系

- `search-layer`：多源搜索与排序
- `content-extract`：网页正文提取
- `mineru-extract`：反爬/复杂页面兜底

> 注意：本 Skill 为编排协议层；底层能力由 `src/codex_search_stack/github_explorer/` 与相关组件提供。
