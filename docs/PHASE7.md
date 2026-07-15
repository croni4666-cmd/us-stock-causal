# Phase 7 — 真实 sector weights (v0.7.x, P6 完成后启动)

> **v0.6.7 P6-3 诊断结论**: 5 日累计归因残差 (DIA -1.05% / QQQE -0.71% / RSP -0.44%) 根因是
> **`config/sector_weights.json` 用的 2026-Q2 近似值与实际 weekly drift 漂移**。
> 改归因窗口 (5d → 20d) 没用 — 5d 残差是 sector weight 短期漂移,不是窗口问题。
>
> **Why Phase 7**: 真修必须拉"实时" sector weights。

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

## Phase 7 进度 (重设计后)

| ID | Item | Status | Note |
|---|---|---|---|
| P7-1 | 装 openbb-etf provider | ✅ done | openbb-etf 1.6.2 装好, 但 sectors/holdings endpoint 受限 |
| P7-2 | 拉 SPY/QQQ 真实 sector weights | ❌ blocked | A 路径死, FMP 受限 + yfinance 限流 |
| P7-3 | DIA/QQQ/QQQE 派生 weights | ⏳ proposed | 依赖 P7-2 |
| P7-4 | cache 1d (sector_weights_live_YYYY-MM-DD.json) | ⏳ proposed | 依赖 P7-2 |
| P7-5 | 残差回归测试 (5d 目标 < 0.3%) | ⏳ proposed | 依赖 P7-2 |
| P7-6 (新) | yfinance 限流检测 + 优雅降级 | ⏳ proposed | Phase 1 全管道风险, 提前到 Phase 7 修 |

**3 选 1 (替代 A)**:
- **C**: hardcode SPY 500 + QQQ 100 sector mapping (0 钱, 1-2h 一次投入, 季度手动维护)
- **D**: FMP 付费订阅 $14/month Starter (信用卡 1 次, 含 etf.sectors + holdings, 真实时)
- **E**: 跳 Phase 7, 进 Phase 8 + 修 yfinance 限流 (P7-6 提前到 Phase 8, 接受 5d 残差 0.4-1.1% 现状)

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
