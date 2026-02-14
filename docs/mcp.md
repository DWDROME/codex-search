# MCP 接入说明

## 服务入口

- 模块：`uv run --extra mcp python -m codex_search_stack.mcp_server`
- 脚本：`uv run --extra mcp codex-search-mcp`
- 依赖：`mcp>=1.6.0`（建议 Python 3.10+）

## Codex 配置示例

```toml
[mcp_servers.codex-search]
command = "uvx"
args = ["--python", "3.11", "--from", "/path/to/codex-search[mcp]", "codex-search-mcp"]
cwd = "/path/to/codex-search"

[mcp_servers.codex-search.env]
CODEX_SEARCH_CONFIG = "/path/to/codex-search/config/config.yaml"
```

## 工具列表

- `search`
  - 参数：`query/mode/intent/freshness/num/domain_boost/sources/model/model_profile/risk_level/budget_*`
  - 默认：`model_profile=strong`（可显式改为 `balanced/cheap`）
  - 返回：`SearchResponse` JSON（可含 `decision_trace`）
- `extract`
  - 参数：`url/force_mineru/max_chars/strategy`
  - 返回：`ExtractionResponse` JSON（可含 `decision_trace`）
- `explore`
  - 参数：`target/issues/commits/external_num/extract_top/with_extract/confidence_profile/output_format/with_artifacts/out_dir/book_max/download_book`
  - 返回：JSON 或 Markdown
- `research`
  - 参数：`query/mode/intent/freshness/num/domain_boost/model_profile/max_rounds/extract_per_round/extract_max_chars/extract_strategy`
  - 返回：多轮闭环 JSON（`rounds/results/notes/decision_trace`）
- `get_config_info`
  - 返回：脱敏后的配置与 readiness

## 协议层参数校验（与 Skills 对齐）

- `search`
  - `num` 必须在 `1..20`
  - `intent=status/news` 必须同时给 `freshness`
  - `intent=comparison` 在 MCP 单查询入口下会返回参数错误（应改走 skill `--queries`）
  - 时间敏感 query（如 latest/最新/本周）未给 `freshness` 会返回参数错误
- `extract`
  - `url` 必须是 `http/https`
  - `max_chars` 必须在 `500..200000`
  - `strategy` 必须是 `auto/tavily_first/mineru_first/tavily_only/mineru_only`
  - 命中高风险域名（知乎/微信/小红书）会强制 `force_mineru=true`
- `explore`
  - `issues/commits` 必须在 `3..20`
  - `external_num` 必须在 `2..30`
  - `extract_top` 必须在 `0..external_num`
  - `output_format` 仅支持 `json/markdown`
- `research`
  - `num` 必须在 `1..20`
  - `intent=status/news` 必须同时给 `freshness`
  - `extract_strategy` 必须是 `auto/tavily_first/mineru_first/tavily_only/mineru_only`

参数错误时返回统一结构：

```json
{
  "ok": false,
  "error": {
    "code": "invalid_arguments",
    "message": "..."
  }
}
```

## 验证步骤

1. 启动服务：`uv run --extra mcp codex-search-mcp`
2. 在 Codex 中调用 `get_config_info`
3. 分别调用 `search/extract/explore/research` 做 smoke 验证

## 端到端回归（MCP）

```bash
uv run python -m unittest tests.test_mcp_server
```
