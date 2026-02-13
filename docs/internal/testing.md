# Testing（内部）

## 目标

补齐 `tests/`，提供不依赖网络的系统化单元测试，覆盖核心解析与编排分支。

## 运行方式

```bash
python3 -m unittest discover -s "tests" -v
```

## 当前覆盖

- `tests/test_key_pool.py`
  - key pool CSV 解析
  - 非法行（含旧格式）带行号报错
  - primary + pool 去重顺序
- `tests/test_config.py`
  - `GITHUB_TOKEN` 读取
  - `GH_TOKEN` / `GITHUB_PAT` 不再兼容
  - `CODEX_SEARCH_CONFIG` YAML 读取优先级（高于同名 env）
  - YAML 存在时忽略同名 env（单一入口）
- `tests/test_search_sources.py`
  - Grok 结果 JSON 解析（围栏/嵌入）
  - SSE 片段合并
  - URL 过滤
- `tests/test_extract_pipeline.py`
  - 内容可用性判断
  - 高阻域名直达 MinerU
  - Tavily 缺 key 回退
  - Tavily 候选轮转成功
  - Tavily 内容不可用回退
- `tests/test_mineru_adapter.py`
  - 默认 wrapper 路径
  - wrapper 不存在错误分支
  - subprocess 环境注入（`CODEX_WORKSPACE` / `MINERU_WORKSPACE`）
- `tests/test_scoring.py`
  - URL 归一化
  - 权威性评分
  - domain boost 对综合分影响
- `tests/test_validators.py`
  - search/extract/explore 协议参数边界校验
  - anti-bot 域名提取与高风险 host 判定
  - 规范化行为（大小写/数字入参）回归
