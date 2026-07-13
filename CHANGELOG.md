# Changelog

All notable changes to us-stock-causal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- v0.3.3: 信号矛盾胜率 (P2-8) + 5 段制报告生成 (P2-9, Phase 3 入口)
- Phase 3: 简洁呈现 (K 线图 + 因果标注)
- Phase 4: 自分析工具
- Phase 5: 调度

## [0.3.2] - 2026-07-13

### Added
- **P2-5: 历史模式匹配** — `src/patterns.py`
  - `find_similar_patterns(symbol, pattern_length=20, n_matches=10, forecast_horizon=5)`
  - Pearson 相关 (不用 DTW,快 100x,效果接近)
  - 当前 20d pattern → 历史最像 5-10 windows → 后续 5/20d 收益
  - 聚合统计: avg / median / win rate / max / min
- **P2-7: 宏观事件日历** — `src/events.py` + `config/events_2026.yaml`
  - 硬编码 2026 FOMC (8 次) / CPI (12 次) / NFP (12 次) / PCE (12 次) = 44 个事件
  - `upcoming_events(n=30)` / `past_events(lookback=14)` / `next_event()`
  - **1 周内事件警告**: 模型预测需谨慎 (事件驱动残差大)
- **`examples/patterns.py`** — 4 指数 20d pattern × top 5 matches × 5d forward
- **`examples/events.py`** — 未来 30/60 天宏观事件 + 下个事件警告

### Verified (2026-07-13)
- **4 指数历史模式匹配** (2026-07-10, 20d pattern, 5d forward, top 5):
  - DIA: avg -0.77% / win 20% (1/5 正) — **偏空,相似 pattern 后续跌**
  - QQQ: avg +2.15% / **win 100% (5/5 正)** — **强势,历史上类似形态后续都涨**
  - RSP: avg -0.33% / win 20% (1/5 正) — 偏空
  - QQQE: avg +1.92% / win 60% (3/5 正) — 偏多
- **未来 30 天事件** (今日 7/13):
  - 7/14 (明天) **CPI 6月** — 1 周内警告
  - 7/29 (16d) FOMC 7月 利率决议
  - 7/31 (18d) PCE 6月
  - 8/7 (25d) NFP 7月
  - 8/12 (30d) CPI 7月
- **过去 11 天事件**:
  - 7/2 NFP 6月 (现在回头看 QQQ 涨的"原因"之一)

### Key Insights
- **QQQ 当前 20d pattern 历史上 5/5 后续 5d 上涨** — 这是 v3 设计目标的"一手信息"
  - 不是"看多/看空"结论,是"统计上历史上类似形态后续如何"
  - 用户应自己判断:这跟当前宏观环境 (CPI 7/14, FOMC 7/29) 是否兼容
- **DIA 当前 20d pattern 历史上 4/5 后续跌** — 与 QQQ 相反,可能是因为 QQQ 科技集中
- **明天 CPI 是关键事件**:残差分析显示 7/5/2026 类似的 4.92% 单日下跌可能由事件驱动

### Phase 2 进度 (6/9 done)
- P2-1 ✅ 收益率
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因
- P2-4 ✅ 残差
- P2-5 ✅ 历史模式匹配
- P2-6 ✅ 关键阈值
- P2-7 ✅ 事件日历
- P2-8 ⏳ 信号矛盾胜率 (Phase 2.3)
- P2-9 ⏳ 5 段制报告 (Phase 2.3)

## [0.3.1] - 2026-07-13

### Added
- **P2-6: 关键阈值检测** — `src/thresholds.py`
  - SMA20/50/200 + 位置 (above/below + %)
  - 经典 floor trader pivot points (P/R1/R2/R3, S1/S2/S3)
  - 52-week high/low + 当前在 52w 区间位置
  - `get_thresholds(symbol, layer)` 主入口
