# 资产专用分析

期间：2026-09-30 → 2026-10-01。模式：事后解释，不能作为当时可交易回测。

因果效应：未识别。以下为回报描述、官方结构和满足条件的机械近似。

个人账户持仓不是此报告的输入。行情缓存缺少历史发布与修订时间，当前不能认证为可交易历史回测。

## GLD

价格/报价变动：+0.5042%。
供应商调整序列总回报代理：+0.5042%；与价格回报差：+0.0000%，不能直接当现金分红收益。
adjusted series is a provider total-return proxy, not an official fund return
官方数据所属日期：2026-10-01；取得/保守可用时间：2026-10-03T15:15:47.790237+00:00。
来源：[SPDR](https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en)；SHA256：`5cff24592bf949c0293556ea4f4feb396526ff2b5b346883a05cccb54a62c2e6`。
independent licensed LBMA benchmark absent; NAV and close have different pricing times
结构日期：2026-10-01。
每股黄金：0.09167709 盎司；16:15官方溢折价：-0.0838%（缺值时不补齐）。
官方档案价格回报 +0.5041%；纽约10:30 NAV回报 -0.5915%；每股黄金储备变化 -0.0013%。
价格与NAV定价时点不同；回报差不能当净跟踪误差。独立授权黄金基准缺失，不能做黄金价格因果分解。

## 因果研究下一步

需要带时间戳的政策意外冲击、独立的事件窗口报价、信息效应处理和样本外检验。日线、持仓核算与普通回归不足以识别政策冲击的因果效应。
