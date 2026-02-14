---
name: mineru-extract
description: >
  Use the official MinerU (mineru.net) parsing API to convert URL sources
  (HTML pages like WeChat articles, or direct PDF/Office/image links) into
  clean Markdown + structured outputs. Use when web fetch/browser extraction
  is blocked or low quality, and higher-fidelity parsing is needed.
---

# MinerU Extract（official API）

把 MinerU 当作“上游内容标准化器”：提交 URL -> 轮询任务完成 -> 下载结果 zip -> 提取主 Markdown。

## Quick start（MCP 语义对齐）

我们对齐 MinerU MCP 的心智模型，但**不运行 MCP server**。

- 主脚本（推荐）：`scripts/mineru_parse_documents.py`
  - 输入：`--file-sources`（逗号/换行分隔）
  - 输出：stdout JSON 合同 `{ ok, items, errors }`
- 低层脚本：`scripts/mineru_extract.py`（单 URL）

认证：

- 必须提供 `MINERU_TOKEN`（mineru.net Bearer Token）
- 可选 `MINERU_API_BASE`（默认 `https://mineru.net`）

默认模型启发式（与脚本一致）：

- URL 以 `.pdf/.doc/.docx/.ppt/.pptx/.png/.jpg/.jpeg` 结尾 -> `pipeline`
- 其他 URL -> `MinerU-HTML`（适合微信文章等 HTML 页面）

---

## 1) 配置 Token（建议写 skill 目录 `.env`）

```bash
# other/codex-search/skills/mineru-extract/.env
MINERU_TOKEN=your_token_here
MINERU_API_BASE=https://mineru.net
```

## 2) URL 解析为 Markdown（推荐）

MCP 风格包装脚本（返回 JSON）：

```bash
uv run python "skills/mineru-extract/scripts/mineru_parse_documents.py" \
  --file-sources "<URL1>\n<URL2>" \
  --language ch \
  --enable-ocr \
  --model-version MinerU-HTML \
  --timeout 600
```

如果需要把 markdown 文本内联到 JSON（便于后续总结）：

```bash
uv run python "skills/mineru-extract/scripts/mineru_parse_documents.py" \
  --file-sources "<URL>" \
  --model-version MinerU-HTML \
  --emit-markdown --max-chars 20000
```

低层单 URL（直接输出 markdown）：

```bash
uv run python "skills/mineru-extract/scripts/mineru_extract.py" \
  "<URL>" --model MinerU-HTML --print > "/tmp/out.md"
```

---

## Output（结果合同）

- `ok`
- `items[]`（每个输入 URL 的结果）
- `errors[]`

`items[]` 常见字段：

- `source`
- `task_id`
- `model_version`
- `full_zip_url`
- `out_dir`
- `zip_path`
- `markdown_path`
- `cached`
- `cache_key`

缓存目录（默认）：

- `other/codex-search/.runtime/codex-workspace/mineru-cache/<cache_key>/`
- 可通过 `MINERU_WORKSPACE` 或 `CODEX_WORKSPACE` 覆盖

---

## 常用参数

- `--model-version`: `pipeline | vlm | MinerU-HTML`
- `--enable-ocr`: 启用 OCR（映射到 `is_ocr`）
- `--enable-table true|false`: 表格识别
- `--enable-formula true|false`: 公式识别
- `--language ch|en|...`
- `--page-ranges "2,4-6"`（`MinerU-HTML` 不支持）
- `--extra-formats "docx,html,latex"`
- `--timeout` / `--poll-interval`
- `--cache` / `--no-cache` / `--force`

---

## Failure modes & fallback

- 受保护页面（登录/权限/地域限制）会失败。
  - 处理：保留原始 URL + 错误信息，建议提供可访问镜像 URL。
- 当前流程不支持本地文件路径（会写入 `errors[].next_step`）。
  - 处理：使用公开 URL，或后续新增 MinerU 批量上传流程。
- 解析质量不佳：
  - HTML 页面优先 `MinerU-HTML`
  - 文档类优先 `pipeline`，必要时试 `vlm`

---

## 交付红线（强制）

- 输出必须带原始来源 URL。
- 错误必须透传到 `errors`，禁止静默失败。
- 不得把受限页面伪装为“解析成功”。
- 本 skill 只做解析，不做登录绕过或权限绕过。
