# us-stock-causal

> **一手数据 + 因果分析** — 看涨跌的"为什么",不是"看多看空"投票
> **v0.8.5** (2026-08-08) — Phase 0-9 done, V1.0 路线图 5/8 子版本 done (测试 80/80, daily cron < 10s)

## 这是什么

**us-stock-causal** 是一个本地化的美股因果分析工具, 47 ticker (6 macro + 4 指数 + 11 行业 + 14 商品期货 + 12 现货 ETF) 全 DAG 因果建模 (Pearl 3 层因果阶梯: 关联 / 干预 / 反事实).

每天 1 个命令, 9 秒内出 5 段制分析报告 + 因果机制段 + 异常告警 + 性能 dashboard:

- **过去 5 天为什么这么走** (Phase 2 归因分解: 11 行业 ETF 加权 + sector weights)
- **接下来 3 个关键阈值在哪** (Phase 2 支撑 / 阻力 / 财报事件)
- **历史相似模式后续如何** (Phase 2 模式匹配 + 5d fwd 收益)
- **为什么涨跌** (Phase 9 Pearl 因果: do-calculus L2 + 反事实 L3)
- **有什么异常** (Phase 8 5 类 check: stale / residual / vix_spike / ticker_fail / parquet_corrupt)

数据自己拉 (yfinance), 模型自己跑, daily cron 0 人工干预.

## 当前状态 (v0.8.5)

| 维度 | 数值 |
|---|---|
| **Ticker** | 47 个 (设计 49, 实际 47 可拉, 2 delisted: BAL cotton 2018 / JO coffee 2018) |
| **DAG 节点** | 47 节点 172 边, acyclic (networkx 验证) |
| **Pearl 3 层** | L1 关联 (attribution) / L2 干预 (causal_query) / L3 反事实 (counterfactual_query) |
| **daily cron 性能** | **9.0s** (V1.0 < 10s 目标达成) |
| **smoke test** | **80/80 pass** (~180s) |
| **v1.0 路线图** | 5/8 子版本 done (提前 22 天) |

## 5 分钟跑通 (本地)

```bash
# 1. 装依赖 (代理 10808, ~3 min)
pip install -r requirements.txt --proxy http://127.0.0.1:10808

# 2. 拉数据 (47 ticker 全, ~2 min, 含 14 期货 + 12 ETF)
python examples/fetch_all.py

# 3. 跑 daily report (冷跑 ~9s, 含因果分析)
python examples/daily_report.py --date 2026-08-08 --skip-fetch
```

输出:
- `output/report_2026-08-08.md` (5 段制报告 + 因果机制段, ~3 KB)
- `output/dashboard_2026-08-08.html` (性能 dashboard, 含 4 指数)
- `output/alerts_2026-08-07.json` (异常告警累积, 5 类 check)
- `data/cache/alerts/alerts_<date>.json` (P8-6 告警 log)

## 5 分钟配 cron (Windows Task Scheduler 17:00 daily)

```cmd
:: admin cmd (右键 cmd.exe - 以管理员身份运行)
cd "G:\Minimax trade market\us-stock-causal"
scripts\install_task.cmd          :: 注册 17:00 daily (美股收盘后 1h)
```

验证: `schtasks /Query /TN "us-stock-causal-daily-report"`
日志: `output\logs\cron_YYYY-MM-DD.log`
卸载: `schtasks /Delete /TN "us-stock-causal-daily-report" /F`

## 文档导航

| 文档 | 内容 |
|---|---|
| [**USER_GUIDE.md**](./USER_GUIDE.md) | 怎么拉数据 / 改 DAG / 跑 daily / 解读输出 / FAQ (400 lines) |
| [**ARCHITECTURE.md**](./ARCHITECTURE.md) | 模块结构 / 数据流 / 缓存层 / 性能 / 扩展点 (300 lines) |
| [**V1.0-ROADMAP.md**](./V1.0-ROADMAP.md) | v1.0 路线图 6 conditions + 8 子版本 + 风险回退 (12 KB) |
| [**CHANGELOG.md**](./CHANGELOG.md) | 详细 commit log (按版本段排序) |
| [父 ROADMAP](../ROADMAP.md) | workspace 级 ROADMAP (多项目统一管理) |

## 核心功能 (Phase 0-9)

