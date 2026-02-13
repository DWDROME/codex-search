# Extract 组件说明

## 组件定位

`extract` 是 URL 内容提取管线，目标是稳定产出 Markdown。

主入口：

- 代码：`src/codex_search_stack/extract/pipeline.py`
- CLI：`codex-search extract ...`

---

## CLI 用法

```bash
codex-search extract "https://zhuanlan.zhihu.com/p/619438846" --max-chars 3000
```

参数：

- `--force-mineru`：强制走 MinerU
- `--max-chars`：截断输出长度
- `--strategy`：`auto | tavily_first | mineru_first | tavily_only | mineru_only`

---

## 配置项（YAML）

默认读取 `config/config.yaml`（可用 `CODEX_SEARCH_CONFIG` 覆盖路径）：

- `search.tavily.api_url` / `search.tavily.api_key`
- `search.key_pool.file` / `search.key_pool.enabled`（Tavily 提取重试）
- `extract.mineru.token` 或 `extract.mineru.token_file`
- `extract.mineru.api_base`
- `extract.mineru.workspace`
- `runtime.extract_timeout_seconds`
- `policy.extract.default_strategy`
- `policy.extract.anti_bot_domains`
- `observability.decision_trace.enabled`

---

## 运行逻辑（简版）

1. 先构建 `ExtractRequest`，再由 Policy 计算 `ExtractPlan`（first/fallback 引擎）。
2. `auto` 策略下：
   - 普通域名：`tavily_first -> mineru fallback`
   - 反爬域名：`mineru_only`
3. Tavily 路径会按 key pool 候选重试，超时受 `runtime.extract_timeout_seconds` 控制。
4. 输出统一 JSON（`ExtractionResponse`），含 `engine`、`notes`，可选 `decision_trace`。

---

## 典型场景

- 普通站点：通常直接 `engine=tavily_extract`
- 反爬站点（知乎/微信等）：常见降级 `engine=mineru`

---

## 常见问题

- 一直 Tavily 失败：检查 `TAVILY_API_URL` 是否可达，或切换/补充 key pool。
- MinerU 失败：检查 `extract.mineru.token_file` 与 `extract.mineru.workspace` 可读写。
- 提取质量不稳定：先看 `notes/decision_trace`，再决定是否用 `--strategy mineru_only`。
