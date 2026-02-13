# Compatibility Watchlist（当前为空）

更新时间：2026-02-13（夜）

当前已无待保留兼容分支。

## 已移除

1. Key Pool 单字段旧格式兼容（`user@example.com----tvly...`）  
   - 变更：`src/codex_search_stack/key_pool.py`  
   - 现状：仅支持严格 CSV `service,url,key,weight`；非法行会带行号报错。

2. GitHub Token 旧变量名兼容（`GH_TOKEN` / `GITHUB_PAT`）  
   - 变更：`src/codex_search_stack/config.py`  
   - 现状：仅读取 `GITHUB_TOKEN`。

3. 脱敏快照中的 `GH_TOKEN` 采集  
   - 变更：`scripts/masked_env_snapshot.py`  
   - 现状：`secrets` 仅采集 `GITHUB_TOKEN`，不再包含 `GH_TOKEN`。
