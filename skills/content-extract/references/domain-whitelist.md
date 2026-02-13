# Domain Whitelist（强制走 MinerU）

命中以下域名时，建议直接走 `MinerU-HTML`：

- `mp.weixin.qq.com`
- `zhuanlan.zhihu.com`
- `www.zhihu.com`
- `zhihu.com`
- `www.xiaohongshu.com`
- `xiaohongshu.com`

## 匹配规则

- `host == domain`
- 或 `host.endswith('.' + domain)`

## 维护建议

- 若某站点持续出现反爬/空壳页，可增补到白名单
- 若站点恢复可抓取，可回归测试后移出白名单
