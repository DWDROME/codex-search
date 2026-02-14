# codex-search 调用章法（统一版）

## 目标

把 `codex-search` 从“参数拼装系统”收敛为“4 个对外能力 + 最少必要参数”。

---

## 一、能力边界（固定）

对外只承诺：

1. `search-layer`（多源搜索）
2. `content-extract`（URL 提取）
3. `mineru-extract`（复杂文档提取）
4. `github-explorer`（仓库调研）

`research/policy/trace/ci` 都是内部支撑，不额外作为对外能力名。

---

## 二、三层分工（必须遵守）

1. **协议层（Skill 文档）**：定义调用顺序与停止条件，不做业务实现。
2. **策略层（Policy）**：定义 `intent -> mode -> sources -> model` 路由，不在 CLI/MCP 重复。
3. **执行层（Orchestrator）**：只负责执行、重试、去重、返回合同结果。

---

## 三、默认入口（对外）

- 搜索：`codex-search search "<query>" --mode deep --intent exploratory`
- 提取：`codex-search extract "<url>" --strategy auto`
- 仓库调研：`codex-search explore "<owner/repo>"`

> `research` 是 search-layer 的内部高级模式，不作为独立能力默认入口。

---

## 四、故障前置检查（推荐）

出现“API 不可用 / key 失效 / 全链路突然失败”时，先执行：

1. `uv run python "skills/api-availability/scripts/api_availability.py" --json`
2. 若需要严格门禁：`uv run python "skills/api-availability/scripts/api_availability.py" --strict --json`
3. 再继续 `search/extract/explore` 或 MCP `get_config_info`

---

## 五、search-layer 内部高级协议（codex_research_v1）

固定四轮，不建议手工扩轮：

1. `official_baseline`
2. `ecosystem_coverage`
3. `risk_and_alternatives`
4. `verification_and_recency`

输出包含：`rounds[]`、`notes[]`、可选 `decision_trace`。

---

## 六、source 治理

- 权限/私有/反爬页面不做无穷重试。
- 命中不可访问时统一标注：`source_unavailable:*`
- Linux.do 私有/成员可见帖：`source_unavailable:linux_do_private_or_auth_required` 并跳过。

---

## 七、反模式（禁止）

- 在 Skill、CLI、MCP 三处分别定义不同策略。
- 同一任务临场切换多套参数模板且不落盘。
- 对权限站点重复抓取却不标注 `source_unavailable`。
