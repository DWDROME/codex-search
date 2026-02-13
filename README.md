<div align="center">

# codex-search

简体中文

**面向 Codex 的 Skills-first 多源搜索与内容提取能力栈**  
**让搜索更全、提取更稳、结论可追溯**

![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-FastMCP-green.svg)
![Runtime](https://img.shields.io/badge/runtime-Codex-4A90E2)
![Strategy](https://img.shields.io/badge/policy-intent%20%2B%20routing-7B61FF)

</div>

---

## 概述

`codex-search` 是一套专为 Codex 场景设计的搜索与提取能力底座：

- 上层采用 **Skills-first**（推荐）工作流，适合任务编排与复杂检索
- 对外提供 **MCP 标准工具**（可选），适合接入其他 Agent/平台
- 底层统一由 `src/codex_search_stack` 编排，避免“多入口多逻辑”分叉

### 核心价值

- **多源搜索**：Exa + Tavily + Grok 聚合检索，支持并行、降级与来源交叉验证
- **反爬提取**：普通 URL 优先 Tavily，知乎/微信/小红书命中后自动路由 MinerU
- **GitHub 尽调**：仓库元数据 + Issues + Commits + 外部信号，输出结构化报告
- **结果可解释**：支持 `decision_trace`，明确每次路由和回退原因

**工作流程**：`Codex/Agent → Skills 或 MCP → Core Policy → Search/Extract/Explore → 结构化 JSON`  

<details>
<summary><b>💡 为什么选择 codex-search</b></summary>

| 对比项 | 单源搜索/单脚本 | 仅 MCP 直连 | codex-search（Skills + MCP + Core） |
|---|---|---|---|
| 召回覆盖 | 中-低 | 中 | ✅ 高 |
| 反爬可用性 | 低 | 中 | ✅ 高 |
| 失败降级 | 弱 | 中 | ✅ 强 |
| 可解释性 | 弱 | 中 | ✅ 强（decision_trace） |
| 任务编排灵活性 | 中 | 中 | ✅ 高（Skills-first） |

</details>

---

## 功能特性

- ✅ 多源搜索（Exa / Tavily / Grok）
- ✅ 意图感知参数（`intent` / `mode` / `freshness`）
- ✅ 对比类并行检索（`--queries`）
- ✅ 反爬提取自动回退（`auto -> mineru_only`）
- ✅ MCP 协议层参数校验（`invalid_arguments` 统一错误合同）
- ✅ YAML 单入口配置（避免 env 与配置文件双入口混乱）
- ✅ 决策轨迹与统计（`decision_trace` + 聚合脚本）

---

## 安装教程

### Step 0. 前置准备

- Python `3.9+`
- 推荐安装 `uv`（用于 Skills/CLI/MCP 统一启动）
- 已有 Codex 运行环境

### Step 1. 初始化配置

```bash
cp "config/config.example.yaml" "config/config.yaml"
export CODEX_SEARCH_CONFIG="$PWD/config/config.yaml"
```

最小配置示例：

```yaml
search:
  exa:
    api_key: ""
  tavily:
    api_url: "https://api.tavily.com"
    api_key: ""
  grok:
    api_url: "https://api.x.ai/v1"
    api_key: ""
extract:
  mineru:
    token: ""
```

### Step 2. 安装 Skills（推荐主路径）

```bash
bash "scripts/install_skills.sh"
```

默认会链接到：`~/.codex/skills/codex-search/`

### Step 3. （可选）接入 MCP

在 `"~/.codex/config.toml"` 增加：

```toml
[mcp_servers.codex-search]
command = "uvx"
args = ["--python", "3.11", "--from", "/path/to/codex-search[mcp]", "codex-search-mcp"]
cwd = "/path/to/codex-search"

[mcp_servers.codex-search.env]
CODEX_SEARCH_CONFIG = "/path/to/codex-search/config/config.yaml"
```

### Step 4. 验证安装与配置

```bash
uv run python "scripts/check_api_config.py"
bash "scripts/skill_smoke_check.sh"
```

如果你启用了 MCP，也建议检查：

```bash
codex mcp get "codex-search"
```

---

## 提示词模板（建议加入系统提示）

> 下面这段是给 Codex/Claude 一类 coding agent 的“路由提示词”，目标是：优先走本仓 Skills，必要时再走 MCP。

```markdown
# codex-search 路由提示词（Skills-first）

## 1) 激活条件
当用户需求涉及以下任一场景时，激活 codex-search：
- 网络搜索 / 多源交叉验证 / 时效性信息查询
- 网页内容提取 / URL 转 Markdown / 反爬页面处理
- GitHub 项目调研 / 尽调报告 / 竞品分析

## 2) 工具优先级（强制）
1. 优先使用 Skills（编排层）：
   - `skills/search-layer/SKILL.md`
   - `skills/content-extract/SKILL.md`
   - `skills/mineru-extract/SKILL.md`
   - `skills/github-explorer/SKILL.md`
2. 若 Skills 不可用或需要标准化工具接口，再使用 MCP：
   - `search`
   - `extract`
   - `explore`
   - `get_config_info`

## 3) 执行策略
- 搜索任务：先 `search-layer`，按意图选择参数：
  - `intent`: factual/status/comparison/tutorial/exploratory/news/resource
  - `mode`: fast/deep/answer
  - `freshness`: pd/pw/pm/py（时效问题必须带）
- 提取任务：先 `content-extract`（strategy=auto），命中反爬域名自动走 MinerU
- GitHub 任务：用 `github-explorer` 输出结构化结论，必要时补 `search-layer` 外部证据

## 4) 引用与可追溯性（强制）
- 结论必须附来源 URL
- 多源冲突时必须显式标注冲突点
- 时间敏感结论必须标注日期

## 5) 错误恢复
- 先调用 `get_config_info` 检查 readiness 与配置状态
- 无结果：放宽 freshness / 改 intent / 扩展 queries
- 提取失败：切换 `strategy=mineru_only` 或 `--force-mineru`

## 6) 禁止项
- 禁止无来源结论
- 禁止单次失败即放弃
- 禁止未验证假设直接输出为事实
```

<details>
<summary><b>💡 简化版（短提示）</b></summary>

```markdown
优先使用 codex-search 的 Skills（见 skills/README.md 与各子 SKILL.md）：
- 搜索用 search-layer
- 提取用 content-extract（反爬自动回退 mineru-extract）
- GitHub 调研用 github-explorer

只有在 Skills 不可用或需要标准化接口时，才使用 MCP 工具：
search / extract / explore / get_config_info

输出必须附来源 URL；时效信息必须标日期；失败必须重试并说明策略调整。
```

</details>

---

## 快速使用

### 1) 多源搜索（时效问题）

```bash
uv run python "skills/search-layer/scripts/search.py" "OpenAI Codex 最新更新" \
  --mode deep --intent status --freshness pw --num 5
```

### 2) 对比搜索（并行子查询）

```bash
uv run python "skills/search-layer/scripts/search.py" \
  --queries "Bun vs Deno" "Bun 优势" "Deno 优势" \
  --mode deep --intent comparison --num 5
```

### 3) 普通网页提取

```bash
uv run python "skills/content-extract/scripts/content_extract.py" \
  --url "https://platform.openai.com/docs/guides/tools-web-search" --max-chars 3000
```

### 4) 反爬网页提取（知乎示例）

```bash
uv run python "skills/content-extract/scripts/content_extract.py" \
  --url "https://zhuanlan.zhihu.com/p/619438846" --max-chars 3000
```

### 5) GitHub 项目尽调

```bash
uv run python "skills/github-explorer/scripts/explore.py" "openai/codex" \
  --issues 8 --commits 8 --external-num 10 --extract-top 3 --format markdown
```

---

## 详细项目介绍

### 组件说明（Skills）

| Skill | 用途 |
|---|---|
| `search-layer` | 多源搜索、意图判定、并行查询、结果评分 |
| `content-extract` | URL 到 Markdown 的统一入口，自动策略与回退 |
| `mineru-extract` | MinerU API 封装（反爬/复杂文档兜底） |
| `github-explorer` | GitHub 项目结构化解析与尽调 |

### MCP 工具说明

本项目提供四个 MCP 工具：

#### `search` - 多源搜索

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | ✅ | - | 搜索问题 |
| `mode` | string | ❌ | `deep` | `fast/deep/answer` |
| `intent` | string | ❌ | `""` | `factual/status/comparison/tutorial/exploratory/news/resource` |
| `freshness` | string | ❌ | `""` | `pd/pw/pm/py` |
| `num` | int | ❌ | `5` | 返回结果数（协议校验范围 `1..20`） |
| `domain_boost` | string | ❌ | `""` | 域名加权（逗号分隔） |
| `sources` | string | ❌ | `auto` | 指定源组合 |
| `model` / `model_profile` | string | ❌ | `""` / `balanced` | 请求级模型选择 |
| `risk_level` | string | ❌ | `medium` | 风险等级 |
| `budget_*` | int | ❌ | 内置默认 | 调用预算与延迟预算 |

<details>
<summary><b>返回示例</b>（点击展开）</summary>

```json
{
  "ok": true,
  "mode": "deep",
  "intent": "status",
  "count": 5,
  "results": [
    {
      "title": "...",
      "url": "...",
      "source": "tavily,grok",
      "score": 0.81
    }
  ],
  "notes": [],
  "decision_trace": {
    "request_id": "...",
    "policy_version": "policy.v1",
    "events": []
  }
}
```

</details>

#### `extract` - 网页内容提取

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `url` | string | ✅ | - | 目标 URL（仅支持 `http/https`） |
| `force_mineru` | bool | ❌ | `false` | 强制 MinerU |
| `max_chars` | int | ❌ | `20000` | 输出截断（协议校验范围 `500..200000`） |
| `strategy` | string | ❌ | `auto` | `auto/tavily_first/mineru_first/tavily_only/mineru_only` |

<details>
<summary><b>返回示例</b>（点击展开）</summary>

```json
{
  "ok": true,
  "source_url": "https://zhuanlan.zhihu.com/p/...",
  "engine": "mineru",
  "markdown": "...",
  "notes": ["auto_strategy_anti_bot:mineru_only"],
  "sources": ["https://zhuanlan.zhihu.com/p/..."],
  "decision_trace": {
    "request_id": "...",
    "policy_version": "policy.v1",
    "events": []
  }
}
```

</details>

#### `explore` - GitHub 项目解析

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `target` | string | ✅ | - | 仓库 URL / `owner/repo` / 关键词 |
| `issues` | int | ❌ | `5` | 采集 issue 数（`3..20`） |
| `commits` | int | ❌ | `5` | 采集 commit 数（`3..20`） |
| `external_num` | int | ❌ | `8` | 外部信号数量（`2..30`） |
| `extract_top` | int | ❌ | `2` | 提取前 N 条外链（`0..external_num`） |
| `with_extract` | bool | ❌ | `true` | 是否启用外链提取 |
| `confidence_profile` | string | ❌ | 读配置 | `deep/quick` 置信度策略 |
| `output_format` | string | ❌ | `json` | `json/markdown` |

#### `get_config_info` - 配置体检

无需参数，返回：

- 当前生效配置路径
- `search/extract/explore` readiness
- 脱敏后的 key 配置
- runtime 与 decision_trace 开关

---

<details>
<summary><h2>项目架构</h2>（点击展开）</summary>

```text
src/codex_search_stack/
├── config.py               # 配置加载（YAML 单入口）
├── mcp_server.py           # MCP 服务入口（4 tools）
├── validators.py           # 协议参数校验
├── key_pool.py             # Grok/Tavily key pool
├── policy/
│   ├── context.py          # 请求上下文
│   ├── router.py           # 搜索路由
│   └── extract_router.py   # 提取路由（anti-bot）
├── search/
│   ├── orchestrator.py     # 多源编排
│   ├── sources.py          # Exa/Tavily/Grok 适配
│   └── scoring.py          # 评分排序
├── extract/
│   ├── pipeline.py         # 提取管线
│   └── mineru_adapter.py   # MinerU 适配
├── github_explorer/
│   ├── orchestrator.py     # 尽调编排
│   └── report.py           # 报告渲染
└── observability/
    └── decision_trace_store.py  # 决策轨迹落盘与统计
```

</details>

---

## 常见问题

**Q1：为什么 `search` 返回空结果？**  
A：先跑 `uv run python "scripts/check_api_config.py"`；重点看 `search` readiness 和结果中的 `notes`。

**Q2：知乎链接为什么不是 Tavily 抽取？**  
A：`strategy=auto` 下命中高阻域名会自动路由 `mineru_only`，这是预期行为。

**Q3：如何验证 MCP 是否真的可用？**  
A：先 `codex mcp get "codex-search"`，再调用 `get_config_info`、`search`、`extract`、`explore` 逐项 smoke。

**asdfadsfsdaQ4：为什么 comparison 在 MCP 报参数错误？**  
A：MCP 单查询入口不支持 comparison 多查询流程；请改用 skill `search.py --queries ...`。

---

## 致谢与参考

感谢以下开源项目提供的灵感与方法参考：

- [blessonism/github-explorer-skill](https://github.com/blessonism/github-explorer-skill)  
  提供了 GitHub 项目调研流程与结构化报告思路参考。

- [GuDaStudio/GrokSearch](https://github.com/GuDaStudio/GrokSearch)  
  提供了 Grok 搜索能力接入与工具化设计思路参考。

---

## 文档导航

- `skills/README.md`
- `docs/configuration.md`
- `docs/search.md`
- `docs/extract.md`
- `docs/explore.md`
- `docs/mcp.md`
- `docs/policy-architecture.md`
- `docs/components-and-skills.md`
