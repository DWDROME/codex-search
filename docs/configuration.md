# 配置说明（YAML 单一入口）

## 目标

对外只暴露一份配置文件：`config/config.yaml`。  
避免“主 API 填写”和“轮询（key pool）”混在环境变量中。

## 文件位置

- 默认读取：`config/config.yaml`
- 可选覆盖：环境变量 `CODEX_SEARCH_CONFIG=/abs/path/to/config.yaml`
- 规则：当 YAML 文件存在时，同名业务 env 不再生效（避免双入口混用）。

## 配置示例（含 GitHub Explorer）

```yaml
search:
  exa:
    api_key: ""
  grok:
    api_url: "https://api.x.ai/v1"
    api_key: ""
    model: "grok-4.1-thinking"
  tavily:
    api_url: "https://api.tavily.com"
    api_key: ""
extract:
  mineru:
    token_file: "~/.codex/secrets/mineru_key.txt"
explore:
  github_token: ""
runtime:
  search_timeout_seconds: 60
```

> `explore.github_token` 建议填写 GitHub Personal Access Token，用于提升 GitHub API 限额与稳定性。

## 轮询与填写分层

- 主 API 填写：`search.grok` / `search.tavily` / `search.exa`
- 轮询配置：`search.key_pool`
  - `enabled`: 是否启用轮询
  - `file`: key pool CSV 路径（格式固定 `service,url,key,weight`）

## 策略层配置（Policy）

- `policy.models.grok.default`: 默认模型
- `policy.models.grok.profiles`: `cheap/balanced/strong` 到具体模型的映射
- `policy.routing.by_mode`: 不同 mode 的默认 source mix（`exa/tavily/grok`）
- `policy.search.grok.retry_attempts`: Grok 每个候选 key 的总尝试次数（默认 3，失败会重试）
- `policy.extract.default_strategy`: extract 默认策略（`auto/tavily_first/mineru_first/tavily_only/mineru_only`）
- `policy.extract.anti_bot_domains`: 反爬域名列表（`auto` 策略命中后默认走 MinerU）
- `policy.explore.external.model_profile`: github-explorer 外部检索模型档位（`cheap/balanced/strong`）
- `policy.explore.external.timeout_seconds`: github-explorer 外部检索超时（秒）
- `policy.explore.external.primary_sources`: github-explorer 首轮 source mix（例如 `["grok","exa"]`）
- `policy.explore.external.fallback_source`: 首轮无结果回退源（默认 `tavily`）
- `policy.explore.external.followup_rounds`: 缺证据时自动补证轮数（默认 2）
- `policy.research.default_protocol`: research 默认协议（建议 `codex_research_v1`）
- `policy.research.fixed_rounds`: `codex_research_v1` 固定轮数（建议 4）

示例：

```yaml
policy:
  models:
    grok:
      default: "grok-4.1-thinking"
      profiles:
        cheap: "grok-4.1-fast"
        balanced: "grok-4.1-thinking"
        strong: "grok-4.1-thinking"
  routing:
    by_mode:
      fast: ["exa", "grok"]
      deep: ["exa", "tavily", "grok"]
      answer: ["tavily"]
  search:
    grok:
      retry_attempts: 3
  explore:
    external:
      model_profile: "strong"
      timeout_seconds: 60
      primary_sources: ["grok", "exa"]
      fallback_source: "tavily"
      followup_rounds: 2
  research:
    default_protocol: "codex_research_v1"
    fixed_rounds: 4
```

## 可观测性（DecisionTrace）

- `observability.decision_trace.enabled`: 是否在搜索/提取结果中输出决策轨迹
- `observability.decision_trace.persist`: 是否落盘为 JSONL
- `observability.decision_trace.path`: JSONL 路径（默认 `./.runtime/decision-trace/decision_trace.jsonl`）
- 决策轨迹字段：`decision_trace.request_id/policy_version/events[]`

聚合统计（失败率/延迟/命中源）：

```bash
uv run python "./scripts/decision_trace_stats.py" --limit 5000
```

## 体检命令

```bash
uv run python "./scripts/check_api_config.py"
```
