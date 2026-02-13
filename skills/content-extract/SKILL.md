---
name: content-extract
description: >
  URL 转 Markdown 的统一入口。用于网页正文提取、摘要前清洗、反爬站点兜底。
  先尝试 Tavily 抽取，命中高阻域名或抽取失败时自动降级 MinerU，并返回可追溯结果合同。
---

# content-extract（Codex 版）

## 触发时机

- 用户要求“提取网页正文/转 Markdown/网页总结”
- `web_fetch` 内容不完整、混乱或疑似反爬页
- 来源是知乎/微信/小红书等高阻域名

## 决策树（必须遵循）

```
输入 URL
  ↓
命中高阻域名白名单？
  ├─ 是：直接 MinerU（MinerU-HTML）
  └─ 否：先 Tavily Extract
            ↓
      内容可用？（见 heuristics）
        ├─ 是：返回 tavily_extract
        └─ 否：fallback 到 MinerU
```

参考文件：

- 白名单：`references/domain-whitelist.md`
- 可用性规则：`references/heuristics.md`

## 命令模板

默认策略（推荐）：

```bash
uv run python "skills/content-extract/scripts/content_extract.py" \
  --url "<url>" --max-chars 5000
```

强制 MinerU：

```bash
uv run python "skills/content-extract/scripts/content_extract.py" \
  --url "<url>" --force-mineru
```

## 输出合同（Result Contract）

统一返回 JSON，核心字段：

- `ok`
- `source_url`
- `engine`（`tavily_extract` / `mineru`）
- `markdown`
- `artifacts`（路径、task 信息）
- `sources`（原文 URL + 解析来源）
- `notes`（失败原因/降级说明/下一步建议）

## 失败处理与下一步建议

- Tavily 不可用：建议检查 Tavily key 或切换 key pool。
- MinerU 不可用：建议检查 token、网络或直接传镜像链接。
- 内容仍缺失：建议缩小 URL 范围（具体文章页而非聚合页）。

## 质量红线（强制）

- 不得只返回“提取失败”，必须带可执行 next step。
- 不得省略 `sources`；必须可追溯。
- 高阻域名不得反复重试 Tavily，直接走 MinerU。
