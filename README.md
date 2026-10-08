# us-stock-causal

> **一手数据 + 因果分析** — 看涨跌的"为什么",不是"看多看空"投票
> **v0.9.5** — 当前包含资产专用归因、离线图表与登记命题审查。2026-08的性能和测试数字仅是历史记录；当前结果以实际验证为准。

## 这是什么

**us-stock-causal** 是一个本地化的美股因果分析工具, 47 ticker (6 macro + 4 指数 + 11 行业 + 14 商品期货 + 12 现货 ETF) 候选 DAG 建模（条件关联、模型情景与实验反事实；现实因果效应未认证）。

可用一个命令生成5段制分析报告、候选模型结果、异常告警与性能dashboard；运行时间取决于数据与环境：

- **过去 5 天为什么这么走** (Phase 2 归因分解: 11 行业 ETF 加权 + sector weights)
- **接下来 3 个关键阈值在哪** (Phase 2 支撑 / 阻力 / 财报事件)
- **历史相似模式后续如何** (Phase 2 模式匹配 + 5d fwd 收益)
- **候选模型情景**（Phase 9条件关联与实验反事实，不能直接解释真实涨跌原因）
- **有什么异常** (Phase 8 5 类 check: stale / residual / vix_spike / ticker_fail / parquet_corrupt)

数据通过yfinance获取，模型本地运行；定时任务需自行安装，并检查数据缺口和实际运行日志。

## 历史状态（v0.8.5，2026-08-08）

| 维度 | 数值 |
|---|---|
| **Ticker** | 47 个 (设计 49, 实际 47 可拉, 2 delisted: BAL cotton 2018 / JO coffee 2018) |
| **DAG 节点** | 47 节点 172 边, acyclic (networkx 验证) |
| **候选模型** | 行业归因 / 条件关联情景 (causal_query) / 实验模型反事实 (counterfactual_query)；统计结果不认证现实因果效应 |
| **daily cron 性能** | **9.0s** (V1.0 < 10s 目标达成) |
| **smoke test** | **80/80 pass** (~180s) |
| **v1.0 路线图** | 5/8 子版本 done (提前 22 天) |

## 5 分钟跑通 (本地)

