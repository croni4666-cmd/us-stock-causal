---
name: us-stock-causal
description: "美股因果分析工具 (v3 重设计) — 4 指数 + 11 行业 + 6 宏观 + 28 商品的 49 ticker 数据集 + Phase 2 因果分析 (归因/阈值/模式/事件/信号) + Phase 3 简洁呈现 (5 段报告/K线/顶部情绪) + Phase 4 自分析 (export/jupyter/notebooks)。**不输出'看多/看空'结论**,只输出'驱动因子 + 阈值 + 历史 + 风险'。位于 G:\\Gemini - workspace\\trade market\\us-stock-causal\\,Phase 0-4 全部完成,Phase 5 调度待用户配 webhook 后开启。."
license: internal
version: 2.0
---


# us-stock-causal — 美股因果分析工具

## Overview

你是 us-stock-causal 项目的助手。这是一套让用户能"看到涨跌因果关系"的美股分析工具,目标是:
- **不输出"看多/看空"结论** — 输出"为什么涨/为什么跌"的因果链
- **给用户一手数据 + 模型** — 47 个 ticker 干净 parquet,可在 Jupyter 自己跑
- **简洁呈现** — 5 段报告 + K 线 + 顶部情绪

**项目位置**: `G:\Gemini - workspace\trade market\us-stock-causal\`
**当前版本**: 0.5.0 (Phase 0-4 done, Phase 5 待用户确认)

---

## 🎯 三档阅读 (Phase 3 完成)

| 时间 | 入口 | 看什么 |
|---|---|---|
| **30 秒** | `src/macro.py` `topline()` | VIX / 10Y / DXY + 4 指数 1d |
| **5 分钟** | `src/kline.py` `plot_4_indices()` | 4 指数 1y K 线 + 4 阈值线 (200 SMA / 50 SMA / R1 / S1) |
| **15 分钟** | `src/report.py` `render_full_report()` | 4 指数 × 5 段 (行情/归因/阈值/相似/风险) |

---

## 🗂️ 项目结构

```
G:\Gemini - workspace\trade market\us-stock-causal\
├── src/                     # 11 个核心模块
│   ├── proxy.py             # Clash 代理 (8 端口 auto-detect)
│   ├── data.py              # yfinance 统一封装 (DXY→DX-Y.NYB alias)
│   ├── cache.py             # parquet 增量缓存
│   ├── thresholds.py        # SMA + pivot + 52w
│   ├── returns.py           # log/simple return
│   ├── attribution.py       # sector weight × sector return 归因
│   ├── residual.py          # 60d t-test weight 健康度
│   ├── patterns.py          # Pearson correlation 历史匹配
│   ├── events.py            # FOMC/CPI/NFP/PCE 事件日历
│   ├── signals.py           # 3 源信号 + 矛盾 score
│   ├── macro.py             # 顶部情绪 1 行
│   ├── kline.py             # 4 subplot K 线
│   └── report.py            # 5 段制报告
├── config/
│   ├── tickers.yaml         # 49 ticker 4 层
│   ├── sector_weights.json  # 4 指数 × 11 GICS (2026-Q2 近似)
│   └── events_2026.yaml     # 44 硬编码事件
├── examples/                # 9 个 runnable 脚本
│   ├── fetch_all.py         # 49 ticker 批量拉
│   ├── data_quality.py      # 47/47 PASS
│   ├── attribute.py         # Phase 2 归因 demo
│   ├── thresholds.py        # Phase 2.1 阈值 + 残差
│   ├── patterns.py          # Phase 2.2 模式匹配
│   ├── events.py            # Phase 2.2 事件日历
│   ├── report.py            # 5 段报告生成
│   ├── kline.py             # 4 指数 K 线
│   ├── export.py            # 数据集导出 CLI
│   ├── notebook.py          # Jupyter Lab 启动器
│   └── generate_sample_notebooks.py
├── notebooks/               # 3 个 sample notebook
│   ├── 01_load_and_explore.ipynb
│   ├── 02_attribution_custom.ipynb
│   └── 03_pattern_match.ipynb
├── data/raw/<layer>/*.parquet   # 47 个 ticker 数据 (gitignore)
├── output/                       # 报告 + K 线 PNG
├── CHANGELOG.md                  # Keep a Changelog 格式
├── VERSION                       # 0.5.0
└── ROADMAP.md (workspace level)  # 5 phase single source of truth
```

---

## 🚀 常用命令 (一次记,长期用)

```bash
# 跑全套报告 (topline + 5 段 × 4 指数)
python examples/report.py

# 4 指数 K 线图
python examples/kline.py

# 数据集导出
python examples/export.py --tickers DIA,QQQ,RSP,QQQE --format csv
python examples/export.py --tickers XLK,XLF --start 2025-01-01 --format excel

# Jupyter Lab 启动
python examples/notebook.py              # 默认 8888
python examples/notebook.py --port 8889 --no-browser   # SSH 场景
```

---

## 🔍 模块快速参考 (按用途)

### 想知道"今天怎么样"
- `src.macro.topline()` → 1 行情绪
- `src.report.render_full_report(['DIA','QQQ','RSP','QQQE'])` → 5 段制
- `src.kline.plot_4_indices()` → K 线图

### 想知道"为什么涨/跌"
- `src.attribution.attribute_index('QQQ', lookback_days=5)` → sector 贡献
- `src.residual.assess_weight_health('QQQ')` → weights 准不准

### 想知道"历史上类似形态后续如何"
- `src.patterns.find_similar_patterns('QQQ', pattern_length=20, n_matches=10, forecast_horizon=5)`

### 想知道"下一个事件"
- `src.events.next_event()` → 下个 FOMC/CPI/NFP/PCE
- `src.events.upcoming_events(lookahead_days=30)` → 未来 30 天

### 想知道"信号矛盾不矛盾"
- `src.signals.aggregate_signals('QQQ')` → 3 源信号 + 矛盾 score

---

## 📊 当前数据快照 (2026-07-13)

**4 指数 5 日累计**:
- DIA: -0.40% / 信号矛盾 0.67 (mixed)
- QQQ: +1.81% / pattern win 80% / SMA200 +13.7% 距超买
- RSP: -0.28%
- QQQE: +0.38% / pattern win 70% / SMA200 +13.5% 距超买

**关键阈值**:
- 4 指数全 above 200 SMA (+8~+14%),**late cycle bull market**
- R1/S1 贴 52w 高 (突破 R1 才开新一轮)
- 明天 7/14 CPI 是 universal 风险

**信号分歧**:
- VIX 16.40 (+9.12%) **panic 急升** vs 4 指数都小涨
- 报告列事实不解读 — 用户自己判断

---

## ⚠️ 重要约束 (来自 ROADMAP)

1. **跑起来不花钱** (免费 tier,数据源 yfinance)
2. **不维护 hosted 服务**
3. **单人维护 ≤ 几小时/月**
4. **无"必须发布"义务**
5. **第三方免费 API 挂掉要优雅降级** (单 ticker 失败不阻塞)

---

## 🔄 工作流 (用户操作)

```bash
# 1. 拉新数据 (每天 1 次)
python examples/fetch_all.py

# 2. 数据质量验证 (Phase 2 之前必跑)
python examples/data_quality.py

# 3. 看 5 段报告
python examples/report.py

# 4. 看 K 线
python examples/kline.py

# 5. 自分析 (Jupyter)
python examples/notebook.py
```

---

## 🪦 历史 (不要重复)

### v1 (us-stock-daily 单 session 写, 2026-07-03)
**已删**。12 模块单 session 写,"完成"是 byte-level 不是 corpus-level。
**Learn**: 必须配真实数据 + 真实日志证据。

### 0.2 (us-stock-daily 三源投票, 2026-07-13)
**已删**。**产品方向错位** — 输出"看多/看空"投票,跟大 V 喊单没区别。
**Learn**: 目标错位比 bug 严重 100 倍。

### v3 (本项目, 2026-07-13)
因果分析 + 简洁呈现 + 自分析,完成 Phase 0-4。Phase 5 调度待用户配 webhook。
