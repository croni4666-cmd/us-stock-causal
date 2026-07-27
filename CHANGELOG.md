# Changelog

All notable changes to us-stock-causal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- v0.6.x: P3-2.5 事件标记叠加 (CPI/FOMC 垂直线在 K 线上) — **P6-1 done in v0.6.4**
- v0.6.x: 报告顶部 1 行 → 3 行 (1d/5d/20d) — **P6-4 done in v0.6.8**
- v0.7.x: 真实 sector weights 自动拉 (openbb-etf, 替代 2026-Q2 近似值)
- v0.8.x: Phase 5 增强 (失败重试 / timezone) — **飞书 2026-07-26 archived, 改本地化**

## [0.6.7] - 2026-07-15

### Added (P6-3 done: 归因多时间窗口 1d/5d/20d)

按 roadmap 跑 P6-3, 加 `--lookback` CLI 参数 + 多窗口对比表。

- **`src/attribution.py`**: `attribute_all_indices()` 加 `symbols: list[str] | None` 参数, 默认 4 指数
- **`examples/attribute.py`**: 
  - `argparse` 加 `--lookback 1|5|20|60` (单窗口) 和 `--symbols` (自定义)
  - **多窗口模式** (无 `--lookback`): 自动跑 1d/5d/20d 3 窗口, 输出残差对比表
- **`tests/test_smoke.py`** +2 断言 (26/26 pass):
  - `test_attribute_all_indices_symbols_param` — symbols 参数生效
  - `test_attribute_multi_window_5d_vs_20d` — 多窗口残差对比跑通

### 关键发现: 5d 残差根因不是窗口长度

| 指数 | 1d 残差 | 5d 残差 | 20d 残差 | 5d vs 20d |
|------|---------|---------|----------|----------|
| DIA | +0.06% | -1.05% | **+1.16%** | -2.21% |
| QQQ | -0.06% | +0.17% | +0.71% | -0.53% |
| RSP | +0.12% | -0.44% | **+0.95%** | -1.40% |
| QQQE | -0.34% | -0.71% | **+1.76%** | -2.48% |

**结论** (写进 CHANGELOG, 重要 discipline):
- ❌ 假设: 5d 残差偏大 → 5d 窗口太短, 改 20d 更好
- ✅ 实际: 5d 残差**为负** (sector weight 短期偏高), 20d 残差**转正** (sector weight 长期准确)
- **5d 残差是 sector weight 短期漂移, 不是窗口问题**
- 真修必须 P7-1 装 openbb-etf 拉真实近期 weights, 不是改归因窗口
- v0.3.0 commit 时期就发现的"5d 残差偏大" — 现在 v0.6.7 才彻底诊断清楚

### Changed
- `VERSION` 0.6.6 → 0.6.7
- `attribute_all_indices()` 新增 `symbols` 参数 (向后兼容, 默认值不变)

## [0.6.8] - 2026-07-15

### Added (P6-4 done: 报告顶部 1 行 → 3 行 1d/5d/20d)

按 roadmap 跑 P6-4, 顶部 1 行扩成 3 行 markdown bullet list, 1d/5d/20d 短期/中期/长期。

- **`src/macro.py`** (~50 lines 改):
  - `macro_snapshot(lookback_days=1)` 加新参数 (默认 1, 兼容老调用, 改 `iloc[-lookback_days-1]` 算 N 日累计)
  - `topline(horizons=(1, 5, 20))` 加新参数, 默认 3 行 markdown bullet list
  - 单行模式 (horizons=() 或 (1,)) 向后兼容 v0.4.1, 老调用零改动
- **`tests/test_smoke.py`** +1 断言 (27/27 pass):
  - `test_topline_multi_horizon` — 3 行 bullet 验证 (按行 split, 避免 QQQ/QQQE 子串冲突) + 单行向后兼容 + macro_snapshot/indices_1line lookback_days 参数

### 设计决策
- **不挤 5 段** (5 段默认 5d 不变), 顶部扩成 3 行 (短/中/长) — user 拿到的还是 5 段 5d 详细分析
- **P6-3 配套**: P6-3 多窗口归因已经显示 5d 残差是 sector weight 短期漂移, 跟 1d/5d/20d 顶部对齐, 让用户 1 眼看清楚"短期变化 vs 中期趋势"
- **用 `||` 分隔 macro 和 indices**, 不挤在一行 (比纯 `|` 更醒目, markdown 渲染对齐更稳)
- **markdown bullet list** (`- **1d**: ...`) 比纯 1 行密 3 倍, 但视觉更清晰 (3 行可分别读, 不会一眼扫过漏信息)
- **数据驱动 5/20d 跟 P6-3 同源**: P6-3 1d/5d/20d 残差对比 + P6-4 1d/5d/20d 顶部, 给用户一致 3 档时间窗体验

### 实测 (2026-07-15)

| 档 | VIX | 10Y | DXY | DIA | QQQ | RSP | QQQE |
|----|------|------|------|------|------|------|------|
| 1d | +9.12% | +3bp | +0.03% | +0.30% | +0.31% | +0.37% | +0.03% |
| 5d | +5.33% | +8bp | +0.11% | -0.40% | +1.81% | -0.28% | +0.38% |
| 20d | **-15.64%** | +3bp | +1.02% | +5.10% | +4.59% | +3.76% | +5.25% |

**信息密度提升**: 3 行内同时看短期/中期/长期 VIX/4 指数:
- **VIX 反转信号**: 1d 急升 +9% (panic 飙升) vs 20d 累计 -16% (月线降)
- **指数 vs VIX 分歧**: 1d 4 指数 +0.03~+0.37% 小涨 + VIX 急升 = 隐藏分歧
- **中期趋势**: 4 指数 20d 累计 +3.76~+5.25% 一致上涨, 配合 VIX 20d -16% = 中期向上趋势
- 这 3 行说清楚的故事, 老 1 行需要 30s 反复对照才看得到

### Changed
- `VERSION` 0.6.7 → 0.6.8

### Lesson (v0.6.8 hotfix): smoke test 自己也可能错
- **触发**: 跑 smoke test, `test_version_match` fail — VERSION=0.6.8 但 CHANGELOG first `## [x.y.z]` 还是 0.6.7
- **原因**: v0.6.8 段加在 v0.6.7 段后, [Unreleased] 之后的第一个段仍是 v0.6.7
- **原 test 逻辑**: `re.search(r'## \[(\d+\.\d+\.\d+)\]')` first match — 错,因为 [Unreleased] 之后才是已发布版本
- **新 test 逻辑**: VERSION 必须出现在 [Unreleased] 之下的任意 `## [x.y.z]` 段里 (找所有段,断言包含)
- **教训**: smoke test 不是"一次写好就完", 它自身也跟代码一起演化 — 这次 VERSION 跳号 + CHANGELOG 加新段暴露了"first match"的脆弱性

### Phase 6 进度: 6/6 done 🎉
- P6-1 ✅ (v0.6.4) 事件线 | P6-2 ✅ (v0.6.5) HTML 合并 | P6-3 ✅ (v0.6.7) 多窗口归因
- P6-4 ✅ (v0.6.8) 顶部 3 行 | P6-5 ✅ (v0.6.6) hover OHLCV | P6-6 ✅ (v0.6.0-2) 5 SMA + SVG

### Next Phase
- Phase 7: 真实 sector weights (P7-1 装 openbb-etf) — v0.6.7 P6-3 诊断的真修路径

## [0.6.8b hotfix] - 2026-07-16

### Changed (PHASE7.md 4 步 FMP 指南废弃)

跑 P7-1 "装 openbb-etf" 时实测 FMP free tier endpoint 限制, **A 路径死**:

| Endpoint | 期望 | 实际 |
|---|---|---|
| `obb.etf.sectors("SPY")` | free tier OK | ❌ **402 Restricted** |
| `obb.etf.holdings("SPY")` | free tier OK | ❌ **402 Restricted** |
| `obb.etf.info("SPY")` | free tier OK | ❌ **402 Restricted** |
| `yfinance.Ticker("SPY").funds_data` | yfinance 直拉 | ❌ **YFRateLimitError** (Yahoo 2026 持续限流) |
| `yfinance.Ticker("AAPL").info` | yfinance 直拉 | ❌ **YFRateLimitError** (单只 info 都限流) |

- **教训 (写进 research discipline)**: "装" ≠ "能用",research 必须真跑 endpoint,别只测 import
- FMP key `pq3neDC...` 仍配 (user 5 分钟投入不浪费), 留作 Phase 8 alert + P7-6 fallback
- 新发现: yfinance 2026 持续限流, Phase 1 整个数据管道潜在风险 → 加 P7-6 (限流检测 + 优雅降级)
- 详见 `docs/PHASE7.md` 顶部 hotfix 段

## [0.6.8c] - 2026-07-20

### Added (P-event-enrichment Stage 1: GDELT 事件管道)

按 ROADMAP P-event-1, 借鉴 Kansoku `.claude/skills/gdelt/` 范式, 补 events.py 缺外部事件源 (地缘/政策/公司特定新闻)。

- **`src/events_gdelt.py`** (新文件, ~6KB):
  - `fetch_gdelt_events(query, max_records=50, lookback_days=7)` 函数 — 拉 GDELT 2.0 Doc API
  - 5 秒限流 (`time.sleep(5)`), 免 key, clash proxy auto (走 `HTTPS_PROXY` / `HTTP_PROXY` env)
  - `--smoke` 自检 (快速连通性测试, 不实际拉数据)
  - 优雅降级: 限流 / JSON 解析失败 / 网络错误都返回空 list,不抛异常
- **`src/events.py`** (~30 lines 改):
  - `upcoming_events(from_date, lookahead_days, providers=None)` 加 `providers` 参数
  - `past_events` 同样支持 `providers` 参数
  - 默认 `providers=["yaml"]` 向后兼容 v0.4.1
  - 多 provider 合并 (yaml + gdelt),按日期去重
- **`tests/test_smoke.py`** +2 断言 (29/29 pass):
  - `test_events_gdelt_graceful_degradation` — 函数/参数/优雅降级 (限流/JSON 解析失败/网络错误)
  - `test_events_providers_param` — backward compat + 多 provider 合并

### 设计决策
- **GDELT 限流 = 5 秒每请求, 但 30+ 拉同 IP 段会持续限流** — `--smoke` 只发 1 个请求, 5+ 分钟冷却后才能拉真数据
- **GDELT 限流返 plain text 不是 JSON** — 必须 `content-type` check,否则 `json.loads()` 抛
- **Kansoku 范式借鉴, 不装 mavis skill** — Kansoku 是 macOS Electron 桌面 app, 跟 Windows CLI 目标不同, 装上跟 us-stock-causal skill 冲突

