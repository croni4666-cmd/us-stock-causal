# Phase 7 — 真实 sector weights (v0.7.x, P6 完成后启动)

> **v0.6.7 P6-3 诊断结论**: 5 日累计归因残差 (DIA -1.05% / QQQE -0.71% / RSP -0.44%) 根因是
> **`config/sector_weights.json` 用的 2026-Q2 近似值与实际 weekly drift 漂移**。
> 改归因窗口 (5d → 20d) 没用 — 5d 残差是 sector weight 短期漂移,不是窗口问题。
>
> **Why Phase 7**: 真修必须拉"实时" sector weights。

> **🎯 v0.6.8e 更新 (2026-07-20)**: C 路径落地! P7-2 状态 `blocked` → `done`。
> 详见底部 update log + `CHANGELOG.md` v0.6.8e 段。

---

## 🪦 v0.6.8b hotfix (2026-07-16): A 路径错, Phase 7 重设计

**Author 错在哪**: P7-1 research 只验 "openbb-etf 能不能装", **没验 "endpoint 真跑得通"**。
写 PHASE7.md 假设 FMP free tier 含 `etf.sectors`, **实际是付费墙后**。
User 配了 key 才暴露 — 浪费 5 分钟。

**A 路径实际测试结果** (2026-07-16, 配完 FMP key `pq3neDC...` 后):

| Endpoint | 期望 | 实际 |
|---|---|---|
| `obb.etf.sectors("SPY")` | free tier OK | ❌ **402 Restricted Endpoint** |
| `obb.etf.holdings("SPY")` | free tier OK | ❌ **402 Restricted Endpoint** |
| `obb.etf.info("SPY")` | free tier OK | ❌ **402 Restricted Endpoint** |
| `obb.equity.profile("AAPL")` | free tier OK | ✅ **OK** (单只 sector/industry 字段可拿) |
| `obb.equity.price.historical("AAPL")` | free tier OK | ✅ OK |
| `yfinance.Ticker("SPY").funds_data` | yfinance 直拉 | ❌ **YFRateLimitError** (Yahoo 2026 限流) |
| `yfinance.Ticker("AAPL").info` | yfinance 直拉 | ❌ **YFRateLimitError** (单只 info 都限流) |

**新发现 — yfinance 限流 2026 持续**: `ticker.history` / `ticker.info` / `ticker.funds` 全部
YFRateLimitError。**Phase 1 整个数据管道潜在风险** — `data/raw/*.parquet` cache miss 时
拉新数据会失败, daily cron 增量也挂。

**教训 (写进未来 research discipline)**:
- "装" 不等于 "能用", research 必须真跑 endpoint
- 3rd-party API: 测 "register + use", 别只测 "import"
- FMP / yfinance / 任何 SaaS: **先 free tier 跑通 1 个真实 query** 再 commit guide

---

## Phase 7 进度 (重设计后, v0.6.8e C 路径落地后)

| ID | Item | Status | Note |
|---|---|---|---|
| P7-1 | 装 openbb-etf provider | ✅ done | openbb-etf 1.6.2 装好, 但 sectors/holdings endpoint 受限 |
| P7-2 | 拉 SPY/QQQ 真实 sector weights | ✅ **done (C 路径)** | v0.6.8e: SPY N-30D 38 industry groups → 11 sector 真值, DIA/QQQ/QQQE/RSP 估算 |
| P7-3 | DIA/QQQ/QQQE 派生 weights | ⏳ proposed | 依赖 P7-2 (v0.6.8e), 季度手动更新 |
| P7-4 | cache 1d (sector_weights_live_YYYY-MM-DD.json) | ⏳ proposed | 依赖 P7-2; C 路径先直接改 sector_weights.json, 暂无 cache 需求 |
| P7-5 | 残差回归测试 (5d 目标 < 0.3%) | 🟡 partial | v0.6.8e 已对比 4 指数 5d/20d, 5d 目标未达成 (持平), 20d 改善 8% |
| P7-6 (新) | yfinance 限流检测 + 优雅降级 | ⏳ proposed | Phase 1 全管道风险, 推到 Phase 8 修 |

**决策记录 (v0.6.8b hotfix → v0.6.8e)**:
- **C 路径** (选): hardcode SPY 真 sector weights (0 钱, 1-2h 一次投入, 季度手动维护)
- **D 路径** (不选): FMP 付费订阅 $14/month Starter — 跟 user global "hobbyist ceiling" rule 冲突
- **E 路径** (不选): 跳 Phase 7 进 Phase 8 — C 路径已通, 没必要

