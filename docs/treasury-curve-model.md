# 美债多期限曲线与现金流重估

第三阶段在 IEF/TLT 原有单期限久期近似旁，新增官方多期限曲线和逐债券固定现金流重估。
这是实验价格敏感性模型；报告的因果状态和可交易历史回测状态仍未就绪。

## 使用

```powershell
python -m examples.asset_report curve-sync --years 2026
python -m examples.asset_report collect --start 2026-09-30 --end 2026-10-07
python -m examples.asset_report report --symbols IEF TLT --start 2026-10-05 --end 2026-10-06 --mode retrospective --market-store data/asset_market --curve-root data/treasury_curves --json-output output/asset_report.json
```

curve-sync 保存财政部年 CSV 原文、SHA256和真实取得时间。跨年度期间下载两个年度。
report 不访问网络；不填曲线日期或缺失期限。即使没有 Yahoo ^TNX/^TYX，
曲线模型仍可独立计算；官方曲线缺失时原有单期限近似继续显示。
初次下载持仓若晚于期初日期，只能显示当前结构，不能回填历史权重；上述示例能否
进行期间重估取决于本地是否已有合格的10月5日或更早持仓快照。

## 如何读结果

财政部发布的是平价收益率 par curve，不是零息折现曲线。模型以6月、1/2/3/5/7/10/20/30年
par节点线性插值到半年网格，再逐期求折现因子；其余日期对折现因子的对数插值。
不外推30年以上，不声称复现财政部官方单调凸算法。

普通固定票息美元美国国债，从到期日倒推半年支付日，保留月末/闰年规则。
首个剩余周期按Actual/Actual比例计算。起息日需与半年支付周期一致；没有
首次支付证据的非常规长短票息拒绝。TIPS/FRN/缺票息等不计入已覆盖贡献。
iShares展示票息经过舍入；模型保留展示值，不猜测“精确票息”。

期初现金流、估值日期和原始期初权重固定，用期初、期末两条曲线重估PV。
按原始权重加总模型价格贡献，缺失/现金等不重归一化。报告分别显示已覆盖权重、
已知未建模权重、权重舍入或未知差额；100.01%的原始舍入总额不会被称为负现金。
Par节点±1bp后重新bootstrap所得敏感性属于曲线模型，不是按到期年限分桶。
Par节点敏感性可为负，不应解释成某个期限的实际仓位。

“曲线模型贡献 + ETF价格残差 = ETF价格回报”只是会计对照。固定日期重估不计
carry、rolldown、分红、费用、交易/再平衡、付款顺延或具体券的买卖价差。
财政部使用约纽约15:30的指示性买价报价，而ETF回报通常对应16:00市场收盘；
定价时钟也不同，残差不是纯跟踪误差，更不是遗漏因果因素。

取得时间仍不能证明历史首次发布或修订时间。严格模式继续要求报告结束日纽约
16:30前实际已取得曲线，财政部通常18:00前发布、可能延迟，因此新下载的历史
曲线不会被认证成当时收盘已知数据。

方法来源：[财政部曲线方法与发布时间](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology)、
[TreasuryDirect债券定价和付款](https://www.treasurydirect.gov/marketable-securities/understanding-pricing/)。
设计与验收见[第三阶段设计](superpowers/specs/2026-10-07-treasury-curve-design.md)。
