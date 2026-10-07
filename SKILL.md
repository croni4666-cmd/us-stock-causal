---
name: us-stock-causal
description: Use when working in us-stock-causal to generate market charts, choose chart profiles/options, inspect moving-average crossings, or review asset attribution and candidate causal models.
license: internal
metadata:
  skill_version: "2.1"
---

# us-stock-causal

项目根目录是包含本文件、`src/`和`examples/`的目录。先确认实际运行环境与数据位置，不使用旧机器上的绝对路径、旧行情快照或旧阶段状态作为当前事实。

## 图表类型与选项

用户要求生成图片或选择图表类型时，使用统一入口 `python -m examples.chart`。读取[图表profile和option参考](references/chart-profiles.md)，让用户的显式要求覆盖预设；没有指定时，默认`ma-review`。

| 用户表达 | profile | 主要输出 |
|---|---|---|
| 只看价格、清爽纯图 | `price` | K线及独立收盘标识，不默认画均线或写检查 |
| 看均线与穿线，附额外检查 | `ma-review` | 50/100/200日均线；图片外单独检查，推荐默认 |
| 比较黄金、ETF、纳斯达克、美债ETF | `comparison` | 多资产网格图，各标的独立检查 |
| 完整技术图、全部均线和参考价 | `technical` | 20/50/100/150/200日均线与R1/S1，独立检查 |

用`--list-profiles`核对当前可用预设。画哪些均线由`--smas`决定；检查哪些均线由`--review-windows`决定。它们可以不同。例如“纯图但仍要额外均线检查”使用`price --review`，不需要把检查挤进图里。

执行前确认标的、实际缓存目录和行情截至日；缺数据时说明缺口，不用合成数据冒充市场数据。生成后读取`.manifest.json`，确认实际profile、显式覆盖项、标的、报价日期、单位、输入哈希和本次产物。优先按manifest打开本次文件，不沿用旧输出。

## 图片与独立数值检查

- 行情图不叠加联储或其他宏观事件；profile与option都不恢复这些叠线。
- 收盘价、标的、单位和报价日期独立标识。GC=F是连续黄金期货美元/盎司，GLD是ETF美元/份；不能称作同一价格或自动取得的实时现货金价。
- 图片描述之外另读`.ma-review.md`及`.ma-review.json`。默认关注50/100/200日SMA，列当前位置、偏离、最新收盘事件、最近观察窗口以及历史最后一次确认记录。
- 使用每个日期自己的未经四舍五入的均线。上方/下方不等于当天刚穿越；贴线、从贴线离开、数据不足分别展示。该检查不是盘中触线，也不是均线之间的金叉/死叉。
- 默认“上次穿线”搜索全部已加载、可计算历史，分别给出最后上穿/下穿、最近一次方向、前后观察日期与距截至日的观察数。限定`--cross-history`时同时告知范围；未找到只能称范围内未记录，不能说市场历史从未发生。
- `--as-of`先截断数据再计算与绘图。缺失不填补；均线按可用日线数量计算，交易日覆盖未认证。历史缺口和实际检查数量保持可见。

## 生成后审查

数值检查与机器视觉分开：穿越日期来自行情计算，不能凭截图猜。核对数值、日期、单位、纵轴覆盖和产物后，再查看实际导出图片的标题、标识、叠层及可读性。明确哪些是程序检查、哪些是AI视觉观察；人工舒适度、色觉和阅读效率由用户实际看图验收。

PNG是默认视觉产物。既有SVG蜡烛悬停元数据问题未修复时，不用悬停确认价格；读取PNG标识或独立数值文件，不宣称SVG交互已验收。

## 分析边界与其他入口

DAG是低可信候选假设；图内形式识别、统计显著、PC重叠和扰动稳定不认证现实因果效应。只处理有可执行观察约束的登记命题，保留反例、探索记录和不可检验依赖，不制造命题成立概率。该skill负责路由和记录，不承担完整因果认证，也不把均线形态变成未来收益保证。

按任务读取对应文档，不把全部流程强制套在简单绘图上：

- 原有数据、阈值、形态、事件、报告和导出导航：[references/analysis-entrypoints.md](references/analysis-entrypoints.md)。
- 资产专用归因：[docs/asset-specific-attribution.md](docs/asset-specific-attribution.md)。
- 官方权重与市场快照：[docs/asset-data-pipeline.md](docs/asset-data-pipeline.md)。
- 美债曲线与现金流模型：[docs/treasury-curve-model.md](docs/treasury-curve-model.md)。
- 可证伪命题与支持程度：[docs/dag-hypothesis-review.md](docs/dag-hypothesis-review.md)。
- 图像审查与均线数值边界：[docs/chart-price-readability.md](docs/chart-price-readability.md)。

不将当期持仓倒填历史，不把ETF收益、指数点数、收益率报价与期货价格混为同一口径。沿用用户已经授权的任务范围；绘图和分析不构成合并、发布、发送消息或交易授权。
