# MCP 接入说明（统一版）

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

## 能力映射（对外口径）

- `search` -> `search-layer`
- `extract` -> `content-extract` / `mineru-extract`
- `explore` -> `github-explorer`
- `get_config_info` -> 运行态体检

> `research` 工具保留用于 search-layer 的内部高级流程，不作为独立对外能力。

## 工具列表

- `search`：`query/mode/intent/freshness/num`
- `extract`：`url/strategy/max_chars`
- `explore`：`target/output_format/with_artifacts`
- `research`：`query/intent/freshness/num/max_rounds/protocol`（高级模式）
- `get_config_info`：配置脱敏体检

> 说明：`api-availability` 是内部支撑 Skill，不是 MCP tool。用于 API 异常排障前置检查。

## 协议校验（要点）

- `search/research`：`intent=status/news` 时必须给 `freshness`
- `research`：`max_rounds` 必须在 `1..8`
- `extract`：`url` 必须是 `http/https`，`strategy` 必须合法
- `explore`：`output_format` 仅支持 `json/markdown`

错误时返回统一合同：

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

1. 先跑可用性体检（推荐）：
   - `uv run python "skills/api-availability/scripts/api_availability.py" --json`
   - 需要严格失败时：`uv run python "skills/api-availability/scripts/api_availability.py" --strict --json`
2. 启动服务：`uv run --extra mcp codex-search-mcp`
3. 调用：`get_config_info`
4. 再依次 smoke：`search/extract/explore`（如需再测 `research`）