- **P2-4: 残差深入分析** — `src/residual.py`
  - `compute_residual_timeseries(60d)` 时间序列
  - `detect_anomalies(2σ)` 异常日
  - `assess_weight_health()` t-test 评估 weights 是否需更新
  - ok / watch / stale 三档健康度
- **`examples/thresholds.py`** — Phase 2.1 demo
  - 4 指数当前水平表 (价格 / SMA / pivot / 52w)
  - 残差分析 (mean / std / t-test / anomalies)
  - 1 张 4-subplot 图 (1y 价格 + SMA + pivot levels)
  - Markdown 报告 `output/thresholds_<date>.md`

### Verified (2026-07-13)
- **4 指数当前水平** (2026-07-10):
  - DIA $525.78, SMA200 +8.14%, 52w 93%
  - QQQ $725.51, SMA200 +13.72%, 52w 88%
  - RSP $214.30, SMA200 +8.36%, 52w 94%
  - QQQE $120.61, SMA200 +13.50%, 52w 90%
  - **结论: 4 指数全部 above 200 SMA, 52w 88-94% 位置,late cycle bull market**
- **残差健康度** (60d t-test):
  - DIA: mean -0.012% / std 0.45% / p=0.84 → **ok** ✅
  - QQQ: mean +0.036% / std 0.45% / p=0.53 → **ok** ✅
  - RSP: mean +0.045% / std 0.34% / p=0.30 → **ok** ✅
  - QQQE: mean +0.110% / std 0.53% / p=0.12 → **watch** ⚠️
  - **结论: 2026-Q2 sector weights 大部分健康,QQQE 等权 ETF 有轻微偏差,无需立即更新**
- **异常日 (|z| > 2σ)**:
  - QQQ 6/5 (-4.92%) 和 6/23 (-3.35%): 模型预测不够跌,真实市场超跌 → 可能是宏观事件 (FOMC / CPI 数据)
  - DIA 6/4 / 6/16 / 7/2: 小幅正残差,市场比 sector 模型预测涨更多 → 大概率公司特定事件 (DIA 30 只成分股新闻)

### Key Insights (新)
- **200 SMA 全部 +8% 以上,52w 位置 88-94%**: 美股 4 主流指数都在"创新高"或"近创新高"位置
- **Pivot R1 是关键阻力**: QQQ R1 $726.63 (现价 $725.51,差 0.15%) — 短期关键阻力
- **残差分析证实 weights 有效**: 60d mean residual < 0.12% 且 p > 0.05,系统偏移不显著
- **2026-Q2 weights 不需更新**: 健康度评估支持当前配置

### Phase 2 进度 (4/9 done)
- P2-1 ✅ 收益率计算
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因分解
- P2-4 ✅ 残差深入
- P2-5 ⏳ 历史模式匹配 (Phase 2.2,DTW)
- P2-6 ✅ 关键阈值
- P2-7 ⏳ 财报日历 (Phase 2.2)
- P2-8 ⏳ 信号矛盾胜率 (Phase 2.3)
- P2-9 ⏳ 5 段制报告 (Phase 2.3)

## [0.3.0] - 2026-07-13

### Added
- **P2-1: 收益率计算** — `src/returns.py`
  - log return (可加,归因用) / simple return (显示用)
  - cumulative_return / rolling_return helpers
- **P2-2: 指数-行业权重矩阵** — `config/sector_weights.json`
  - 4 指数 (DIA/QQQ/RSP/QQQE) × 11 GICS 行业
  - DIA 价格加权,QQQ 科技集中,QQQE/RSP 等权不同
  - 标注"季度更新",Phase 2.1 用 openbb-etf 自动拉
- **P2-3: 归因分解** — `src/attribution.py`
  - `attribute_index(symbol, date, lookback_days)` 主函数
  - 直接 sector weight × sector return,残差 = actual - predicted
  - 4 指数批量: `attribute_all_indices(lookback_days)`
