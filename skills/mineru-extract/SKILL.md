---
name: mineru-extract
description: >
  MinerU 官方 API 封装。用于反爬站点或复杂文档（PDF/Office/图片/复杂 HTML）解析，
  输出高保真 Markdown 与结构化结果，作为 content-extract 的下游兜底。
---

# mineru-extract（Codex 版）

## 使用场景

- `content-extract` 触发 fallback 到 MinerU
- 目标页面反爬严格（知乎、微信、小红书）
- 文档类型复杂（PDF、PPT、扫描件、表格/公式密集）

## 前置配置

至少配置以下之一：

- `MINERU_TOKEN`
- `MINERU_TOKEN_FILE`（例如 `~/.codex/secrets/mineru_key.txt`）

可选：

- `MINERU_API_BASE`（默认 `https://mineru.net`）
- `MINERU_WORKSPACE` / `CODEX_WORKSPACE`（缓存目录）

## 模型选择建议

- HTML 页面（知乎/微信等）：`MinerU-HTML`
- 通用文档流：`pipeline`
- 视觉复杂页面可尝试：`vlm`

## 命令模板

```bash
uv run python "skills/mineru-extract/scripts/mineru_parse_documents.py" \
  --file-sources "https://zhuanlan.zhihu.com/p/619438846" \
  --model-version MinerU-HTML \
  --emit-markdown --max-chars 20000
```

多 URL：

```bash
uv run python "skills/mineru-extract/scripts/mineru_parse_documents.py" \
  --file-sources "<url1>\n<url2>" --model-version MinerU-HTML
```

## 输出约定

脚本返回 JSON，核心字段：

- `ok`
- `items[]`（每个输入 URL 的结果）
- `errors[]`

`items[]` 常见子字段：

- `markdown`
- `markdown_path`
- `zip_path`
- `task_id`

## 故障与降级

- 403/登录墙/地理限制：记录错误并保留原始 URL，建议用户提供可访问镜像。
- 解析超时：增大超时、拆分输入或降低并发。
- 解析质量不佳：切换模型（`MinerU-HTML` ↔ `pipeline/vlm`）再试。

## 质量红线

- 输出必须带原始来源 URL。
- 错误必须透传到 `errors/notes`，禁止静默失败。
- 作为兜底模块，不做“无证据成功”返回。
