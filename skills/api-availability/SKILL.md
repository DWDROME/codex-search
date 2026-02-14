---
name: api-availability
description: >
  Check current API availability for codex-search (Exa, Tavily, Grok, GitHub, MinerU).
  Use when users ask "当前 API 是否可用 / 哪个 key 挂了 / 服务健康度怎么样".
  Returns a traceable health report with config readiness + optional live probes.
---

# api-availability — API 可用性体检

目标：快速回答“现在哪些 API 可用、哪些不可用、为什么不可用”。

## 何时触发

- 用户问“API 可用性 / 健康检查 / key 是否失效”
- 搜索或抽取突然失败，需要先确认上游服务状态
- 回归前需要做一次运行环境体检

## 用法

仅配置体检（不打外网）：

```bash
uv run python "skills/api-availability/scripts/api_availability.py" --no-live --json
```

配置 + 实时探测（推荐）：

```bash
uv run python "skills/api-availability/scripts/api_availability.py" --json
```

严格模式（已配置服务任一失败则非 0）：

```bash
uv run python "skills/api-availability/scripts/api_availability.py" --strict --json
```

## Result Contract

输出 JSON 结构：

- `ok`: 是否通过（受 `--strict` 影响）
- `config`: 配置路径与 readiness
- `services`: 各 API 探测结果（`status/latency_ms/error`）
- `summary`: 汇总统计（ok/failed/skipped）

状态说明：

- `ok`: 可用
- `missing_config`: 未配置
- `skipped`: 未执行实时探测
- `auth_failed`: 认证失败
- `error`: 请求失败或上游异常

## 注意事项

- 本 skill 只做可用性检测，不做业务搜索结果质量判断。
- MinerU/GitHub 探测为轻量接口探测，不会提交真实解析任务。
- 如需业务链路验证，再配合 `scripts/skill_smoke_check.sh`。