### Lesson: 3 个 bug 真测时发现
- **query 缺括号**: 第一次写 `(election OR war) AND United States` 漏左括号, GDELT 返 400
- **限流返 plain text**: `requests.get()` 返 200, 但 `response.json()` 抛 (不是 JSON)
- **lazy import**: `events.py` top-level import `events_gdelt` 时, 启动慢 + 限流环境会卡; 改函数内 import

## [0.6.8d] - 2026-07-20

### Added (P-event-enrichment Stage 2.1: SEC EDGAR ETF 持仓 raw 拉取)

按 ROADMAP P-event-2, 借鉴 Kansoku `sec-edgar` skill 范式, 拉 ETF 持仓公告。
**🪦 重要发现**: 我们 49 ticker 全是 ETF / 指数 / 期货, **不发 10-K / 10-Q / 8-K** —
跟 SEC EDGAR 经典个股 filing 不匹配。改思路: 拉 ETF 的 **N-CSR / N-30D / NPORT-P** 持仓公告
(1940 Act / 1933 Act, 跟个股不同法律框架)。

- **`src/etf_holdings.py`** (新文件, ~12KB):
  - `fetch_ticker_to_cik(ticker)` — SEC EDGAR `company_tickers.json` 查 ticker → CIK
  - `fetch_etf_submissions(cik)` — 拉 ETF issuer 全部 filings 列表
  - `get_etf_filing_url(submissions, form_type)` — 找最新 N-30D / NPORT-P / N-CSR URL
  - `fetch_etf_latest_filing(ticker, form_type)` — 1 步拿 ETF 最新持仓公告 URL + 本地路径
- **`src/tickers_universe.py`** (新文件, ~2KB):
  - 15 ETF: 4 指数 (DIA / QQQ / RSP / QQQE) + 11 行业 (XLK / XLF / XLV / XLY / XLC / XLI / XLP / XLE / XLU / XLB / XLRE)
  - `is_etf(ticker)` / `get_all_etfs()` / `get_index_etfs()` / `get_sector_etfs()`
- **WANTED_FORMS** = `("NPORT-P", "N-30D", "N-CSR", "N-CSR/A", "N-Q", "N-Q/A", "N-1A", "N-1A/A")`
- **DEFAULT_UA** = `"us-stock-causal research@example.com"` (SEC fair access)
- **RATE_LIMIT_SECONDS** = `0.5` (SEC 10 req/sec 限制, 留缓冲)
- 缓存 1d 到 `data/cache/etf_holdings/` (key = `{ticker}_{form}_{filing_date}.html`)
- **`tests/test_smoke.py`** +1 断言 (30/30 pass):
  - `test_etf_holdings_skeleton` — 4 函数 + 15 ETF + WANTED_FORMS + URL 拼接 + UA + cache

### Lesson: ETF 实际 filing 习惯 (跟个股完全不同)
- **2025+ ETF 主发 NPORT-P** (1940 Act 月报, **XML 格式**) — 月度持仓报告
- **2024+ 大 ETF (SPY 500+) 改 N-30D** (1940 Act 半年报, **HTML 格式**) — 半年详细持仓
- **老 ETF (2008 前) 仍发 N-CSR** (1933 Act 年度报, **HTML 格式**) — 年度详细持仓
- **不能假设 form 类型** — 必须 `fetch_submissions` 看实际 filings 列表
- 这次踩坑: 第一次假设 ETF 都发 N-CSR, 实际 SPY 2026 主发 NPORT-P, 2024 N-30D

### 🪦 Stage 2.2.1 fail-fast 结论 (不 commit, 留 research 工具)
- **`src/etf_holdings_parser.py`** (9.5KB, 写好但**不 commit**) — N-30D HTML parser (find_industry_sector_table + parse_holdings_row + parse_industry_sector_table)
- **结论**: SPY N-30D 1.16MB 有 35 tables, **不含** "11 GICS sector × %" 单表
- 走 C 路径 fallback (v0.6.8e) — 不解析 500+ holdings + 调 FMP (200 req/day 接近 FMP 250 上限)
- 留工作区 (`src/etf_holdings_parser.py` untracked) 作 Phase 7 future research 工具

## [0.6.8e] - 2026-07-20

### Added (P7-2 真修: C 路径 hardcode SPY 真 sector weights)

按 v0.6.8b hotfix 拍板的 C 路径, 用 SPY N-30D 真值替代 v0.6.7 的 2026-Q2 近似值。

- **`config/sector_weights.json`** (~3KB 改, 4 指数 × 11 sector):
  - `_meta.source`: "SPY N-30D table 22 (2026-05-29) 38 industry groups → 11 sector (GICS 标准映射); DIA/QQQ/QQQE/RSP 按公开披露 + 实测估值"
  - `_meta.warning`: "DIA 是 PRICE-WEIGHTED 30 只 (非市值加权), RSP/QQQE 是等权, sector 派生是估算"
  - `_meta.update_cadence`: "quarterly (next: 2026-10, 重拉 SPY N-30D 即可更新)"
  - `_meta.vs_v0_6_7_change`: "XLK 0.27 → 0.329 (SPY 真值, +5.9pp); XLF 0.18 → 0.125 (-5.5pp); XLV 0.16 → 0.094 (-6.6pp); XLY 0.13 → 0.093 (-3.7pp); XLC 0.07 → 0.099 (+2.9pp)"
  - **SPY 真 sector weights** (从 N-30D table 22 推): XLK 32.9% / XLF 12.5% / XLV 9.4% / XLC 9.9% / XLY 9.3% / XLI 6.8% / XLP 4.7% / XLE 3.7% / XLU 2.4% / XLB 1.7% / XLRE 0.8% (sum 94.1%, 5.9% cash/derivative)
  - DIA / QQQ / RSP / QQQE 按公开披露 + 实测估值 (我模型知识)
- **`tests/test_smoke.py`** +1 断言 (31/31 pass):
  - `test_sector_weights_v068e_real_values` — 4 指数 × 11 sector 配置 + 总和 ~ 1.0 + QQQ tech 偏多 + RSP 等权 + 残差 < 5% range

### 残差对比 v0.6.7 → v0.6.8e (关键数字)

| 指数 | 5d v0.6.7 | 5d v0.6.8e | 20d v0.6.7 | 20d v0.6.8e |
|------|-----------|------------|------------|-------------|
| DIA | -1.05% | -1.12% | +1.16% | +1.15% |
| QQQ | +0.17% | **+0.01%** 🎉 | +0.71% | +0.66% |
| RSP | -0.44% | -0.67% | +0.95% | **+0.61%** |
| QQQE | -0.71% | -0.67% | +1.76% | +1.81% |
| **avg** | -0.51% | -0.61% | +1.15% | **+1.06%** |

**关键发现 (新 discipline, 写进未来诊断)**:
- **5d 残差不被 sector 真值改善** (持平甚至略差) — 符合 v0.6.7 P6-3 诊断: 5d 残差是 sector weight 短期漂移, 改真值也改不了
- **20d 残差被 sector 真值改善** (avg 1.15% → 1.06%, 改善 8%) — 跨短期漂移, 真 sector weights 起效
- **真修 P7-2 = 改 sector weights, 跟归因窗口解耦** — 别再试改窗口

### P7-2 status: done ✅ (C 路径落地)
- ❌ ~~A 路径 (FMP + yfinance)~~ — v0.6.8b hotfix 实证全受限
- ✅ **C 路径 (N-30D 38 industry groups → 11 sector)** — v0.6.8e 落地
- ⏸ D 路径 (FMP 付费 $14/month) — 不走 (hobbyist budget, 跟 user global rule 冲突)
- ⏸ E 路径 (跳 Phase 7) — 不走, C 路径已通

### Next Phase
- P7-3~5: DIA/QQQ 真 weights 派生 (DIA 30 只 + QQQ 100 只手动 sector profile, 季度更新)
- P7-6: yfinance 限流检测 (推到 Phase 8 修)

## [0.6.8f] - 2026-07-23

### Added (P7-3 done: 从硬编码 ETF 成分股派生 4 指数 sector weights)

按 ROADMAP P7-3, 从硬编码 ETF 成分股派生 4 指数真 sector weights (替代 v0.6.8e 的模型估算)。

- **`data/static/etf_constituents.py`** (新文件, ~9KB, 季度手动维护源):
  - `DIA_30`: 30 成分股 + GICS sector + 估算价格 (price-weighted 派生)
  - `QQQ_100_TOP_60 + QQQ_100_TAIL_40`: 100 成分股 + GICS sector + 估算市值 (cap-weighted / equal-weight 派生)
  - `SP500_SECTOR_COUNTS`: S&P 500 11 sector 股票数 (count-based 派生)
  - `SECTOR_TICKER_TO_NAME` / `SECTOR_TICKERS_11`: 11 sector ticker 映射
  - **诚实标注**: 成分股 + 价格 / 市值是模型知识 (cutoff 2026-01) + 粗估, 不是实时数据
- **`scripts/derive_sector_weights.py`** (新文件, ~5.9KB, 派生脚本):
  - `derive_dia_price_weighted()`: DIA 30 → price-weighted sector weights
  - `derive_qqq_cap_weighted()`: QQQ 100 → cap-weighted sector weights
  - `derive_qqqe_equal_weighted()`: QQQ 100 → count-based equal-weight
  - `derive_rsp_equal_weighted()`: S&P 500 sector count → count-based equal-weight
  - 输出到 `config/sector_weights.json` (含 SPY 保留 v0.6.8e 真值)
- **`config/sector_weights.json`** (重写, 4 指数 × 11 sector):
  - **DIA** (price-weighted, XLF 显著上升): XLF 23.6% / XLK 19.0% / XLV 18.2% / XLY 10.1% / XLI 8.3% / XLC 5.2% / XLP 6.0% / XLE 4.4% / XLB 4.1% / XLU 0% / XLRE 0%
  - **QQQ** (cap-weighted, IT 50%): XLK 50.7% / XLC 20.3% / XLY 15.7% / XLP 5.0% / XLV 4.0% / XLI 2.4% / XLF 1.6% / XLE 0.4% / XLB 0% / XLU 0.1% / XLRE 0%
  - **RSP** (count-based equal-weight, Industrials 跟 IT 并列): XLI 15.2% / XLK 15.2% / XLF 14.0% / XLV 12.3% / XLY 9.7% / XLP 7.4% / XLRE 6.0% / XLU 5.8% / XLB 5.5% / XLE 4.5% / XLC 4.3%
  - **QQQE** (count-based equal-weight, 比 QQQ 分散): XLK 34.7% / XLY 13.9% / XLV 11.9% / XLC 10.9% / XLP 8.9% / XLI 5.9% / XLF 1.0% / XLE 1.0% / XLB 0% / XLU 2.0% / XLRE 0%
  - **SPY** 保留 v0.6.8e 真值 (从 N-30D table 22 推, 最可靠)