```bash
# 1. 装依赖 (代理 10808, ~3 min)
pip install -r requirements-lock.txt
pip install -e .

# 2. 拉数据 (47 ticker 全, ~2 min, 含 14 期货 + 12 ETF)
python examples/fetch_all.py

# 3. 跑 daily report（日期仅为历史示例，按实际缓存截至日修改）
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
cd "<path-to-repo>\us-stock-causal"
scripts\install_task.cmd          :: 注册本机时区17:00 daily；按纽约实际收盘及夏令时另行配置
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
| 工作区路线图 | 属于本机工作区，不随仓库分发；项目路线见V1.0-ROADMAP.md |

## 核心功能 (Phase 0-9)

| Phase | 内容 | 关键交付 |
|---|---|---|
| 0. Setup | OpenBB → yfinance 切换, Clash 代理 | `data.fetch()` |
| 1. 数据层 | 47 ticker 全 DAG, parquet 增量缓存 | `examples/fetch_all.py` + `data/raw/` |
| 2. 归因 + 模式 + 阈值 | OLS + sector weights + pattern matching | `src/attribution.py` + `src/patterns.py` |
| 3. 简洁呈现 | 5 段制报告 + 顶部情绪 | `src/report.py` + `src/report_html.py` |
| 4. 自分析 | export + Jupyter | `examples/notebook.py` + `notebooks/` |
| 5. 调度 | Windows Task Scheduler 17:00 daily (P5-3) | `scripts/install_task.cmd` |
| 6. KPI | 5d / 20d 残差回归 (P7-5 baseline) | `src/residual_regression.py` |
| 7. 异常检测 | 5 类 check (stale / residual / vix_spike / ticker_fail / parquet_corrupt) | `src/checks/` + `src/alert_logger.py` |
| 8. 告警 | Windows toast (plyer) | `src/notify.py` |
| 9. **候选因果模型** | DoWhy + EconML + gcm.InvertibleSCM；DAG默认低可信，输出条件关联与模型情景 | `src/causal.py` |

## 设计原则 (vs v1/v2)

| 维度 | v1/v2 (us-stock-daily) | v3 (本项目) |
|---|---|---|
| **底层** | 自写 fetch + Clash hack | yfinance 直接拉 (跟 OpenBB 一样的后端, 但更轻) |
| **数据** | 5 个股 | **47 ticker (6 macro + 4 指数 + 11 行业 + 14 期货 + 12 ETF)** |
| **分析** | 投票出"看多/看空" | **归因 + 模式匹配 + 阈值 + 候选图条件关联（因果效应未建立）** |
| **输出** | 311 行 7 张表 | **5 段制报告 + 因果机制段 + 异常告警 + 性能 dashboard** |
| **维护** | 全自己 | yfinance / DoWhy / EconML 社区 (月更) |
| **本地化** | 飞书 1-2 min 推送 (需联网 + 收 push) | **本地化 (2026-07-26 archived 飞书) + Windows toast 弹窗** |

## 为什么换方向

v1/v2 (us-stock-daily) 失败原因: 输出了"看多/看空"投票结论, 跟大 V 喊单没区别。

用户原话: **"看多看空这种评论性内容你只要混迹对应股市的社交圈子都能得到消息。假如不掌控数据、没有一手信息和模型,我还不如直接去看研报。"**

v3 方向: **掌控数据（yfinance）+ 可检查的候选模型 + 透明输出（归因、模型情景与风险）**. 不输出"看多/看空"结论, 只输出"驱动因子 + 阈值 + 历史 + 风险".

## 约束 (hobbyist ceiling)

- **本地存储**: ~90 GB free (C/E/F/G, D 移动硬盘不计)
- **不花一分钱**: 免费 tier (yfinance, DoWhy, EconML, gcm)
- **单人维护**: 借社区, 不自己 fork 大库
- **优雅降级**: 单 ticker 失败不阻塞, yfinance 5xx 走 tenacity retry 3 重 (P8-5)
- **30天稳定期**：路线图目标，实际完成情况需查当前日志；2026-08的运行天数不代表当前状态。

## License

[MIT License](./LICENSE) — 自由使用 / 修改 / 商业, 保留 copyright 即可.

- **个人维护**: 不接受 PR, fork 自用 OK
- **数据源**: yfinance (Yahoo Finance 免费) + GDELT (公开) + SEC EDGAR (公开) + FRED (公开,需 key)
- **第三方代码**: `tools/sec_fetch.py` 复制自 mavis `sec-filings-fetch` skill (MIT, 跨 project 复用)
- **DAG 设计**: 借鉴 Innei/kansoku (AGPL-3.0, 灵感来源, 非代码复用)

## 历史版本

- **v0.8.5** (2026-08-08): 测试 80+ (V1.0 路线图 "测试 80+" 达成, 66 → 80 +14 tests)
- v0.8.0 (2026-08-08): P9-1.7 batch 5 (DAG 35 → 47 节点, 加 12 现货 ETF, 12 ETF→期货 配对边)
- v0.7.5 (2026-08-08): 性能 < 10s (Pydot cache + report LRU cache, daily cron 14s → 8.6s)
- v0.7.0 (2026-08-08): P9-1.7 batch 4 (DAG 21 → 35 节点, 加 14 商品期货, 26 commodity→industry 边)
- v0.6.9m (2026-08-07): P8-5 错误恢复 (tenacity 统一 retry 抽象)
- 详见 `CHANGELOG.md` (按 (date, base, -suffix_rank) 排序的 44 段)

## 资产专用归因入口

新增官方 QQQ / IEF / TLT 持仓、GLD 历史档案和离线资产分析。
使用方法及模型边界见 [资产专用分析](docs/asset-specific-attribution.md)，
详细路线见 [设计文档](docs/superpowers/specs/2026-10-03-asset-specific-attribution-design.md)。
可重复采集行情、分红拆股与每日官方快照见 [数据积累流程](docs/asset-data-pipeline.md)。
IEF/TLT官方多期限曲线与实验现金流模型见 [美债曲线模型](docs/treasury-curve-model.md)。

## DAG可信度与正向证据

DAG、SCM和CATE默认只是候选假设及条件模型结果。统计显著、PC重叠或扰动稳定不升级因果可信度。
新增离线登记检验与平衡支持评估，保留反例、事后探索、重复与无法检验项；不输出命题成立概率。
协议、边界、真实历史示例及使用方法见 [低可信DAG与可证伪命题](docs/dag-hypothesis-review.md)。

行情图已移除联储等宏观事件叠线，收盘价、单位和报价日期独立展示；边界见 [图表价格标识](docs/chart-price-readability.md)。
生成图片后另存50/100/200日均线穿越检查，区分当前位置、最新收盘穿越及最近5个可用日线记录；结果放在同名 `.ma-review.md` / `.ma-review.json`，图片不新增叠层。
现另告知历史最后上穿/下穿日期、最近一次方向及搜索范围。用 `python -m examples.chart --list-profiles` 选择纯价格、均线检查、多资产对比或完整技术图；可选项及可重复流程记录于 [项目skill](SKILL.md) 和 [profile参考](references/chart-profiles.md)。