**C 路径产出 (v0.6.8e)**:
- `config/sector_weights.json` 4 指数 × 11 sector 真值 (sum ~1.0)
- `_meta.source` 标 SPY N-30D table 22 (2026-05-29) 38 industry groups 推 11 sector
- `_meta.warning` 标 DIA/QQQE/RSP 是估算 (price-weighted / 等权)
- `_meta.update_cadence` 标 quarterly (next: 2026-10)
- 31/31 smoke test pass, 新加 `test_sector_weights_v068e_real_values`

**残差对比 (写进 CHANGELOG)**:
- QQQ 5d: +0.17% → **+0.01%** 🎉 (基本 0 残差)
- RSP 20d: +0.95% → **+0.61%** (改善 0.34pp)
- 20d avg: +1.15% → +1.06% (改善 8%)
- 5d avg: 持平 (符合 v0.6.7 P6-3 诊断: 5d 残差是 sector weight 短期漂移, sector 真值改不了)

**🪦 discipline 写进未来诊断** (v0.6.8e 新发现):
- "5d 残差 vs 20d 残差" 是诊断 sector weight 准不准的天然试金石
- 5d 残差为负 / 20d 残差转正 = sector weight 短期偏高 (rebalance / ETF flow)
- 真修 = 改 sector weights, 跟归因窗口解耦 — 别再试改窗口
- 季度重拉 SPY N-30D 即可更新 (DIA 30 只 / Q 100 只手动 sector profile 派生是 P7-3 的活)

---

## 🛠️ P7-2 ~~注册 FMP + 配 key~~ (历史, 不再推荐)

> 这 4 步原打算走 A 路径, 实测失败 (见顶部 hotfix 段)。user 拍板 C/D/E 后改写。
> 详细步骤存档: 见 git log `d868eeb` v0.6.8a commit (PHASE7.md 旧版)

FMP key `pq3neDC...` 已配, 仍可作:
- Phase 8 alert: 用 `equity.profile` 拉单只 sector 做 sanity check (免费, 不受 402)
- P7-6 限流检测: 用 FMP key 当 fallback, yfinance 限流时切 FMP 单点拉

---

## 📜 Update log

| Date | Change |
|---|---|
| 2026-07-15 | Phase 7 初始化 (P6 完成后启动)。user 选 A 路径 (FMP free key), 写 4 步指南。 |
| 2026-07-15 | commit `d868eeb` v0.6.8a: PHASE7.md 4 步指南。 |
| 2026-07-16 | **v0.6.8b hotfix (A 路径错)**: 配完 FMP key 后实测 7 个 endpoint, **5/7 受限** (FMP 402 + yfinance 限流)。 |
| | - FMP key `pq3neDC...` 仍配 (user 5 分钟投入不浪费, Phase 8 alert + P7-6 fallback 可能用) |
| | - Phase 7 重设计: 3 选项 C/D/E 等 user 拍板 |
| | - 新发现: yfinance 2026 持续限流, Phase 1 整个数据管道潜在风险 → 加 P7-6 (限流检测 + 优雅降级) |
| | - 教训写进顶部 hotfix 段: "装" ≠ "能用", research 必须真跑 endpoint, 别只测 import |
| 2026-07-20 | **v0.6.8c (P-event-1)**: 借鉴 Kansoku gdelt 范式, `src/events_gdelt.py` done, 3 个 bug 真测发现 |
| 2026-07-20 | **v0.6.8d (P-event-2 Stage 2.1)**: 借鉴 Kansoku sec-edgar 范式, `src/etf_holdings.py` done, **🪦 ETF filing 习惯发现** (NPORT-P / N-30D / N-CSR) |
| 2026-07-20 | **🪦 Stage 2.2.1 fail-fast**: N-30D 1.16MB 35 tables, **不含** "11 GICS sector × %" 单表, 走 C 路径 fallback |
| 2026-07-20 | **v0.6.8e (P7-2 C 路径 done) 🎯**: user 拍 C 路径, SPY N-30D 38 industry groups → 11 sector 真值, `config/sector_weights.json` 重写 |
| | - QQQ 5d 残差 +0.17% → **+0.01%** 🎉, RSP 20d +0.95% → **+0.61%** |
| | - 20d avg 改善 8% (+1.15% → +1.06%), 5d 持平 (符合 v0.6.7 P6-3 诊断) |
| | - 31/31 smoke test pass, 新加 `test_sector_weights_v068e_real_values` |
| | - **新 discipline**: "5d 残差 vs 20d 残差" 是诊断 sector weight 准不准的天然试金石 |
| | - P7-2 status: `blocked` → `done (C 路径)` |
| | - 下一步: P7-3 (DIA 30 + Q 100 手动 sector profile 派生) + P7-6 (推 Phase 8 修) |