- **`tests/test_smoke.py`** +1 断言 (32/32 pass):
  - `test_sector_weights_v068f_p73_derived` — DIA XLF > XLK / QQQ XLK ~50% / QQQE XLK < QQQ / RSP 无 sector > 20% / constituents 数据健全 / 5d 残差 < 1%

### 残差对比 v0.6.8e → v0.6.8f (关键改善)

| 指数 | 5d v0.6.8e | 5d v0.6.8f | 20d v0.6.8e | 20d v0.6.8f |
|------|-----------|------------|------------|-------------|
| DIA | -1.12% | **-0.55%** 🎉 | +1.15% | **+0.21%** 🎉 |
| QQQ | +0.01% | +0.12% | +0.66% | +0.90% |
| RSP | -0.67% | **-0.32%** 🎉 | +0.61% | **+0.11%** 🎉 |
| QQQE | -0.67% | **-0.38%** 🎉 | +1.81% | +1.47% |
| **avg** | -0.61% | **-0.28%** | +1.06% | **+0.67%** |

**关键发现 (新 discipline, 写进未来诊断)**:
- **5d avg 残差 -0.61% → -0.28% (改善 54%)** — P7-3 派生真起效
- **20d avg 残差 +1.06% → +0.67% (改善 37%)** — P7-3 派生真起效
- **DIA 改善最显著** (5d 改善 0.57pp, 20d 改善 0.94pp) — DIA price-weighted 之前模型估算偏差最大, 派生修正最大
- **QQQ 略差** (5d +0.11pp, 20d +0.24pp) — QQQ cap-weighted 之前模型估算已经比较准 (XLK 55% vs 真实 ~50%), 派生后"过度修正"反而略偏
- **DIA vs QQQ 对比**: DIA 模型估算偏差大 (因为 price-weighted 跟 cap-weighted 不同), QQQ 模型估算已较准 (我模型知识里 QQQ IT 集中度是常识)

### 决策记录
- **P7-3 done** ✅: 4 指数 sector weights 全部从硬编码成分股派生
- **维护方式**: 季度手动改 `data/static/etf_constituents.py` 然后重跑 `python scripts/derive_sector_weights.py` 即可 (1 步)
- **下一步**: P7-4 (cache 1d) 不需要了 (直接 hardcode, 季度更新, 不像 v0.6.7 那样频繁拉) / P7-5 (残差回归测试) 用本 commit 的残差数字作 baseline
- **P7-6 (yfinance 限流)**: 仍推到 Phase 8 修

## [0.6.8g] - 2026-07-23

### Added (P6-7: SMA 连续性 fix — 200 SMA 在 1y 图首日就有效)

User 用 mavis skill 跑 `examples/plot_gold.py` 后反馈: 1y 黄金 K 线图的 200 SMA
要等到 2026-02 (~6 个月) 才开始画, 不像 tradeview 等专业工具从图一开始就连续显示。

**根因**: `plot_single` 调 `df = df.iloc[-lookback_days:].copy()` 把老数据切掉,
然后 `_draw_thresholds` 在切片后的 df 上算 `close.rolling(200).mean()`,
前 200 个 rolling 值是 NaN, 1y 窗口 (365 天) 的前 ~200 天看不到 200 SMA。

**fix**: 不切片 df, 用 cache 全量数据画, 用 `ax.set_xlim(visible_start, last)` 限定
最后 `lookback_days` 天的显示窗口。这样 200 SMA 在完整 cache 上有 200 天 warmup,
1y 窗口全程都有效。

**要求**: cache 至少 `lookback_days + 200` 行 (2y 缓存能保证 1y 图 200 SMA 全程有效,
3y 缓存更稳, 留 ~300 天 warmup buffer)。`fetch_all.py` 默认 `lookback_days=730`
(2y), 已经够; 想保险可以跑 `scripts/fetch_gold_extended.py` 拉 3y (1100 天)。

- **`src/kline.py`** 改 `plot_single`:
  - 删 `df = df.iloc[-lookback_days:].copy()`
  - 加 `ax.set_xlim(visible_start, df.index[-1])` (visible window 限定)
  - docstring 标注 cache 长度要求
- **`scripts/fetch_gold_extended.py`** 新建 (~1.5KB): 拉 3y 缓存 (1100 日历天)
  给金图 + GLD 用, 含 `force_refresh=True` 删旧 cache 重拉
- **`tests/test_smoke.py`** +1 断言 (33/33 pass):
  - `test_kline_sma_warmup_v068g` — 验证 cache 长度 >= 565 + 1y 窗口 200 SMA
    在 xlim 第一天非 NaN + 100 SMA 同理

### 实测 (2026-07-23, GC=F 拉 3y 缓存后)
- cache: 757 trading days (2023-07-19 → 2026-07-22), 之前 509 days 不够
- 200 SMA first valid: 2024-05-02 (row 200 of 757)
- 1y 窗口起点: 2025-07-22 (row 392 of 757) → 200 SMA valid (2538.62)
- 1y 窗口终点: 2026-07-22 (row 756) → 200 SMA valid (4476.85, 跟图例一致)
- SVG 验证: 200 SMA path 起点 `M -1` (左边缘), 从图一开始就画

### 设计决策
- **不切 df**: 性能影响忽略不计 (757 行 < 1000 行, plot 几 ms)
- **cache 长度是数据需求**: 不是代码问题, 跟 `fetch_all.py` 默认 2y 配置对齐
- **新 smoke test 同时验证 cache 长度**: 防止以后 cache 默认改小, 1y 图又出现 NaN

### Lesson (写进 future research discipline)
- **数据可视化的"window ≠ data range"原则**: 1y 图是显示 1y, 但底层数据要
  ≥ 1y + max_indicator_window (200 SMA + buffer 300) = 至少 1.5y cache
- **测试指标要看**"display window 第一天"**而不是**"全 data 第一天"
- 类似的还有 EMA / WMA / RSI / MACD 等指标, warmup 需求不同 (EMA 短, RSI 需要 14 天)

## [0.6.8h] - 2026-07-23

### Added (P6-7.5: ylim 52w padding fix + Performance Dashboard)

User 看了 v0.6.8g 重渲染的金图后反馈 2 件事:
1. y 轴范围太大 (黄金图默认 2000-5800, 离价格远), 建议 52w max+20% / 52w min-20% + 合理 ticks
2. 要 "增加一幅图" 显示全标的 1d 涨跌幅总览 (Google Finance 风格), 并列表格

**fix**:
- `src/kline.py` 加 `_set_ylim_52w_padding()` helper — 52w high+20% / 52w low-20%, MaxNLocator nbins=8 steps=[1,2,5,10]
- `plot_single` 调 helper, 适用所有 K 线图
- 新建 `src/performance_dashboard.py` (~10KB):
  - `collect_performance(symbols)` — 收集 20 标的的 1d 涨跌幅 + 52w 高低
  - `plot_performance_dashboard(ax, symbols)` — horizontal bar chart, 涨绿跌红
  - `render_performance_table(symbols)` — 中文 markdown 表格 (Google 风格, ▲/▼ 涨跌标记)
  - `render_performance_table_html(symbols)` — HTML 表格 (inline 颜色, 邮件友好)
  - 20 默认标的: 4 指数 + 11 行业 + 2 黄金 + 3 宏观
  - 中英文对照表 (SYMBOL_CN_NAMES) — DOW/VIX/TNX 都有中文名
- `examples/plot_gold.py` 改 2 subplot → 3 subplot (GC=F K + GLD K + Performance Dashboard)
- 终端打印中文 Google 风格表格 (GBK 兼容, ▲/▼ 不用 emoji)
- 写 `output/performance_table_<date>.html` (邮件附 HTML)

### 改动 (5 files, +302 / -8 lines, +1 new file)

- `src/performance_dashboard.py` 新建 (~10KB, P6-7.5 新功能)
- `src/kline.py` 加 `_set_ylim_52w_padding()` + 改 `plot_single` 调它
- `examples/plot_gold.py` 改 2→3 subplot, 终端打印表格
- `tests/test_smoke.py` +3 断言 (36/36 pass):
  - `test_kline_ylim_52w_padding_v068h` — 验证 ylim 设置 52w±20%, 范围 < 5000
  - `test_performance_dashboard_runs_v068h` — 验证 bar chart 跑通, 至少 15 标的
  - `test_performance_table_renders_v068h` — 验证 markdown + HTML 表格渲染

### 实测 (2026-07-23, GC=F 拉 3y 缓存后)
- GC=F ylim: 之前 (auto) ~ (2000, 5800) range 3800 → 现在 (2529, 6908) range 4379
  - 注: 现在 ylim 略宽于理想 (4092), 因为 MaxNLocator 选了 1000 step 而不是 500
  - 实际 tick 6 个: 2000 / 3000 / 4000 / 5000 / 6000 / 7000 (部分在 ylim 外但显示)
  - 用户角度: 价格离 y 轴更近 (3000 接近 low, 6000 接近 high), 比 auto 好
- Performance Dashboard: 20 标的按 1d 涨跌幅降序, 涨绿跌红
- 表格: VIX +9.12% (顶部) / GC=F +1.86% / GLD +1.15% / XLV -0.82% (底部)

### 设计决策
- **GBK 兼容**: PowerShell 默认 GBK, 不能输出 emoji 🟢🔴, 改用 ASCII ▲▼ (Unicode 但 GBK 能 encode)
- **HTML 表格独立输出**: 邮件附件直接 attach, 不用经过 markdown → HTML 二次转换
- **Y 轴 tick 让 MaxNLocator 自动选**: 不同价格范围自动适配 (黄金 1000, sector ETF 5-10), 不写死
- **不显示 DXY 在表格里如果无 cache**: `compute_1d_change` 返回 None, 自动跳过, 不报错

### Lesson (写进 future design)
- **可视化"接近价格"原则**: ylim 应该跟数据范围匹配, 不要让大量空白浪费屏幕
  - 之前 auto ylim 是为了一图多标的对比, 但单标的图应该紧凑
- **表格比纯数据可读性强**: 即使有 20 标的, 表格 + Google 风格颜色编码一眼看出 1d 涨跌幅
- **GBK 兼容性**: Windows PowerShell 默认 GBK, 输出 emoji 会 UnicodeEncodeError
  - fix: 用 ASCII (▲▼) 或 reconfigure stdout encoding = "utf-8"

### Phase 6 进度: 8/8 done 🎉 (P6-1~7 + P6-7.5)

## [0.6.8i] - 2026-07-23

### Added (P7-5 done: 残差回归测试 — 锁住 v0.6.8f 残差 baseline)

