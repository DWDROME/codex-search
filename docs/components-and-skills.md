# 组件清单（主组件 + 附属 Skill）

本文用于回答两个问题：

1. 我们现在有哪些可运行组件？
2. 这些组件分别对应上游哪些 Skill/能力？

---

## 一、主组件（当前仓库内）

| 组件 | 代码位置 | 职责 | CLI 入口 |
|---|---|---|---|
| Search Orchestrator | `src/codex_search_stack/search/` | 多源搜索编排、去重、意图评分、号池重试 | `codex-search search` |
| Extract Pipeline | `src/codex_search_stack/extract/` | URL 提取，优先 Tavily，失败降级 MinerU | `codex-search extract` |
| GitHub Explorer | `src/codex_search_stack/github_explorer/` | Repo/Issues/Commits/外部信号采集 + 置信度报告 | `codex-search explore` |
| Smoke & CI Hook | `scripts/` + `.github/workflows/` | 本地回归、CI 自动化、脱敏环境快照 | `./scripts/smoke_phase6.sh` / `./scripts/ci_smoke_hook.sh` |

---

## 二、附属工程能力（本仓库内）

| 能力 | 位置 | 用途 |
|---|---|---|
| Key Pool（Grok/Tavily） | `src/codex_search_stack/key_pool.py` | 多 key 候选顺序重试，降低 429/单 key 失效风险 |
| Confidence Profile | `src/codex_search_stack/github_explorer/orchestrator.py` | `deep/quick` 两套评分权重 |
| Masked Env Snapshot | `scripts/masked_env_snapshot.py` | CI 侧输出可审计但不泄露明文密钥的环境快照 |

---

## 三、上游 Skill 对应关系（迁移映射）

| 上游 Skill / 模块 | 本仓库对应 |
|---|---|
| `search-layer` | `src/codex_search_stack/search/{sources,scoring,orchestrator}.py` |
| `content-extract` | `src/codex_search_stack/extract/pipeline.py` |
| `mineru-extract` | `src/codex_search_stack/extract/mineru_adapter.py` |
| `github-explorer` | `src/codex_search_stack/github_explorer/{orchestrator,report}.py` |

证据见：`docs/migration-map.md`

---

## 四、外部依赖能力（非本仓库代码）

| 类别 | 典型项 | 说明 |
|---|---|---|
| 搜索 API | Exa / Tavily / Grok | 由 `config/config.yaml` 提供，运行时按可用性自动降级 |
| 提取后端 | Tavily Extract / MinerU API | Extract Pipeline 统一编排 |
| CI 环境 | GitHub Actions | 使用 `.github/workflows/ci-smoke.yml` |

---

## 五、建议阅读顺序

1. `README.md`（总体能力与命令）
2. `docs/migration-map.md`（上游映射）
3. 组件子 README：
   - `docs/search.md`
   - `docs/extract.md`
   - `docs/explore.md`
   - `docs/internal/ci-smoke.md`
4. `docs/internal/phase*.md`（阶段细节）
5. `docs/internal/testing.md`（测试入口与覆盖说明）
6. `src/codex_search_stack/cli.py`（命令入口）
