# 资产专用分析

期间：2026-10-01 → 2026-10-02。模式：事后解释，不能作为当时可交易回测。

因果效应：未识别。以下为回报描述、官方结构和满足条件的机械近似。

个人账户持仓不是此报告的输入。行情缓存缺少历史发布与修订时间，当前不能认证为可交易历史回测。

## GLD

价格/报价变动：-0.6845%。
供应商调整序列总回报代理：-0.6845%；与价格回报差：+0.0000%，不能直接当现金分红收益。
adjusted series is a provider total-return proxy, not an official fund return
官方数据所属日期：2026-10-01；取得/保守可用时间：2026-10-03T15:15:47.790237+00:00。
来源：[SPDR](https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en)；SHA256：`5cff24592bf949c0293556ea4f4feb396526ff2b5b346883a05cccb54a62c2e6`。
independent licensed LBMA benchmark absent; NAV and close have different pricing times
结构日期：2026-10-01。
每股黄金：0.09167709 盎司；16:15官方溢折价：-0.0838%（缺值时不补齐）。
专用期间分析未就绪：exact GLD archive dates unavailable; no forward fill。

## GC=F

价格/报价变动：-0.9519%。
continuous futures quote change excludes roll, collateral and margin effects
专用期间分析未就绪：no official fund holdings model for this price index, futures or yield quote。

## IEF

价格/报价变动：-0.2800%。
供应商调整序列总回报代理：-0.2800%；与价格回报差：+0.0000%，不能直接当现金分红收益。
adjusted series is a provider total-return proxy, not an official fund return
官方数据所属日期：2026-10-01；取得/保守可用时间：2026-10-03T15:15:45.783241+00:00。
来源：[iShares](https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf/latest-holdings.csv)；SHA256：`a6c12ab1261fa5931c3e6a0aa4f9ce100565d6b69cd11636462998b87cf34f47`。
结构日期：2026-10-01。
债券 16 支，权重 99.9900%；已知权重总计 99.9900%；久期已覆盖债券权重 99.9900%。
按原始权重计算的久期：6.8643 年。
当前结构平行上移10bp的线性价格敏感性：-0.6864%，不是历史回报归因。
归因期初证据：日期 2026-10-01；取得/可用时间 2026-10-03T15:15:45.783241+00:00；SHA256 `a6c12ab1261fa5931c3e6a0aa4f9ce100565d6b69cd11636462998b87cf34f47`。
期初持仓 2026-10-01；单期限代理 ^TNX 变化 +4.00bp，线性久期近似 -0.2746%，价格残差 -0.0054%。
此近似未覆盖全曲线、凸性、票息、费用与非平行变化。

## TLT

价格/报价变动：-0.2960%。
供应商调整序列总回报代理：-0.2960%；与价格回报差：+0.0000%，不能直接当现金分红收益。
adjusted series is a provider total-return proxy, not an official fund return
官方数据所属日期：2026-10-01；取得/保守可用时间：2026-10-03T15:15:46.271120+00:00。
来源：[iShares](https://www.ishares.com/us/products/239454/ishares-20%2B-year-treasury-bond-etf/latest-holdings.csv)；SHA256：`52d189c4580b0fc9d8a795204c7eb8eef3aa2d0c613fc1aaa80ca60367fb20de`。
结构日期：2026-10-01。
债券 47 支，权重 100.0100%；已知权重总计 100.0100%；久期已覆盖债券权重 100.0100%。
按原始权重计算的久期：14.6912 年。
当前结构平行上移10bp的线性价格敏感性：-1.4691%，不是历史回报归因。
归因期初证据：日期 2026-10-01；取得/可用时间 2026-10-03T15:15:46.271120+00:00；SHA256 `52d189c4580b0fc9d8a795204c7eb8eef3aa2d0c613fc1aaa80ca60367fb20de`。
期初持仓 2026-10-01；单期限代理 ^TYX 变化 +2.70bp，线性久期近似 -0.3967%，价格残差 +0.1007%。
此近似未覆盖全曲线、凸性、票息、费用与非平行变化。

## QQQ

价格/报价变动：+1.0175%。
供应商调整序列总回报代理：+1.0175%；与价格回报差：+0.0000%，不能直接当现金分红收益。
adjusted series is a provider total-return proxy, not an official fund return
官方数据所属日期：2026-10-02；取得/保守可用时间：2026-10-03T15:15:45.291017+00:00。
来源：[Invesco](https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/46090E103/holdings/fund?idType=cusip&productType=ETF)；SHA256：`6f91615adacaf98ecd05e4eeb4b528b4b696308cd9b87373070b32e1566ff787`。
unknown weight: USDPDV:Currency
结构日期：2026-10-02。
官方记录 106 条；股票 101 条，权重 99.7517%；已知权重总计 100.0000%；未知权重记录 1 条。
非股票原始权重：Currency=0.243394%；Index Future=0.138193%；Currency Collateral=0.004913%；Synthetic Cash=-0.138193%；Currency=未知
专用期间分析未就绪：no eligible beginning holdings/availability; current structure is not historical attribution。

## ^NDX

价格/报价变动：+1.0044%。
price index change excludes reinvested dividends; QQQ weights are not index weights
专用期间分析未就绪：no official fund holdings model for this price index, futures or yield quote。

## ^IXIC

价格/报价变动：+1.1881%。
price index change excludes reinvested dividends; QQQ weights are not index weights
专用期间分析未就绪：no official fund holdings model for this price index, futures or yield quote。

## ^TNX

收益率 5.237% → 5.277%，变化 +4.00bp；不是债券投资回报。
yield quote change is not a bond investment return
专用期间分析未就绪：no official fund holdings model for this price index, futures or yield quote。

## ^TYX

收益率 5.603% → 5.630%，变化 +2.70bp；不是债券投资回报。
yield quote change is not a bond investment return
专用期间分析未就绪：no official fund holdings model for this price index, futures or yield quote。

## 因果研究下一步

需要带时间戳的政策意外冲击、独立的事件窗口报价、信息效应处理和样本外检验。日线、持仓核算与普通回归不足以识别政策冲击的因果效应。