- **examples/attribute.py** — Phase 2 第一个真实可看的归因 demo
  - 控制台表格 (4 指数 × 当日 / 5 日)
  - 详细归因表 (每个指数 × 11 行业)
  - 1 张 stacked bar 图 (English 标签, 4 subplot)
  - Markdown 报告 `output/attribution_<date>.md`

### Verified (2026-07-13)
- **当日归因** (2026-07-10):
  - DIA  实际 +0.30% / 预测 +0.24% / **残差 +0.06%** ✅
  - QQQ  实际 +0.31% / 预测 +0.37% / **残差 -0.06%** ✅
  - RSP  实际 +0.37% / 预测 +0.26% / 残差 +0.12% (可接受)
  - QQQE 实际 +0.03% / 预测 +0.37% / 残差 -0.34% (等权 ETF 内部换手噪音)
- **5 日累计归因**:
  - DIA  -0.40% vs +0.65% (残差 -1.05%,DIA 价格加权特殊 + 权重近似值)
  - QQQ  +1.79% vs +1.62% (残差 +0.17%,合理)
  - RSP  -0.28% vs +0.16% (残差 -0.44%)
  - QQQE +0.38% vs +1.10% (残差 -0.71%)
- 全跑 < 1s (数据在缓存里)

### Known Limitations
- **Sector weights 是 2026-Q2 近似值**,不是实时数据。Phase 2.1 用 openbb-etf 自动拉
- **DIA 价格加权**: sector 权重是从 30 只成分股推算的近似,可能与实际有 5-10% 误差
- **5 日累计残差大**: 长期 lookback 时,权重变化 + 内部换手导致残差累积
- **等权 ETF (RSP/QQQE)**: 内部换手/再平衡会引入残差

### Phase 2 进度
- P2-1 ✅ 收益率计算
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因分解
- P2-4 ⏳ 残差分析 (Phase 2.1)
- P2-5 ⏳ 历史模式匹配 (Phase 2.2,DTW)
- P2-6 ⏳ 关键阈值 (Phase 2.1)
- P2-7 ⏳ 财报日历 (Phase 2.2,openbb.sec)
- P2-8 ⏳ 信号矛盾胜率 (Phase 2.3)
- P2-9 ⏳ 5 段制报告 (Phase 2.3)

## [0.2.1] - 2026-07-13

### Added
- **P1-9: 14 商品现货 ETF 代理** — `config/tickers.yaml` `commodities.spot_etf` 段
  - 与 14 期货 (=F) 一一对应: GLD/SLV/PPLT/PALL/CPER/USO/BNO/UNG/WEAT/CORN/SOYB/CANE
  - 基差 (basis) = futures - ETF,真正的市场预期信号
- **`examples/data_quality.py`** — P1-10 数据质量 gate
  - 8 项检查: 存在性 / 列名 / 无 NaN / 单调索引 / 无重复 / 价格合法 / 成交量合法 / 时效性
  - 47/47 parquet 全 PASS
  - 是 Phase 2 归因前的硬 gate

### Verified
- 47/47 parquet 数据质量: 全部无 NaN、单调索引、无重复、close > 0、volume >= 0、最新 < 7 天
- 23,481 rows 总数据, ~1.1 MB parquet 缓存
- 12/14 spot ETF 成功 (BAL/JO iPath ETN 2018 delisted,Phase 2 用期货代理)
- 12/14 fetch < 2s/ticker, 47 全 41.8s (含 2 个 retry 8s × 3 = 24s 浪费)

### Known Limitations
- **BAL (cotton ETN) + JO (coffee ETN) iPath delisted 2018**: 1:1 ETF 代理不可用
  - Phase 2 workaround: 直接用 CT=F / KC=F 期货作 spot 代理 (有展期噪音,但能用)
  - 未来可选:换成 Invesco DB Agriculture Fund (DBA) 篮子型 ETF (覆盖 6 种农产品)
- (继承 v0.2.0) 14 商品现货 =X yfinance 不可用 (已用 ETF 代理补完)