| Phase | 内容 | 关键交付 |
|---|---|---|
| 0. Setup | OpenBB → yfinance 切换, Clash 代理 | `data.fetch()` |
| 1. 数据层 | 47 ticker 全 DAG, parquet 增量缓存 | `examples/fetch_all.py` + `data/raw/` |
| 2. 归因 + 模式 + 阈值 | OLS + sector weights + pattern matching | `src/attribution.py` + `src/patterns.py` |
| 3. 简洁呈现 | 5 段制报告 + 顶部情绪 | `src/report.py` + `src/report_html.py` |
| 4. 自分析 | export + Jupyter | `examples/jupyter/` |
| 5. 调度 | Windows Task Scheduler 17:00 daily (P5-3) | `scripts/install_task.cmd` |
| 6. KPI | 5d / 20d 残差回归 (P7-5 baseline) | `src/residual_regression.py` |
| 7. 异常检测 | 5 类 check (stale / residual / vix_spike / ticker_fail / parquet_corrupt) | `src/checks/` + `src/alert_logger.py` |
| 8. 告警 | Windows toast (plyer) | `src/notify.py` |
| 9. **Pearl 因果** | DoWhy + EconML + gcm.InvertibleSCM, 3 层因果阶梯 | `src/causal.py` |

## 设计原则 (vs v1/v2)

| 维度 | v1/v2 (us-stock-daily) | v3 (本项目) |
|---|---|---|
| **底层** | 自写 fetch + Clash hack | yfinance 直接拉 (跟 OpenBB 一样的后端, 但更轻) |
| **数据** | 5 个股 | **47 ticker (6 macro + 4 指数 + 11 行业 + 14 期货 + 12 ETF)** |
| **分析** | 投票出"看多/看空" | **归因 + 模式匹配 + 阈值 + Pearl 因果 (L1/L2/L3)** |
| **输出** | 311 行 7 张表 | **5 段制报告 + 因果机制段 + 异常告警 + 性能 dashboard** |
| **维护** | 全自己 | yfinance / DoWhy / EconML 社区 (月更) |
| **本地化** | 飞书 1-2 min 推送 (需联网 + 收 push) | **本地化 (2026-07-26 archived 飞书) + Windows toast 弹窗** |

## 为什么换方向

v1/v2 (us-stock-daily) 失败原因: 输出了"看多/看空"投票结论, 跟大 V 喊单没区别。

用户原话: **"看多看空这种评论性内容你只要混迹对应股市的社交圈子都能得到消息。假如不掌控数据、没有一手信息和模型,我还不如直接去看研报。"**

v3 方向: **掌控数据 (47 ticker 一手 yfinance) + 一手模型 (Pearl 因果) + 透明输出 (5 段制 + 因果机制段)**. 不输出"看多/看空"结论, 只输出"驱动因子 + 阈值 + 历史 + 风险".

## 约束 (hobbyist ceiling)

- **本地存储**: ~90 GB free (C/E/F/G, D 移动硬盘不计)
- **不花一分钱**: 免费 tier (yfinance, DoWhy, EconML, gcm)
- **单人维护**: 借社区, 不自己 fork 大库
- **优雅降级**: 单 ticker 失败不阻塞, yfinance 5xx 走 tenacity retry 3 重 (P8-5)
- **30 天稳定期**: v1.0 must-have, 8/4 起 daily cron 已跑 5 天

## License

个人项目, 非开源.

## 版本

- **v0.8.5** (2026-08-08): 测试 80+ (V1.0 路线图 "测试 80+" 达成, 66 → 80 +14 tests)
- v0.8.0 (2026-08-08): P9-1.7 batch 5 (DAG 35 → 47 节点, 加 12 现货 ETF, 12 ETF→期货 配对边)
- v0.7.5 (2026-08-08): 性能 < 10s (Pydot cache + report LRU cache, daily cron 14s → 8.6s)
- v0.7.0 (2026-08-08): P9-1.7 batch 4 (DAG 21 → 35 节点, 加 14 商品期货, 26 commodity→industry 边)
- v0.6.9m (2026-08-07): P8-5 错误恢复 (tenacity 统一 retry 抽象)
- 详见 `CHANGELOG.md` (按 (date, base, -suffix_rank) 排序的 44 段)