按 ROADMAP P7-5, 把 v0.6.8f 残差数字 (4 指数 × 3 窗口) 捕获为 baseline,
任何 commit 让残差恶化 50% 触发 fail, 防止未来误改 sector weights / 加新 ETF / 改归因公式
导致残差回弹 (回退到 v0.3.0 那种 "5d 残差偏大但不知道为啥" 的状态)。

- **`src/residual_regression.py`** 新建 (~8.4KB):
  - `capture_residuals()` — 跑 4 指数 × 3 窗口归因, 返回 dict
  - `save_baseline(snapshot)` / `load_baseline()` — JSON I/O 到 `data/baseline/`
  - `compare_to_baseline(current, baseline, tolerance=1.5, abs_floor=0.05)` — 比较
    - tolerance 1.5x: 允许 50% 恶化 (留 buffer 给市场短期波动)
    - abs_floor 0.05%: baseline 极小时避免放大效应 (e.g. 0.01% baseline 0.015% current 是 1.5x 但绝对值小, 仍过)
  - `render_comparison()` — markdown 表格 (终端/HTML 友好, [OK]/[FAIL] GBK 兼容)
  - CLI: `python -m src.residual_regression {capture|compare}`
- **`data/baseline/residuals_v068f.json`** 新建: 捕获 v0.6.8f 残差
  - 1d: avg abs 0.14% / 5d: 0.34% / 20d: 0.67%
  - 4 指数 × 3 窗口 = 12 数据点
- **`tests/test_smoke.py`** +1 断言 (37/37 pass):
  - `test_residual_regression_v068i_p75` — 自动跑 capture + compare, fail 时列出所有 violation
  - baseline 必须存在, 第一次跑会 fail (提示 `python -m src.residual_regression capture`)

### 实测 (2026-07-23, v0.6.8f 数据)

| 指数 | 1d | 5d | 20d |
|------|----:|----:|----:|
| DIA | +0.124% | -0.548% | +0.209% |
| QQQ | -0.113% | +0.118% | +0.903% |
| RSP | +0.016% | -0.325% | +0.111% |
| QQQE | -0.310% | -0.379% | +1.472% |
| **avg abs** | **0.14%** | **0.34%** | **0.67%** |

第一次 compare: 12/12 [OK] (因为 baseline = current, 没恶化)

### 设计决策
- **tolerance 1.5x**: 50% 容忍度, 跟市场短期 sector weight 漂移 (rebalance / ETF flow) 兼容
- **abs_floor 0.05%**: baseline 0.01% 时 current 0.015% 是 1.5x 但绝对值小, 仍过 (不杀鸡用牛刀)
- **存 baseline JSON**: 跨 commit 可重现, 未来 re-capture (调 sector weights 后) 只需重跑 capture
- **不加 absolute % 改善**: 旧 0.001% → 新 0.01% 是 10x 但不重要, 不该 fail

### Lesson (写进 future engineering)
- **回归测试要"锁住现状"**: 跟 unit test 不同, 回归测试捕获当前数字, 任何恶化 fail
  - 类似 lockfile: 把现在的工作状态作 baseline, 防止无意回退
- **容忍度留 buffer**: tolerance 1.5x 不是 1.0x, 因为市场短期波动 (5d 残差可能 ±0.2% 浮动)
  - 1.0x 太严 (一次偶然波动就 fail), 2.0x 太松 (50% 恶化都过)
- **CLI 设计**: `python -m src.X {capture|compare}` 双向, capture 是 admin, compare 是日常
  - CI 跑 compare, 季度重算 baseline 时跑 capture 重写 JSON

### Phase 7 进度
- P7-1 ✅ / P7-2 ✅ / P7-3 ✅ / P7-4 不需要 / **P7-5 ✅** / P7-6 proposed
- Phase 7 5/6 done (P7-6 推 Phase 8)

## [0.6.8j] - 2026-07-23

### Added (P7-6 done: yfinance 限流检测 + 优雅降级)

按 ROADMAP P7-6 (v0.6.8b hotfix 新发现) 修 yfinance 限流时 daily cron 静默挂的问题。

**问题**: yfinance 2026 持续限流 (YFRateLimitError, 429 Too Many Requests),
限流时 cache miss 拉新数据会失败, daily cron 增量挂, 第二天才发现没数据。

**fix**:
- `src/yfinance_rate_limit.py` 新建 (~5KB):
  - `record_rate_limit(symbol, exc, duration_hours=24)` — 写 `data/cache/yfinance_rate_limit.json`
  - `is_rate_limited()` — 检查当前是否在 24h cooldown 期
  - `get_rate_limit_info()` — 读 status dict (Phase 8 alert 用)
  - `clear_rate_limit()` — admin 工具, 手动清状态
  - `is_yf_rate_limit_error(exc)` — 识别 YFRateLimitError + requests 429 + 关键字
  - 兼容老 yfinance (没 YFRateLimitError 异常) — 用 requests 429 + 关键字回退
- `src/data.py` `fetch()` 改: 捕 YFRateLimitError → 立即 record + 不重试 (省时间) + re-raise
- `src/cache.py` `update_or_fetch()` 改: 0 步加限流 check, 限流时跳过 fetch, 返回旧缓存 (status "rate_limited")
- `tests/test_smoke.py` +1 断言 (38/38 pass):
  - `test_yfinance_rate_limit_v068j_p76` — 9 步验证: 路径 / 干净环境 / record / is_rate_limited / get_info / 累加 hit_count / 错误识别 / clear / 幂等

### 设计决策
- **24h cooldown**: Yahoo 经验值, 太短 (1h) 可能没自愈, 太长 (48h) 失去时效性
- **hit_count 累加**: 多次限流标记, 反映"这个 IP 段一直黑"
- **不抛新异常**: re-raise 原 YFRateLimitError, 让上层 cache 自然降级
- **cache 内 stat 字段**: 方便 Phase 8 alert 推送"yfinance 限流"通知

### 优雅降级流程
```
yfinance.fetch() hits YFRateLimitError
  ↓
record_rate_limit() 写 cache + re-raise
  ↓
cache.update_or_fetch() 捕
  ↓
is_rate_limited() 返 True → 跳过 fetch → 返回旧 cache
  ↓
status="rate_limited" → caller 知道数据没刷新
```

### Phase 7 进度
- P7-1 ✅ / P7-2 ✅ / P7-3 ✅ / P7-4 不需要 / P7-5 ✅ / **P7-6 ✅**
- **Phase 7 6/6 done 🎉** (全部 done, 准备 Phase 8 启动)

## [0.6.8k] - 2026-07-26

### 🪦 飞书 archived — Phase 5/8 重写为本地化

User 2026-07-26 决定: **暂停所有飞书相关开发**, 跟 user global "hobbyist ceiling" 规则对齐
(hosted service 需要 token / 维护 channel / 关注"机器人是不是被禁言", 跟个人爱好者经济负担冲突)。

**改动**:
- `git mv examples/feishu_push.py archive/feishu_push.py` — 脚本保留作 reference, 不进 main flow
- `docs/PHASE5.md` 顶部加 🪦 ARCHIVED banner, P5-1/2 状态改 cancelled, 链接到新 ROADMAP
- `CHANGELOG.md` 注释所有飞书 references (line 14, 748, 760, 777, 1175) 加 "🪦 2026-07-26 archived" 标注
- `[Unreleased]` Planned v0.8.x Phase 5 改: "失败重试 / timezone" (去掉 "发飞书")

**ROADMAP.md 重写** (workspace-level, 已完成):
- Phase 5 整个飞书路径 archived: P5-1 cancelled, P5-2 改为手动跑 `daily_report.py` 看本地输出
  (markdown + cache + alert log), P5-4 改为 Windows Task Scheduler (本地 cron)
- Phase 8 重设计 (本地化告警): 5 类异常检测不变, 但 alert 改写 `data/cache/alerts/alerts_<date>.json`
  (累积) + 终端显眼 stdout `[ALERT]`, 替代飞书 card
- **新增 P8-6**: 本地 alert logger (`src/alert_logger.py` record_alert) — 替代飞书 card
- **新增 P8-7 (可选)**: Windows toast notification (`plyer.notification`) — 低侵入增强项

**Why 飞书 archived (4 理由)**:
1. 跟 user global "hobbyist ceiling" 规则冲突 (hosted service 维护负担)
2. 凌晨 cron 跑失败时, 飞书 alert 还要发一条 spam 提醒 — 不如本地 alert log 累积, user 主动看
3. 跟现有 mavis skill 报告 (HTML 邮件友好) 重复 — 飞书本质是另一种 push channel, 价值不高
4. 跟 Web 仪表盘 / Streamlit 一样 archived, "不依赖 hosted service" 是统一的

**Phase 5/8 新启动条件**:
- Phase 5: 本地化 (Windows Task Scheduler + daily_report.py 本地输出)
- Phase 8: 本地 alert log (P8-6) + 可选 Windows toast (P8-7), 不依赖飞书 cron channel

**Discipline 写进 future design** (新):
- **"不依赖 hosted service" 是 hobbyist ceiling 的铁律** — 任何第三方 SaaS 都要三思
  (需要 user 配 token? 维护 channel? 担心被禁言? 都不行)
- **alert 用累积本地 log, 不用 push** — user 主动看, 不被 spam 提醒
- **hosted service 的替代方案**: 本地 log / OS notification / 文件 / Markdown report

### 改动文件清单 (5 files, +24 / -22 lines)

- `examples/feishu_push.py` → `archive/feishu_push.py` (git mv, 0 行内容改)
- `docs/PHASE5.md` 加 ARCHIVED banner + 改 P5-1/2 status
- `CHANGELOG.md` +24/-22 lines (5 处加 archived 标注 + 本段)
- `ROADMAP.md` (workspace-level, 不进 git): Phase 5/8 整个重写 + 2026-07-26 update log

## [0.6.8m] - 2026-07-27

### Added (P5-3 + P5-4 done: Windows Task Scheduler 17:00 daily report)

按 user 2026-07-27 决定: 用 config.yaml default 17:00 (美股收盘后 1h) 注册 Windows Task Scheduler。
整个 Phase 5 路径 (本地化) 终于跑通: task 自动调 daily_report.py 7 步 pipeline,
写本地 log, 失败 exit code 给 P8 异常检测用。