### Phase 1 完成度
**P1-1 ~ P1-10 全部 done** ✅
- 数据层 100% complete
- 47 个 ticker 干净数据
- Phase 2 因果分析 可以安全开干

## [0.2.0] - 2026-07-13

## [0.2.0] - 2026-07-13

### Added
- **49 ticker 数据集**(实际 35 个 parquet, 14 商品现货 =X 不可用 skip)
  - 4 指数: DIA / QQQ / RSP / QQQE
  - 11 行业 ETF (GICS 全 11,含 XLC Communication Services)
  - 6 宏观: ^VIX / DXY → DX-Y.NYB / ^IRX / ^FVX / ^TNX / ^TYX (完整 yield curve)
  - 14 商品期货 (=F): GC=F / SI=F / PL=F / PA=F / HG=F / CL=F / BZ=F / NG=F / ZW=F / ZC=F / ZS=F / SB=F / CT=F / KC=F
- **`src/data.py`** yfinance 统一封装 (替代 OpenBB commodity API 缺失问题)
  - ticker alias: DXY → DX-Y.NYB (yfinance 真实名字)
  - retry 3 次 + 指数 backoff
  - 列名小写 + DatetimeIndex + 去 tz
- **`src/cache.py`** parquet 增量缓存
  - 缓存 < 1 天 → 直接返回 (cached)
  - 缓存 > 1 天 → 增量更新 (incremental)
  - 无缓存 → 全量拉 (full)
  - safe_name: ^VIX → _VIX, GC=F → GC_F
- **`config/tickers.yaml`** 49 ticker 4 层分类 + GICS 标注 + 各层 description
- **`examples/fetch_all.py`** 一键拉全 49 ticker,带进度 + 缓存复用

### Verified
- 35/35 non-optional ticker 成功 (4 指数 + 11 行业 + 6 宏观 + 14 期货)
- 17,493 rows 总数据, 858 KB parquet
- Phase 1 fetch 实际耗时 ~40s (35 个 ticker × ~1s)
- 缓存复用: 二次跑 0.1s 完成 (cached status)

### Known Issues
- **14 商品现货 (=X) yfinance 不可用**: GC=X / SI=X / CL=X / GC=X 等 ticker 在 yfinance
  返回空数据 (8s timeout × 14 = 112s 浪费)。OpenBB `commodity.price.spot` 只支持 FRED provider
  (宏观数据,无商品)。**Workaround**: 用现货 ETF 代理 (GLD/SLV/USO 等),计划 v0.2.1 实现
- (继承 v0.1.0) matplotlib font warning on Windows (cosmetic)

### Design Pivot (重要)
- **OpenBB Platform SDK 不是 commodity 数据的好后端**: `obb.commodity.price.historical`
  方法不存在,`obb.commodity.price.spot` 只支持 FRED。**v0.2.0 改用 yfinance 直接拉**,
  OpenBB 退到 Phase 4 自分析工具再考虑 (那时可能用 OpenBB 跑 Jupyter)

### Not Yet Implemented (等 Phase 2+)
- 归因分解 (ret_ticker = α + β·ret_market + γ·ret_sector + ε)
- 历史模式匹配 (DTW 或欧式距离)
- 关键阈值检测 (支撑/阻力/财报)
- 报告生成 (5 段制)
- 飞书推送
- cron 调度
- 自分析工具 (Jupyter / sample notebook)

## [0.1.0] - 2026-07-13

### Added
- OpenBB Platform SDK 4.7.2 装好
- Clash 代理自动检测 (8 端口)
- AAPL 端到端 demo (380 rows / SMA20/50/200 / K 线图 / parquet)
- 项目结构 + git init + .gitignore + requirements.txt + README

### Verified
- 1 个 AAPL ticker 0.5s 拉到 380 行
- K 线图生成 117 KB PNG
- git commit `6f1ff7a` (9 files / 514 lines)
