# 组件清单（统一版）

## 一、对外只承诺 4 个能力（Skills）

`codex-search` 对外产品面统一为以下四项：

| 对外能力 | Skill | 主职责 |
|---|---|---|
| 多源搜索 | `search-layer` | Exa + Tavily + Grok 搜索、去重、排序、交叉验证 |
| 网页提取 | `content-extract` | URL -> Markdown，普通页优先 Tavily，失败/高阻降级 MinerU |
| 复杂文档提取 | `mineru-extract` | PDF/Office/图片/复杂 HTML 解析为高保真 Markdown |
| GitHub 项目调研 | `github-explorer` | Repo/Issues/Commits/外部信号聚合，输出结构化报告 |

> 这四项是“对用户讲能力”时的唯一口径。

---

## 二、内部支撑组件（不作为独立对外能力）

| 内部组件 | 代码位置 | 说明 |
|---|---|---|
| Search Core | `src/codex_search_stack/search/` | search-layer 的执行内核 |
| Extract Core | `src/codex_search_stack/extract/` | content-extract/mineru-extract 的统一管线 |
| Explore Core | `src/codex_search_stack/github_explorer/` | github-explorer 的执行与报告内核 |
| Research Loop | `src/codex_search_stack/research/` | search-layer 的“多轮补证模式”，属于内部高级流程 |
| API Availability | `skills/api-availability/scripts/api_availability.py` | API 可用性体检（配置检查 + 实时探测 + strict 失败） |
| Policy Router | `src/codex_search_stack/policy/` | 路由、模型、预算、降级策略 |
| Decision Trace | `src/codex_search_stack/observability.py` | 决策轨迹与回放（审计/调试） |
| CLI / MCP | `src/codex_search_stack/cli.py` `src/codex_search_stack/mcp_server.py` | 运行入口，不增加能力种类 |

---

## 三、为什么看起来“很多”

原因不是能力多，而是把“能力 + 平台化支撑”放在了同一仓库：

- 能力层：只有 4 个（上表）
- 平台层：配置、可观测、协议校验、CI、兼容入口

统一后原则：

1. 对外描述只讲四大能力。
2. Research/API 体检/Policy/Trace/CI 只作为内部支撑描述。
3. 新功能若不能映射到四大能力之一，默认不新增对外能力名。

---

## 四、建议阅读顺序

1. `README.md`（统一能力口径）
2. `skills/README.md`（四个 Skill 的实际入口）
3. `docs/call-protocol.md`（统一调用章法）
4. 组件说明：`docs/search.md` / `docs/extract.md` / `docs/explore.md`