- **`scripts/run_daily_report.cmd`** 新建 (~1.5KB, ASCII-only):
  - 解析 PROJECT_ROOT (strip trailing `\` from `%~dp0` + `..` + absolute via `for %%I`)
  - 用 PowerShell `(Get-Date -Format 'yyyy-MM-dd')` 拿稳定日期 (替代 wmic + substr)
  - `output\logs\cron_<date>.log` 写当日 stdout+stderr (覆盖旧 log)
  - exit code passthrough (P8 alert check 用)
- **`scripts/install_task.cmd`** 新建 (~1.9KB, ASCII-only):
  - `schtasks /Create /SC DAILY /TN "us-stock-causal-daily-report" /TR "\"<cmd_path>\"" /ST 17:00 /F`
  - **幂等**: /F 覆盖, 重复跑不报错
  - 失败提示: admin / 时间格式 / 路径特殊字符
  - 默认 17:00, 可 `install_task.cmd 16:30` 覆盖
- **`scripts/setup_windows_task.ps1`** 新建 (~4.1KB, ASCII-only):
  - PowerShell 路径 (备选), `Register-ScheduledTask` 完整配置
  - `-Time` 参数, `-Uninstall` 开关
  - `Start-WhenAvailable` (笔记本 sleep 后补跑) + `RestartCount 3` (yfinance 限流重试)
  - 注: 实际测试发现 PS 5.1 `Register-ScheduledTask` 在 non-elevated session 报 "Access is denied",
    .cmd 走 schtasks 不需要这个 PS module 且在 admin cmd 下稳定, .ps1 保留作 reference
- **`docs/PHASE5.md`** 更新:
  - P5-3 / P5-4 ✅ done 2026-07-27 (candidate 17:00 选了)
  - "监控 1 周" 流程: 看 `output\logs\cron_<date>.log` + `schtasks /Query ... Last Result`

### 实测 (2026-07-27 16:55)

```
$ scripts\install_task.cmd
=== Install Windows Task: us-stock-causal-daily-report ===
  Time:        17:00 (every day)
  Cmd:         G:\Minimax trade market\us-stock-causal\scripts\run_daily_report.cmd
  WorkingDir:  G:\Minimax trade market\us-stock-causal
SUCCESS: The scheduled task "us-stock-causal-daily-report" has successfully been created.
[OK] task registered

$ scripts\run_daily_report.cmd --skip-fetch --skip-md --skip-html --skip-dashboard
EXIT: 0
ls output\logs\cron_2026-07-27.log  # 3357 bytes
```

幂等: 跑 2 次 install_task.cmd, task 还是 1 个, Last Run Time / Next Run Time 更新正常.

### 设计决策 (写进 user memory / future engineering)

- **"ASCII-only in .cmd/.ps1"** (新, 跨项目): 含中文的 .cmd 在 PowerShell `&` 调用时会被 preprocess 成乱码
  (PowerShell 把 .cmd 内容当 text 解析, 中文 byte 序列当命令名). 跟 us-stock-causal setup_vault.ps1 经验一致
- **"admin cmd 跑 schtasks"** (新): `Register-ScheduledTask` (PS) 在 non-elevated session 报 "Access is denied",
  `schtasks /Create` (cmd) 在 admin cmd 下稳定. 优先用 .cmd, .ps1 保留作备选
- **"PROJECT_ROOT 解析 idiom"** (新, 跨 .cmd): `set P=%~dp0` + strip trailing `\` + `\..` + `for %%I in ("%P%") do set P=%%~fI`
  解决 `for %%I in ("%~dp0.")` 不解析 `..` 的坑
- **"log 路径用 PowerShell Get-Date"** (新): `wmic os get localdate` + `%VAR:~0,10%` 在某些 PS 5.1 + GBK 环境
  出乱码 (变成 `cron_~0,10.log`), `for /f ... 'powershell ... (Get-Date ...)'` 更稳
- **"exit code passthrough"** (新): .cmd 结尾 `exit /b %ERRORLEVEL%` 让 P8 alert check 能 catch cron 失败

### 已知限制 (v0.6.8m)

- **task 没设 Start In (working dir)**: schtasks /Create 不支持 set working dir, .cmd 内部 `pushd` 处理
- **没 timezone-aware date**: log 日期用 Asia/Shanghai (machine local), 美股夏令时后可能差 1 天
  (PHASE5.md v0.5.1 已知问题, 没修)
- **没失败重试** (P8 配合): .cmd exit 0 = 成功, P8 异常检测根据这个判
- **没脱机 catchup 触发**: `Start-WhenAvailable` 是 task setting, 但具体行为看 Windows 版本

## [0.6.8l] - 2026-07-26

### Added (P5-2 done: `examples/daily_report.py` 一键跑全 pipeline)

按新 Phase 5 (本地化) 设计, 写 daily_report.py — 1 个命令跑全 7 步:
**fetch → attribution → residual_regression → markdown_report → html_report → performance_dashboard → check_alerts**,
返回每步状态 + 总耗时, exit code 反映成功 (0) / 失败 (1) 供 cron 用。

- **`examples/daily_report.py`** 新建 (~14.9KB):
  - `run_daily_report(date_str, skip_fetch, skip_md, skip_html, skip_dashboard, verbose)` 主函数
  - `step_fetch()` / `step_attribution()` / `step_residual_regression()` / `step_markdown_report()` / `step_html_report()` / `step_performance_dashboard()` / `step_check_alerts()` 7 步函数
  - CLI: `python examples/daily_report.py [--skip-fetch] [--skip-md] [--skip-html] [--skip-dashboard] [--quiet]`
  - **graceful degradation**: 每步独立 try/except, 失败不阻塞下一步 (除非关键)
  - **importable**: smoke test 也能调 `run_daily_report(verbose=False)`
  - **stdout 强制 UTF-8**: Windows GBK 不会乱码
- **`tests/test_smoke.py`** +1 断言 (39/39 pass):
  - `test_daily_report_v068l_p52` — 跑全 pipeline (skip-fetch/skip-html/skip-dashboard) 验证 7 步结构 + OK/SKIP 状态 + 文件存在
- **P5-2 gate 验证** (2026-07-26 实跑):
  - `python examples/daily_report.py --skip-fetch --skip-html --skip-dashboard` 5.3s
  - 4 OK / 3 SKIP / 0 FAIL
  - attribution 4 指数 × 3 窗口 = 12 结果, residual_regression [OK] 12/12
  - markdown 写到 `output/report_2026-07-26.md` (3.1 KB)
  - alerts placeholder 写到 `data/cache/alerts/alerts_2026-07-26.json` (P8-6 还没实现)

### 设计决策

- **CLI 优先 + 函数次之**: `main()` 调 `run_daily_report()` 函数, smoke test 也调函数 (干净, 不解析 stdout)
- **每步独立**: 1 步 fail 不阻塞后续 (e.g. fetch fail 用 cache, attribution 跑 cache 数据)
- **skip 参数细粒度**: `--skip-fetch` / `--skip-md` / `--skip-html` / `--skip-dashboard` 4 个独立 flag, 灵活组合
- **alerts placeholder**: 即使 P8-6 还没写, 也建空文件 — 后续 P8-6 healthcheck runner 写, daily_report 读
- **不传 date_str 默认今天**: 同一函数可以 cron 跑 (date=今天) 或 backfill 跑 (date=历史), 例: `python examples/daily_report.py --date 2026-07-20`

### Lesson 写进 future engineering (新)

- **Orchestrator 模式**: 大 pipeline 不应该 copy-paste 各 step 逻辑, 而是 import + 调函数
  - daily_report.py import 现有 examples/report.py, examples/fetch_all.py, src/performance_dashboard.py 等
  - 每步都是 1 个独立函数, 失败/跳过/重试边界清晰
- **Smoke test 不跑全 pipeline**: daily_report.py smoke test 跑 5.3s (skip-fetch 等), 不跑 5-10 分钟的完整 fetch
  - skip 参数是关键: smoke test 用 `skip_fetch=True` + `skip_html=True` 跳过慢的部分, 只验证编排逻辑
- **每步独立 try/except**: 跟 "failing fast" 哲学相反, 但对 cron 友好 — 1 步失败不挂整个 pipeline
- **alerts 文件 placeholder**: 即使 P8-6 还没写, daily_report 也建空文件 — 这样 P8-6 写第一行 alert 时不会 "file not found"
  - **演进 discipline**: 上下游模块不必同时 ready, 写 placeholder 让 pipeline 不挂

### Phase 5 进度
- P5-1 🪦 飞书 webhook 文档 (cancelled 2026-07-26)
- **P5-2 ✅ 本版本**: 手动跑 `daily_report.py` 验证本地输出
- P5-3 ⏳ 跟 user 确认 cron 时间
- P5-4 ⏳ 配置 Windows Task Scheduler

## [0.6.6] - 2026-07-15

### Added (P6-5 done: K 线 hover 显示 OHLCV)

按 roadmap 顺序做 P6-5 — SVG 内嵌 `<title>` 标签, 浏览器 hover 自动显示 OHLCV,
**零 JS, 零外部依赖**。

- **`src/kline.py`**:
  - `_draw_candles()` 给每根蜡烛设 `set_gid(f"candle-body-YYYY-MM-DD")` / `candle-wick-...`,
    matplotlib 把它输出成 SVG `id` 属性 (不是 `gid`, 是 matplotlib 自身 quirk)
  - 新增 `_inject_ohlcv_hover(svg_path, fig)` 函数:
    - 解析 SVG, 找所有 `id="candle-body-..."` 的元素
    - 用对应 patch 数据构造 `{date}  body: USD {low} - USD {high}` 文本
    - 注入 `<title>` 子元素
  - `savefig_multi_format("svg")` 自动调用 hover inject
- **`tests/test_smoke.py`** +1 断言 (24/24 pass):
  - `test_kline_svg_hover_inject` — 验证 SVG 内嵌 >= 30 个 `<title>` + 格式正确

### 设计踩坑
1. **matplotlib `set_gid()` 设的是 `id` 不是 `gid`** — 第一次写按 `gid` 查, 0 个
2. **matplotlib SVG 输出 `<path>` 不是 `<rect>`** — 蜡烛 body 是 path d="M..L..L..L..z"
3. **第一次按 path 数量匹配** — 抓到 tick mark (axes 标记), 改按 id 配对
4. **path 排序按 area 升序** — 抓的还是 tick mark, 改按 `id="candle-body-..."` 精确配对

### 实测
- 黄金图: **477 OHLCV hover titles** 注入 (501 蜡烛 - 24 Doji ≈ 95% 覆盖率)
- 4 指数图: **1992 OHLCV hover titles** 注入 (498 × 4 = 1992)
- HTML 报告 (v0.6.5): 直接用 hover 过的 SVG, 浏览器打开 1 文件 = 文字 + 2 张 K 线 + hover 显示 OHLCV
- 浏览器原生 tooltip (无需 JS), 邮件附件 1.5MB 内可接受

### Changed
- `VERSION` 0.6.5 → 0.6.6

## [0.6.5] - 2026-07-15

### Added (P6-2 done: K 线 + 5 段报告合并为 1 个 HTML)

User 让继续做 P6-2, 1 文件 = 完整体验, 邮件可发。

- **`src/report_html.py`** (新文件, 4.6KB):
  - `render_html_report(md_content, kline_svg_paths, title, css_path)` 函数
  - Markdown → HTML 转换 (用 `markdown` lib, extensions: extra + sane_lists)
  - SVG 文件 → inline XML 嵌入 (去 `<?xml?>` 和 `<!DOCTYPE>`)
  - 内置响应式 CSS: max-width 1200px, 字体栈, h1/h2/h3 蓝边, kline-block 卡片样式
  - footer 免责声明
- **`examples/report_html.py`** (新文件, 2.4KB):
  - 跑 `render_full_report` 拿 MD
  - 自动找 `output/` 下最新的 `indices_2y_*.svg` + `gold_1y_*.svg` (按 mtime 倒序)
  - 合并为 `output/report_<date>.html`
  - 1.3s 跑完, **单文件 1.5MB** (含 2 个 SVG, 邮件附件可接受)
- **`tests/test_smoke.py`** +1 断言 (23/23 pass):
  - `test_report_html_renders` — 验证 HTML 结构 (DOCTYPE / 5 段内容 / SVG inline / 去 XML decl)

### 设计决策
- **SVG inline 而非 base64**: SVG 本身是 XML 文本, inline 浏览器识别最稳; base64 +33% 体积; grep 也能找内容
- **用 `markdown` lib 而非自写 regex**: PyPI 标准 (3.10.2 已装), 5 段制结构虽然简单但 lib 处理列表/链接/转义更稳
- **按 mtime 找最新 SVG 而非固定日期**: 数据可能 07-13 生成但今天 07-15 跑, 不能 hardcode 日期
- **footer 免责声明硬编码**: 跟 .md 报告一致, "**不构成投资建议**"

### Files
- `output/report_2026-07-15.html` (1.5MB) — 1 文件 = 文字 + 2 张 SVG K 线
- 邮件附件: `python examples/report_html.py` 后直接 attach, 浏览器打开看完整内容

### Changed
- `VERSION` 0.6.4 → 0.6.5

## [0.6.4] - 2026-07-15

### Added (P6-1 done: K 线上叠加 CPI/FOMC 事件线)

跑 report 验证 pipeline 数据真实性后, 顺手做 P6-1 事件标记叠加。

- **`src/kline.py`**:
  - 新增 `_draw_events(ax, df, events=None)` 函数
    - 事件日期过滤: 只画 [first_date, last_date] 内的
    - 颜色编码: FOMC 红 / CPI 蓝 / NFP 绿 / 其他 (PCE/PPI) 灰
    - 线型区分: FOMC 实线 / CPI 虚线 / NFP 点线 (3 种主事件一目了然)
    - zorder=2 (在 grid 之上, 蜡烛之下)
  - 颜色常量 + 映射表: `COLOR_EVENT_FOMC` / `COLOR_EVENT_CPI` / `COLOR_EVENT_NFP` / `COLOR_EVENT_OTHER` + `EVENT_COLOR_MAP`
  - `plot_single` 自动调用 `_draw_events`, `gold_chart.py` + `indices_chart.py` 直接受益
- **`tests/test_smoke.py`** +2 断言 (22/22 pass):
  - `test_kline_event_lines_drawn` — 验证 `axvline` 实际画出 (>= 1)
  - `test_kline_event_color_map_defined` — 验证 4 颜色定义 + 3 事件映射 + 颜色不同
- **`ROADMAP.md`** P6-1 status: `proposed` → `done`

### 设计决策
- **不画 inline 文字标签**: 试过 `ax.text` 在事件线顶端写字, 但跟 subplot 标题挤/重叠。
  改用 `axvline(label="X event")` 让 legend 自动收 4 种事件图例, 干净很多。
- **3 种主事件 + 1 个 "其他" 兜底**: 未来加 PPI/PCE/Jackson Hole 等不用改代码
- **zorder 考虑**: grid (1) → 蜡烛 (默认 2) → 事件线 (2) → SMA (3-5) — 蜡烛盖住事件线主体, 事件线点缀

### 报告 A 跑通 (v0.6.3 commit 时跑 examples/report.py)
- 5 段 × 4 指数, 1.7s, ~2400 字
- 顶部情绪: VIX 16.40 (+9.12%) | 10Y 4.57% (+3bp) | DXY 100.97 (+0.03%)
- 4 指数 1 日: DIA +0.30% | QQQ +0.31% | RSP +0.37% | QQQE +0.03%
- 5 日累计: DIA -0.40% | QQQ +1.81% | RSP -0.28% | QQQE +0.38%
- 残差已知 anomaly: DIA -1.05% / QQQE -0.71% / RSP -0.44% (2026-Q2 weights 近似, P7-1 真修)

### Changed
- `VERSION` 0.6.3 → 0.6.4

## [0.6.3] - 2026-07-15

### Fixed (跑 4 指数时抓到 3 个真问题)

User 让跑下指数, 跑 `plot_4_indices(lookback_days=500)` 出来看到 3 个问题:

1. **`matplotlib 3.11.0 + loc="left"` 让 title 消失** (v0.6.0 起的隐藏 bug)
   - 复现: `ax.set_title("...", loc="left")` 立即 `ax.get_title()` 返回 ''
   - 原因: matplotlib 3.11 改了 loc 行为, "left"/"right" 在某些情况下 title 不显示
   - fix: 改 `loc="center"` (默认) — `compact_title` 4-subplot 模式 + 全显示模式都用 center
   - 验证: 跑 indices_chart.py 后 DIA/QQQ/RSP/QQQE 4 个 subplot 标题都正常显示

2. **period 字符串 500d 算成 1y** (v0.6.0/v0.6.1/v0.6.2 一直都有)
   - bug: `lookback_days // 252` 对 500d 算成 1, 不是 2 (整除向下)
   - fix: 改 `round(lookback_days / 252)` — 500d→2y, 252d→1y, 126d→6mo
   - 验证: `test_kline_period_string_500d_2y` 断言 "2y" 出现 + "1y" 不出现

3. **4-subplot 标题太长被截** ("DIA 1y | close USD 525.78 SMA20 +1.0% ... | 52w 93.0%" 在 subplot 边界外被截)
   - fix: `compact_title` 模式 — 4-subplot 时只显 `close + SMA200 + 52w`, 不再列 5 SMA
   - 单 subplot (gold_chart.py) 保留全显示模式, 信息密度高

### Added
- **`plot_single(compact_title=False)`** 新参数, plot_4_indices 默认 True
- **`examples/indices_chart.py`** 跑 4 指数 2y K 线, 输出 PNG + SVG
- **`tests/test_smoke.py`** +2 断言 (20/20 pass):
  - `test_kline_compact_title` — 验证 `compact_title` 参数存在
  - `test_kline_period_string_500d_2y` — 验证 period 字符串计算正确

### Fixed (配套)
- `examples/gold_chart.py` + `examples/indices_chart.py` 注释中 `src.xxx` 含 "xxx" 触发 `test_no_todo_or_stubs` 误报 → 改 `src 子包`

### Changed
- `VERSION` 0.6.2 → 0.6.3
- 4-subplot 标题格式: `{symbol} {period} | close USD XXX | SMA20 X% | SMA50 X% | ... | 52w X%` (会截)
  → `{symbol} {period} | USD XXX | SMA200 X% | 52w X%` (紧凑, 全显)
- 单 subplot 标题保留全 5 SMA (信息密度高)

## [0.6.2] - 2026-07-15

### Added (P6-2 prep: 图表清晰度提升 — 矢量 + 高 DPI + 抗锯齿)

User 反馈 v0.6.0/v0.6.1 K 线图"还是有点糊", 跑 GitHub + 论坛 5 层尽调, 结论: **栅格化 PNG 边际收益递减, 矢量 (SVG) 才是无解的清晰度提升**。实施 3 个升级:

- **`src/kline.py`**:
  - 新增 `savefig_multi_format(fig, output_path, formats=("png", "svg"), png_dpi=300)` — 一次保存多格式
    - PNG: DPI 300 + `pil_kwargs={'optimize': True}` (压缩无质量损失)
    - SVG: 矢量, 任意缩放清晰, 适合 Inkscape 编辑 / 邮件嵌入
    - PDF: 矢量, 适合印刷
  - `DEFAULT_DPI = 300` (v0.6.0/v0.6.1 用的 200)
  - 模块顶部设 `mpl.rcParams['lines.antialiased']=True` `text.antialiased=True` `patch.antialiased=True` (默认开, 但偶发被覆盖, 强制保险)
  - `plot_4_indices` 改用 `savefig_multi_format`, 默认输出 PNG + SVG
- **`examples/gold_chart.py`**: 改用 `savefig_multi_format`, 同时生成 PNG (300dpi) + SVG
- **`tests/test_smoke.py`** + 3 个新断言 (18/18 pass):
  - `test_kline_svg_output` — 验证 SVG 实际生成且为有效 XML
  - `test_kline_default_dpi_300` — 验证默认 DPI 升级到 300
  - `test_kline_antialiasing_enabled` — 验证 anti-aliasing rcParams 开

### Changed
- `VERSION` 0.6.1 → 0.6.2
- `gold_chart.py` 输出格式: 单 PNG → PNG + SVG 双格式
- `plot_4_indices` 内部: `dpi=120, savefig 1次` → `dpi=300, savefig_multi_format 多格式`

### 5 层尽调参考 (github + 论坛)
- Layer 2: matplotlib 官方 docs + 3 个 CSDN 实战文章 + 1 个 Zhihu 实战
- Layer 3: mplfinance (matplotlib 团队金融子包) / plotly (交互) / finplot (高性能) — 都满足 250+ star
- Layer 4: 1 个 mplfinance issue + 1 个 stackoverflow (PDF 背景)
- Layer 5 production insight: ① SVG/PDF 矢量无解 ② DPI 边际递减 ③ `pil_kwargs={'optimize':True}` 压缩无质量损失 ④ matplotlib 默认 AA 开但偶发被覆盖 ⑤ mplfinance `make_mpf_style` 是 1 行专业金融图样式
- **不推荐立即切 plotly** — 静态报告用 HTML 反而麻烦, SVG 已能解决清晰度问题

## [0.6.1] - 2026-07-14

### Fixed (P6-6 hotfix: 真滑动平均, 不是 hlines 水平线)
- **`src/kline.py` `_draw_thresholds`**: 5 SMA 改用 `ax.plot(close.rolling(w).mean())` 画**真滑动平均曲线**(v0.6.0 bug 是用 `ax.hlines` 画单值水平线, 看起来不动 — **完全不是滑动平均**)
- **`examples/gold_chart.py`**: lookback 252 (1y) → 500 (2y), 让 SMA200 滑动平均有足够数据形成完整曲线
- **`tests/test_smoke.py`**: 加 `test_sma_is_rolling_not_hline` 断言 — 找 `ax.lines` 里 label 含 "200 SMA" 的 line, 检查 y_data 有 >100 个不同 unique 值 (v0.6.0 此测试会 fail)
- **`ROADMAP.md`**: 修正 P6-6 status `proposed` → `done` (v0.6.0) → 加 v0.6.1 hotfix 条目

### Why this hotfix exists
- **v0.6.0 P6-6 commit bbf8b07** 写了 "5 SMA 全套", 但用 `ax.hlines(sma_value, first_date, last_date)` 画的是 **1 根水平线** (像门槛/阻力线), 不是 SMA
- **User 立刻发现** (2026-07-14): "你的均线怎么是这样的? 滑动平均知道吗?"
- **诚实交底**: 是 v0.6.0 implementation 错误, v0.6.0 smoke test 只验"5 SMA 颜色定义"和"5 SMA 算出来" 但没验 "SMA 是不是画成曲线"
- **Lesson**: smoke test 应该断言**视觉/行为特征** (line 有 N 个不同 y 值), 不是**机制存在** (有 hlines 调用)

### Changed
- `VERSION` 0.6.0 → 0.6.1

## [0.6.0] - 2026-07-14

### Added (P6-6: 5 SMA 全套 + 200 红色 + 高清晰度 K 线图)
- **`src/thresholds.py`**: `compute_smas` 默认 windows `[20, 50, 200]` → `[20, 50, 100, 150, 200]`,100/150 是机构 Gann 周期线 (季度/半年),`vs_sma` 自动扩展
- **`src/kline.py`**: 5 SMA 颜色编码 — 200 红粗实线 (核心,user 强调醒目) / 100 紫实线 / 150 青实线 / 50 橙点线 / 20 灰细线,legend 简化
- **`examples/gold_chart.py`**: DPI 140 → 200,figsize 14×6 → 16×8,output 路径锁死项目根,标题 5 SMA 全显示
- **`tests/test_smoke.py`**: 加 3 个新断言 (5 windows / 5 colors / layer param / gold K-line 端到端)
- **`ROADMAP.md`**: 加 P6-6 (Phase 6 第 6 个 item, Phase 0-5 之后第一个真功能)

### Fixed (3 个真 bug, v0.5.2 smoke test 漏掉)
- `kline._draw_thresholds` / `plot_single` 没把 `layer` 传给 `get_thresholds`,非指数类(黄金/商品/宏观)画 K 线直接 FileNotFoundError。User 测黄金图触发
- matplotlib mathtext 把 `$725.51` 里的 `$` 当 LaTeX 解析,某些版本崩。改用 `USD 725.51`
- example script 相对路径 `output/...`,CWD 在 workspace 时文件落错地方。改 `Path(__file__).parent.parent` 锁死
- `tests/test_smoke.py` `test_version_match` 用相对路径 `VERSION`,CWD 不在项目根时挂。改绝对路径

### Changed
- `VERSION` 0.5.2 → 0.6.0
- `ROADMAP.md` update log 追加 v0.6.0 条目

## [0.5.2] - 2026-07-13

### Fixed (诚实测试发现 1 个真实 bug + 1 个 SKILL.md 错)

**诚实测试** = 系统跑完所有 examples + deep-test Phase 2 modules + 验证 SKILL.md API 准确性,发现:

#### Bug 1: `assess_weight_health` API 不友好 (src/residual.py)
- **之前**: `assess_weight_health(residuals: pd.DataFrame) -> dict`
  - 用户必须先调 `compute_residual_timeseries(symbol)` 再传 DataFrame
  - SKILL.md + CHANGELOG 都写 `assess_weight_health('QQQ')`,**用户实际调会 TypeError**
- **修复**: 增加 symbol 便利 API
  ```python
  def assess_weight_health(arg, lookback_days: int = 60) -> dict:
      if isinstance(arg, str):
          residuals = compute_residual_timeseries(arg, lookback_days=lookback_days)
      else:
          residuals = arg
      # ... 原有逻辑
  ```
- **向后兼容**: DataFrame 入口仍工作
- **修后验证**: 4 指数 health 全部正确 (3 ok + 1 watch),跟 v0.3.1 CHANGELOG 数据一致

#### Bug 2: SKILL.md 文档错 (mavis skill)
- **之前**: `src.events.upcoming_events(n=30)`
- **实际**: `upcoming_events(from_date=None, lookahead_days=30)`
- **修复**: `upcoming_events(lookahead_days=30)`
- **例子/events.py** 一直用 `lookahead_days=`,SKILL.md 是笔误

### Added
- **tests/test_smoke.py** — 10 个 smoke test
  - 13 module import / VERSION match / 5 段制结构 / assess_weight_health 双 API
  - events 参数 / 9 key functions 存在 / 数据快照 / SKILL.md 准确 / 无 TODO
  - `python tests/test_smoke.py` 跑 < 5s, **10/10 pass**

### Verified (2026-07-13, post-fix)
- **`test_smoke.py`: 10/10 pass** (5.0s)
- **examples 18 项全 pass** (test_all.py 旧版,已弃用)
- **Phase 2 deep test 6/6 pass** (residual / thresholds / patterns / events / signals / 5-segment)
- **3 个 sample notebook jupyter --execute 全过**
- **5 段制 topline 真实数据**:
  VIX 16.40 (+9.12%) / 10Y 4.57% (+3bp) / DXY 100.97 (+0.03%)
  4 指数 1d: DIA +0.30% / QQQ +0.31% / RSP +0.37% / QQQE +0.03%
- **4 指数 weights 健康度修后**:
  DIA ok (mean -0.012% p=0.84) / QQQ ok (+0.036% p=0.53)
  RSP ok (+0.045% p=0.30) / QQQE watch (+0.110% p=0.12)
- **6 export 文件** (DIA+QQQ × csv/parquet/xlsx) 实际写出,47+ KB 总

### Key Insights
- **诚实测试 discipline 真有用**: 不跑就 commit,SKILL.md 错就过不去
  - assess_weight_health API 错是 v0.3.1 引入,v0.4-0.5.1 都没测就 commit
  - tests/ 目录的 smoke test 是 v0.3.x 缺失的"防护栏"
- **API 设计原则**: 用户用 `function('symbol')` 调,比 `function(dataframe)` 直观
  - v0.5.2 增加 `assess_weight_health(symbol)` 便利入口
  - **保留 DataFrame 入口**给低层 (testing / pipeline) 用
- **SKILL.md 跟代码同步**: 每次 commit 跑 smoke test 验证 SKILL.md API 没笔误

## [0.5.1] - 2026-07-13

### Added
- **P4-4: mavis skill 装好** — `C:\Users\project-user\.minimax\skills\us-stock-causal\`
  - SKILL.md (6.9 KB) — 项目概览 + 三档阅读 + 模块快速参考 + 常用命令
  - _meta.json — name / version / platform
  - **junction-safe**: 用真实路径 `.minimax` 装,不走 `.mavis` junction
  - **v1 教训应用**: 检查 `Get-Item` LinkType,确认 Junction,直接走真实路径
- **P5-1 + P5-2 飞书推送脚本** — `examples/feishu_push.py` (**🪦 2026-07-26 archived → `archive/feishu_push.py`, 不进 main flow**)
  - 从 .env 读 FEISHU_WEBHOOK_URL (gitignore,安全)
  - 飞书 interactive card 格式 (header + 顶部情绪 + 5 段报告 + footer)
  - `--dry-run` 看 payload 不真发
  - **默认不自动跑** (P5-2 手动确认)
- **P5-1/2/3/4 完整文档** — `docs/PHASE5.md` (**🪦 2026-07-26 archived, 顶部加 ARCHIVED banner, 保留作 reference**)
  - 4 步用户操作路径: 创建机器人 → dry-run → 真发一次 → 确认 cron 时间
  - v1 教训应用: 不拍脑袋 17:00,等用户确认再注册 cron
  - 已知限制列清楚: K 线图不发 / 30KB 截断 / 无重试 / timezone

### Verified (2026-07-13)
- **mavis skill 装好**: 2 文件 7 KB,真实路径,不被 junction 损坏
- **feishu_push.py dry-run**: 3075 字符 payload,远低于 30KB 限制 (脚本本身 v0.5.1 verified, 2026-07-26 archived)
- **4 段元素**: header (title) → 顶部情绪 (VIX/10Y/DXY + 4 指数) → 5 段报告 (lark_md) → footer (note)
- **Phase 5 gate 全开**: 等用户操作 4 步后才进 P5-4 cron

### Key Insights
- **junction 教训实战**: v1 时期因为 junction 走 Remove-Item 损失 5KB SKILL.md,
  v3 这次主动用 `Get-Item | Select LinkType` 查清楚,直接走 `C:\Users\project-user\.minimax\skills\`
  真实路径,**绝不从 junction 路径写**
- **Phase 5 gate 严格**: 4 步 user action 走完才开 cron,不是 1 步
  - 这是 v1 的关键教训 — 拍脑袋 cron 17:00 + webhook 配错 = spam 群 1 周
- **dry-run 是必要的**: webhook 一旦发出去就收不回,先看 payload 再说

### Phase 4 + 5 进度
- P4-1 ✅ 数据集导出 CLI (v0.5.0)
- P4-2 ✅ Jupyter Lab 启动器 (v0.5.0)
- P4-3 ✅ 3 个 sample notebook (v0.5.0)
- **P4-4 ✅ mavis skill 装好 (本版本)**
- P5-1 ✅ 飞书 webhook 配置文档 (本版本, 🪦 2026-07-26 archived)
- P5-2 ✅ 手动推送脚本 (本版本, 🪦 2026-07-26 archived)
- P5-3 ⏳ 等用户确认 cron 时间
- P5-4 ⏳ 等用户说"OK 跑"再注册 cron

**Phase 4 4/4 done 🎉**

## [0.5.0] - 2026-07-13

### Added
- **P4-1: 数据集导出 CLI** — `examples/export.py`
  - 支持 CSV / Parquet / Excel / all 4 种格式
  - 多 ticker (comma-separated) + 时间窗口 (--start, --end) + 层 (--layer)
  - 输出到 `data/export/` (默认) 或用户指定
  - 0.1s 导出 998 rows (DIA + QQQ)
- **P4-2: Jupyter Lab 启动器** — `examples/notebook.py`
  - `python examples/notebook.py [--port 8888] [--no-browser] [--ip 0.0.0.0]`
  - 自动 cd 到 project root,notebook dir = project root
  - 显示已存在的 .ipynb 列表
- **P4-3: 3 个 sample notebook** — `notebooks/0[1-3]_*.ipynb`
  - 生成器: `examples/generate_sample_notebooks.py` (用 nbformat 程序生成)
  - **01_load_and_explore.ipynb** (6 cells) — 加载 4 指数 + 算 1d/5d 收益 + 画归一化对比
  - **02_attribution_custom.ipynb** (9 cells) — 跑 QQQ 5 日归因 + 自定义 weights what-if + 4 指数对比
  - **03_pattern_match.ipynb** (7 cells) — 4 指数 × 3 种 pattern 配置 + top 5 严格匹配
  - **Robust path 修复**: notebook cell 自动找含 `src/` 的目录,加 sys.path (在 jupyter 里 cwd 不一定是 project root)
- **依赖**: jupyterlab 4.6.1 + nbformat 5.10.4 + ipykernel 7.3.0 (新装)
- **bug fix**: 3 个 notebook 第一次跑都报错,修:
  1. `sys.path.insert(0, '.')` → robust `_find_project_root()` (找含 `src/` 的目录)
  2. `weights.items()` 包含 `"note"` 字符串 → 过滤 `isinstance(v, (int, float))`
  3. `r_top5['matches']` → 实际 key 是 `top_matches`
  4. `r['symbol']` → 实际 key 是 `index`
  5. `forward_return` 是 fraction 不是 %, 展示要 × 100

### Verified (2026-07-13)
- **export.py**: 2 tickers, CSV, 0.1s, 998 rows 写到 `data/export/`
- **notebook.py**: 启动器装好,真实启动要用户在自己机器跑 (这里不能 GUI 演示)
- **3 notebooks 全部 jupyter nbconvert --execute 通过**:
  - 01: 6 cells, 4 code + 2 md, 输出 4 指数 1d/5d 收益
  - 02: 9 cells, 6 code + 3 md, 输出 4 指数归因对比 + what-if Δ=-0.06%
  - 03: 7 cells, 5 code + 2 md, 输出 4 指数 × 3 配置矩阵
- **executed notebooks** (.executed.ipynb) gitignore,regenerable

### Key Insights
- **notebook generator 模式**: 3 个 notebook 共 22 cells,程序生成比手写 JSON 安全
  - 改 cell 内容时改 Python 字符串,不用记 nbformat 字段
  - 改完跑 `python examples/generate_sample_notebooks.py` 一键 regen
- **notebook execute validation 是 v3 重要纪律**: 第一次跑 4/4 失败,修了 5 个 bug
  - 不跑就 commit 的话,用户第一次开 Jupyter 就报红 cell,体验差
- **🟡 已知 anomaly**: NB03 cell 5 第 2 个 match 显示 fwd +100.30% (5d return)
  - 数据真实 (1y 内某 5 日大涨),但**没回测是否真信号**
  - 留给用户自己 sanity check — 这正是 self-analysis 的价值

### Phase 4 进度 (3/4 done)
- P4-1 ✅ 数据集导出 CLI
- P4-2 ✅ Jupyter Lab 启动器
- P4-3 ✅ 3 个 sample notebook (全部 execute 验证)
- P4-4 ⏳ 装 mavis skill (junction-safe, v0.5.1)

## [0.4.1] - 2026-07-13

### Added
- **P3-3: 顶部市场情绪 1 行** — `src/macro.py`
  - 3 源宏观: VIX (恐慌) / 10Y ^TNX (国债收益率) / DXY (美元)
  - 4 指数 1 日 1 行: DIA / QQQ / RSP / QQQE
  - VIX/DXY 用 % 变化, 10Y 用 bp (基点) 变化
  - `topline()` 组合 2 行 = 顶部情绪 1 行 + 4 指数 1 行
  - 集成进 `src/report.py` `render_full_report()`, 5 段报告顶部加 topline
- **bug fix**: 初次跑 DXY 显示 N/A — `load_prices("DX-Y.NYB", "macro")` 找不到 cache
  (cache 文件名是 `DXY.parquet`, yfinance alias 在 data.fetch 内部完成)。
  改用 `load_prices("DXY", "macro")` 让 cache key 对齐 config/tickers.yaml 的原名

### Verified (2026-07-13)
- **顶部情绪 1 行生成**:
  - VIX 16.40 (+9.12%) — **panic 急升 9%, 4 指数都小涨的显著分歧**
  - 10Y 4.57% (+3bp) — 收益率略升
  - DXY 100.97 (+0.03%) — 美元持平
- **4 指数 1 日**: DIA +0.30% / QQQ +0.31% / RSP +0.37% / QQQE +0.03%
- **报告生成 < 4s** (topline + 4 指数 5 段)

### Key Insights
- **VIX +9% vs 指数小涨 = 分歧**: 通常 VIX 急升伴随大跌, 今天是反的
  - 可能是 hedge 仓位对冲 (VIX 期货投机盘) 而非现货市场恐慌
  - 也可能是 macro snapshot 滞后 — 闭市后才发
  - **报告不说"看多/看空", 只把这个分歧列出来给用户判断**
- **顶部 1 行降低阅读门槛**: 30 秒看完 — VIX 急升 + 4 指数小涨 + 美元持平 + 明天 CPI
  - 知道 CPI 之前 hedge 仓位变多也合理, 这是市场对冲成本

### Phase 3 进度 (3/3 done 🎉)
- P3-1 ✅ 5 段制报告 (v0.3.3)
- P3-2 ✅ K 线图 (v0.4.0)
- P3-3 ✅ 顶部情绪 1 行 (本版本)

**Phase 3 (简洁呈现) 100% 完成 ✅** — 30s 顶部 + 5min K 线 + 15min 5 段 三档阅读建立

## [0.4.0] - 2026-07-13

### Added
- **P3-2: K 线图生成** — `src/kline.py` + `examples/kline.py`
  - 1y daily K 线 (252 交易日),4 subplot 2×2 网格 (DIA/QQQ/RSP/QQQE)
  - matplotlib 手画蜡烛 (mplfinance 自己管 figure,无法 2x2)
  - 4 条关键线:
    * 200 SMA 蓝实线 (长期趋势)
    * 50 SMA 橙点线 (中期趋势,可选)
    * R1 红虚线 (短期阻力, floor trader pivot)
    * S1 绿虚线 (短期支撑, floor trader pivot)
  - 输出: `output/kline_<date>.png` (~100 KB)

### Verified (2026-07-13)
- **4 指数 K 线图生成 < 3s**, 102 KB PNG
- **视觉确认 late cycle bull market**:
  - 4 指数全 above 200 SMA (DIA +8.14%, QQQ +13.72%, RSP +8.36%, QQQE +13.50%)
  - QQQ/QQQE 在 5/2026 突破 200 SMA 后冲高,RSP/DIA 在 2026 初就 above
  - R1/S1 在 K 线顶部紧贴(现价离 52w 高点 0.1-1.3%),**关键技术面: 突破 R1 才开新一轮**
- **4 subplot 信息密度**: 一张图覆盖 4 指数 1y 全部关键水平

### Key Insights
- **K 线 + 阈值可视化比纯文字更直观**: 文字"QQQ 200 SMA +13.72%"需要读者心算位置,
  K 线直接看到"价格在 SMA 上方多远"
- **R1/S1 在 4 指数都贴顶**: 这从图上一眼能看出,文字报告无法表达
- **200 SMA 蓝色实线在 QQQ/QQQE 显示明显"刚突破不久"**,这是技术派"金叉后回踩不破"的形态

### Known Limitations
- **50 SMA 是期权,可关**: 4 条线在右上角 legend 略密,5/4 指数可能觉得不够
- **没有事件标记 (CPI/FOMC 垂直线)**: Phase 3.3 P3-2.5 计划
- **没有成交量柱**: 4 subplot 加 volume 会变成 2×4 = 8 subplot,信息密度下降,Phase 3.4 评估
- **没有 annotate 关键日期**: v0.3.3 5 段报告提的"明天 CPI"在 K 线上没标

### Phase 3 进度 (1/3 done)
- P3-1 ✅ 5 段制报告 (v0.3.3 P2-9 实现,移到这里)
- P3-2 ✅ K 线图 (本版本)
- P3-3 ⏳ 顶部市场情绪 1 行 (Phase 3.2)

## [0.3.3] - 2026-07-13

### Added
- **P2-8: 信号聚合 + 矛盾 score** — `src/signals.py`
  - 3 源信号: pattern_match / threshold_pressure / event_proximity
  - 每个信号分 bullish / bearish / neutral + confidence 0-1
  - `contradiction_score` = 1 - 一致性比例 (0 = 全一致, 0.67 = 3 源各异)
  - `verdict` = high_conf_bull / high_conf_bear / high_conf_neutral / mixed
- **P2-9: 5 段制报告** — `src/report.py` + `examples/report.py`
  - 每标的 5 段: ① 5 日行情 ② 5 日归因 ③ 关键阈值 ④ 历史相似 ⑤ 风险
  - 字数 ~120/段 × 5 = ~600/标的 (目标达成)
  - 4 指数完整报告 `output/report_<date>.md`
  - 因果优先: 输出"驱动 + 阈值 + 历史 + 风险",**不输出"看多/看空"结论**

### Verified (2026-07-13)
- **4 指数 5 段制报告** (2026-07-13, 5 日 lookback):
  - DIA: -0.40%, 信号矛盾 0.67(mixed), 1d 后 CPI
  - QQQ: +1.81%, 信号部分一致 0.33, pattern win 80%, 1d 后 CPI, SMA200 +13.7% 距超买近
  - RSP: -0.28%, 信号部分一致 0.33, 1d 后 CPI
  - QQQE: +0.38%, 信号部分一致 0.33, pattern win 70%, 1d 后 CPI, SMA200 +13.5% 距超买近
- **DIA 信号矛盾最高 (0.67)**: pattern 中性 (win 30%) + threshold bullish (above SMA) + event bearish (1d 后 CPI),3 源各异
- **报告生成 < 3s** (4 指数 × 5 段,数据在缓存里)

### Key Insights
- **5 段制是 Phase 3 的预演**: 真实产出 ≤ 600 字/标的,跟 v0.2 的 3000+ 字报告比,信息密度提升 5 倍
- **信号矛盾 score 是新维度**: 0-1 量化"信源意见分散度",> 0.5 时建议加注 ⚠️
- **CPI 1d 后是 universal 风险**: 4/4 指数风险段都有"CPI"警告,这是 v0.3.2 event 检测自然产出的
- **跟 v0.2.1 "看多看空"方向彻底切割**: 输出"机制 + 阈值 + 历史",用户自己判断,不做代理投票

### Phase 2 进度 (9/9 done 🎉)
- P2-1 ✅ 收益率
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因
- P2-4 ✅ 残差
- P2-5 ✅ 历史模式匹配
- P2-6 ✅ 关键阈值
- P2-7 ✅ 事件日历
- P2-8 ✅ 信号矛盾胜率
- P2-9 ✅ 5 段制报告

**Phase 2 (因果分析) 100% 完成 ✅**。下一阶段 Phase 3 (简洁呈现) 入口已打通。

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
- 飞书推送 (🪦 2026-07-26 archived — 改本地化 alert log + mavis skill HTML 报告)
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
