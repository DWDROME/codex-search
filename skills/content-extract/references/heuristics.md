# 内容可用性启发规则（probe → fallback）

用于判定 Tavily 抽取结果是否可接受，若不满足则 fallback 到 MinerU。

## 接受 Tavily 结果（全部满足）

- 请求成功且有正文
- 正文长度显著（文章类建议 > 800 字符）
- 不含明显反爬/验证提示

## 强制 fallback 到 MinerU（命中任一）

### 1) 命中域名白名单

见 `domain-whitelist.md`，命中则跳过 Tavily 直接 MinerU。

### 2) 反爬或中间页特征

正文出现以下任一关键词：

- `environment abnormal`
- `verify you are human`
- `access denied`
- `security verification`
- `请在微信客户端打开`
- `验证码`

### 3) 内容过薄或明显缺失

- markdown 为空
- 正文长度过短（< 400）
- 内容仅为导航/页脚/提示页

### 4) 抽取失败状态

- 401/403/429/5xx
- 超时且重试仍失败

## 失败后输出要求

- 返回失败原因（`notes`）
- 返回下一步建议（补 key/改策略/强制 MinerU）
- 保留原始 URL 作为可追溯来源
