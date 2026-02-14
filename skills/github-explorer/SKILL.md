---
name: github-explorer
description: >
  GitHub 项目深度分析 Skill。用于“帮我看看这个仓库/这个项目怎么样/值不值得用”类请求。
  采用证据优先流程：仓库定位 -> GitHub API 主证据 -> 外部信号补证 -> 结构化结论，避免只读 README。
---

# GitHub Explorer（Codex 版）

> 核心原则：README 只算入口，结论必须落在 Issues / Commits / 外部可追溯链接。

## Workflow

```text
[项目名/URL]
  -> [1. 定位仓库]
  -> [2. 采集证据（主证据 + 外部补证）]
  -> [3. 研判打分]
  -> [4. 结构化输出 + 自检]
```

## Phase 1：定位仓库（必须）

1. 优先输入 `owner/repo` 或完整 GitHub URL。
2. 若只有项目名：先用 `search-layer` 找候选，再确认主仓。
3. 同名冲突必须写入 `notes`，禁止拍脑袋选仓库。

仓库定位命令（候选检索）：

```bash
uv run python "skills/search-layer/scripts/search.py" \
  "site:github.com <project_name>" --mode deep --intent resource --num 5
```

## Phase 2：采集证据（并行）

### 2.1 主证据（必须）

必须走本仓 `github-explorer` 脚本（内部已使用 GitHub API，不依赖 repo 页面抓取）：

```bash
uv run python "skills/github-explorer/scripts/explore.py" "owner/repo" --format markdown
```

深度尽调建议：

```bash
uv run python "skills/github-explorer/scripts/explore.py" "owner/repo" \
  --issues 8 --commits 8 --external-num 10 --extract-top 3 \
  --confidence-profile deep --format markdown
```

产物落盘（默认开启）：

- 每次执行会在 `".runtime/github-explorer/<repo>_<time>/"` 输出：
  - `report.md`
  - `report.json`
  - `book/README.md`
  - `book/papers/*.pdf`（若命中 arXiv 且下载成功）
- 可用 `--out-dir` 指定目录，`--no-book-download` 仅生成索引不下载 PDF。

### 2.2 外部补证（按需）

默认会优先注入 DeepWiki（若存在 `https://deepwiki.com/{owner}/{repo}`），并并行检查 `arXiv`、`zread` 收录状态；DeepWiki 不可用时自动降级，不中断主流程。

当需要社区观点/实测反馈/竞品讨论时（知乎/公众号/V2EX/Twitter + alternatives）：

```bash
uv run python "skills/search-layer/scripts/search.py" \
  --queries "<owner/repo> review" "<owner/repo> 使用体验" "<owner/repo> alternatives" \
  --mode deep --intent exploratory --num 5
```

### 2.3 反爬站点降级（强制）

遇到知乎/微信/小红书或 `web` 抽取不完整时：

```bash
uv run python "skills/content-extract/scripts/content_extract.py" --url "<url>"
```

必要时强制 MinerU：

```bash
uv run python "skills/content-extract/scripts/content_extract.py" --url "<url>" --force-mineru
```

## Phase 3：研判规则（必须回答）

至少回答以下 4 点：

1. 项目阶段：快速迭代 / 稳定活跃 / 维护模式 / 低活跃
2. 真实风险：精选 Issues 暴露了什么（稳定性、性能、兼容性、维护成本）
   - 必须明确 maintainer 是否参与评论（`OWNER/MEMBER/COLLABORATOR`）
3. 适用边界：适合什么团队/场景，不适合什么场景
4. 采用建议：直接采用 / PoC 后采用 / 暂缓

### 精选 Issue 评分（建议）

每条 Issue 可按 0-10 粗评分：

- 讨论热度（0-3）
- 维护者参与（0-3）
- 风险价值（0-2）
- 可执行性（0-2）

优先展示高分 + 最近 90 天有进展的问题。

## Phase 4：输出合同（强制）

输出必须满足：

- 顶部可点击仓库标题：`# [owner/repo](URL)`
- 包含：一句话定位 / 健康度 / 精选 Issue / 最近提交 / 外部信号 / 结论建议
- 每条外部观点必须有 URL；时间敏感信息带日期
- 信息缺失写“未找到”，禁止编造

模板参考：`references/report-template.md`

## 快速参数矩阵

| 目标 | 推荐参数 |
|---|---|
| 快速扫仓 | `--issues 5 --commits 5 --external-num 5 --no-extract` |
| 深度尽调 | `--issues 8 --commits 8 --external-num 10 --extract-top 3` |
| 低成本巡检 | `--confidence-profile quick --no-extract` |
| 证据优先 | `--confidence-profile deep --extract-top 3` |

## 失败与降级

- 仓库无法解析：要求用户提供明确 `owner/repo`
- 外部信号不足：保留 GitHub 主证据并在 `notes` 标注
- 外链抓取失败：切换 `content-extract` / `--force-mineru`

## 输出前自检清单（强制）

- [ ] 仓库链接可点击且正确
- [ ] 至少 3 条最近提交
- [ ] 至少 1 条精选 Issue（若无则写明）
- [ ] 外部信号有可追溯 URL（若无则写明）
- [ ] 结论包含“适用场景 + 风险 + 建议动作”

## 依赖关系

- `skills/search-layer`：外部检索与补证
- `skills/content-extract`：正文提取
- `skills/mineru-extract`：反爬兜底
- `src/codex_search_stack/github_explorer/`：主编排与报告渲染
