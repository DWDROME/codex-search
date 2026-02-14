# Explore 组件说明

## 组件定位

`explore` 用于 GitHub 项目研判，输出结构化报告（JSON/Markdown）。

主入口：

- 代码：`src/codex_search_stack/github_explorer/orchestrator.py`
- 报告渲染：`src/codex_search_stack/github_explorer/report.py`
- CLI：`codex-search explore ...`

---

## CLI 用法

```bash
codex-search explore "microsoft/graphrag" --format markdown
```

快扫 profile：

```bash
codex-search explore "microsoft/graphrag" --confidence-profile quick --format json
```

参数：

- `--issues` / `--commits` / `--external-num`
- `--extract-top` / `--no-extract`
- `--confidence-profile`: `deep | quick`
- `--format`: `markdown | json`
- `--out-dir`：指定产物目录
- `--book-max`：Book 论文上限
- `--no-book-download`：只生成索引，不下载 PDF
- `--no-artifacts`：不落盘产物
- `--hard-fail-contract` / `--no-hard-fail-contract`：控制深度调查合同是否硬失败（默认硬失败）

---

## 配置项（YAML）

默认读取 `config/config.yaml`（可用 `CODEX_SEARCH_CONFIG` 覆盖路径）：

- `explore.github_token`（推荐，有助于提高 API 配额）
- `runtime.confidence_profile`（默认 profile）
- `policy.explore.external.model_profile`（外部检索模型档位，默认 `strong`）
- `policy.explore.external.primary_sources`（首轮检索源，默认 `["grok","exa"]`）
- `policy.explore.external.fallback_source`（首轮无结果后的回退源，默认 `tavily`）
- `policy.explore.external.followup_rounds`（自动补证轮数，默认 `2`）
- 其余依赖透传到 search/extract（如 Grok/Tavily/MinerU）

---

## 运行逻辑（简版）

1. 解析目标仓库（URL 或 `owner/repo`，失败则走搜索解析）。
2. 拉取 GitHub 元信息（含 README 摘要）、精选 issue、最近 commits。
3. 对 issue 做质量刻画（评论热度 + maintainer 参与 + 风险标签）。
4. 搜索外部信号（社区域名 + arXiv + zread + alternatives）；若 DeepWiki/zread 直连可用会优先注入。
5. 可选对 Top N 外链做提取。
6. 若关键覆盖缺失（如 arXiv/zread），会自动生成 follow-up query，按 `followup_rounds` 做多轮补证。
7. 计算 confidence：
   - `deep`：偏元数据/活跃度/可验证性
   - `quick`：偏外部覆盖/稳定性
8. 输出报告并附执行注记 `notes`。

---

## 输出重点字段

- `repo`：基础元信息（含 `readme_excerpt`）
- `issues`：含 `maintainer_participated` / `risk_tags` / `quality_score`
- `commits` / `external`
- `comparisons`：竞品候选（含证据标题）
- `index_coverage`：DeepWiki/arXiv/zread 收录状态
- `book`：论文/DeepWiki/zread 资料包索引
- `artifacts`：落盘目录与下载统计（`report.md/json` + `book/`）
- `confidence.score` / `confidence.level` / `confidence.profile`
- `confidence.factors[]`（含 weighted + raw 分）

---

## 深度调查合同（默认硬失败）

当输出 `markdown` 时，默认检查以下配额，不满足即返回非 0：

- 社区声量：`>= 6`
- 竞品对比：`>= 4`
- 反对证据：`>= 2`

退出码约定：

- `0`：成功且合同满足
- `1`：运行失败（如仓库解析失败）
- `2`：合同不满足（仅当 `--no-hard-fail-contract`）
- `3`：合同不满足（默认硬失败）

> Linux.do 等权限帖若不可访问，会标注 `source_unavailable:*` 并跳过，不做无限重试。

---

## 论文下载说明

- `book.papers` 会收集 `arXiv` 以及直接 PDF 链接（不仅限 arXiv）。
- 默认会下载到 `book/papers/`；可用 `--no-book-download` 关闭下载，仅保留索引。

---

## 常见问题

- 仓库解析失败：优先传完整 `owner/repo` 或 GitHub URL。
- 结果来源偏少：增大 `--external-num`，并检查搜索源 key 可用性。
- 置信度偏低：查看 `notes` 里的失败项（`*_failed`）并补齐对应凭据。
