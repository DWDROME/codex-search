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

---

## 配置项（YAML）

默认读取 `config/config.yaml`（可用 `CODEX_SEARCH_CONFIG` 覆盖路径）：

- `explore.github_token`（推荐，有助于提高 API 配额）
- `runtime.confidence_profile`（默认 profile）
- 其余依赖透传到 search/extract（如 Grok/Tavily/MinerU）

---

## 运行逻辑（简版）

1. 解析目标仓库（URL 或 `owner/repo`，失败则走搜索解析）。
2. 拉取 GitHub 元信息、精选 issue、最近 commits。
3. 搜索外部信号；可选对 Top N 外链做提取。
4. 计算 confidence：
   - `deep`：偏元数据/活跃度/可验证性
   - `quick`：偏外部覆盖/稳定性
5. 输出报告并附执行注记 `notes`。

---

## 输出重点字段

- `repo`：基础元信息
- `issues` / `commits` / `external`
- `confidence.score` / `confidence.level` / `confidence.profile`
- `confidence.factors[]`（含 weighted + raw 分）

---

## 常见问题

- 仓库解析失败：优先传完整 `owner/repo` 或 GitHub URL。
- 结果来源偏少：增大 `--external-num`，并检查搜索源 key 可用性。
- 置信度偏低：查看 `notes` 里的失败项（`*_failed`）并补齐对应凭据。
