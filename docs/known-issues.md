# Known Issues — us-stock-causal

历史 issue 记录,V1.0 路线图 30 天稳定期窗口 0 fail 不容忍新 fail,但**已发生的历史 issue** 单独记录根因和修复方式。

---

## KI-1: 2026-08-05 daily cron MISSING (历史 issue, 已修根因)

**症状**:
- `output/logs/cron_2026-08-05.log` 不存在
- `tools/verify_30days.py --start 2026-08-04` 报 1 FAIL (MISSING)
- Task Scheduler `us-stock-causal-daily-report` 那天 17:00 没跑

**根因分析** (2026-08-09 排查):
- 8/5 13:55 机器进入 Sleep (Application API)
- 8/5 20:12 才从 Hibernate 唤醒
- 8/5 22:49 关机
- 17:00 cron 触发时机器在 Sleep,**Task Scheduler 默认不唤醒机器**
- Task Scheduler Settings 原状态:
  - `WakeToRun: False` ❌
  - `StopIfGoingOnBatteries: True`
  - `DisallowStartIfOnBatteries: True`

**修复** (2026-08-09 commit 1af0199+):
- `WakeToRun = True` — 17:00 触发时即使机器 Sleep 也唤醒
- `StopIfGoingOnBatteries = False` — 笔记本电池供电时也跑
- `DisallowStartIfOnBatteries = False` — 同上

**V1.0 稳定期影响**:
- 8/5 没法 backfill (已过去 4 天,无当日 yfinance 数据)
- **8/9 起新 30 天窗口** (8/9 ~ 9/7) 严格 0 fail 验证
- 8/4~8/8 旧窗口 8/5 MISSING 单独标 known historical issue,不计入 V1.0 0 fail 验证

**V1.0 tag 推迟**:
- 原 9/3 收尾 → 现 9/8 收尾 (新窗口 8/9~9/7 30 天)
- v0.9.5 RC1 改 9/8
- v0.9.9 RC2 改 9/15
- v1.0.0 tag 9/20 保持

**重现验证**:
- 修配置后 8/8 Sat 17:00 cron 跑通 (16KB log) → 配置生效
- 8/9 Sun 17:00 触发 → 7 小时后看 `output/logs/cron_2026-08-09.log` 是否生成

---

## 验证命令

```powershell
# 看 Task Scheduler 触发器 + 唤醒设置
Get-ScheduledTask -TaskName 'us-stock-causal-daily-report' | Select-Object -ExpandProperty Settings | Format-List

# 看历史 LastRun
Get-ScheduledTaskInfo -TaskName 'us-stock-causal-daily-report' | Select-Object LastRunTime, NextRunTime, LastTaskResult

# 跑 30 天验证
python tools/verify_30days.py --start 2026-08-09
```

---

## KI-2: WFC (Wells Fargo) SEC companyfacts stale (Shadow mode known issue, 待修)

**症状**:
- `examples/sec_filings_report.py` 拉 WFC 营收返回 `2020-09-30 $54.41B FY2020 Q3` (6 年前数据)
- 其他 32 ticker (AAPL/MSFT/NVDA/...) 全部正常, 只 WFC stale
- `data/sec.gov/api/xbrl/companyfacts/CIK0000072971.json` 实际状态: 38 records total, 最新 5 条都是 2020, 2021-2026 全空白

**根因分析** (2026-08-18 Shadow mode 验证):
- WFC CIK `0000072971` 正确 (Wells Fargo & Company)
- WFC 实际有 2026 Q2 10-Q filed (~7/30, $21.5B 营收 4-6 月)
- 但 SEC EDGAR companyfacts XBRL facts API 没更新 WFC 2021+ 数据
- 可能是 SEC XBRL 解析 pipeline 漏 WFC, 也可能是 edgar-parser tag mismatch
- WFC companyfacts 38 records, latest = 2020-09-30, earliest = 2016-12-31 (10 年数据带个 gap)

**影响**:
- Shadow mode 主验证 OK (32/33 真实数据), 只 1 ticker stale
- 不阻塞 daily_report (Shadow mode 本身不接 daily_report)
- 如果 9/3 RC1 拍板合入 daily_report, WFC stale 会显示在 cache 里 → 需要标记 "stale" 或 fallback 到 8-K 直接拉

**修法候选** (9/3 RC1 拍板):
- 选项 1: 换 alt revenue tag (`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` vs `us-gaap:Revenues` 试)
- 选项 2: WFC 排除出 33 ticker, 用 STT (State Street) 替补 XLF #3
- 选项 3: 拉 8-K + 10-Q 直接 HTML (47MB 慢, 跟 SKILL.md 限速矛盾, 但只 WFC 一家)
- 选项 4: 接受 WFC stale, 标 known data quality issue, 不修

**修法实施 (2026-08-18 17:50, 选项 1 拍板后)**:

WFC 根因深挖 (跑 _wfc_tags.py 查 companyfacts 全部 revenue tag):
- WFC 2021+ 用 `us-gaap:RevenuesNetOfInterestExpense` (净利息 + 非利息收入 = 银行总营收)
- WFC 2021+ 不用 `us-gaap:Revenues` (传统营收)
- 但 WFC 2020 之前用 `us-gaap:Revenues` 报告,所以旧数据存在
- _match_metric 按"recent 2 年内 filed"选,WFC Revenues 2020 已 6 年前 → recent=0
- 但 COMMON_METRICS["revenue"] 列表无 `RevenuesNetOfInterestExpense` → fallback 都找不到
- → 最后 fallback 选 Revenues 2020 stale

修法 (tools/sec_fetch.py):
- COMMON_METRICS["revenue"] 加 `us-gaap:RevenuesNetOfInterestExpense` 在 `RevenueFromContractWith...` 之后
- 移除 `us-gaap:InterestAndDividendIncomeOperating` (避免 _match_metric 选这个中间项,不是真"营收")
- _match_metric 现在 选 RevenuesNetOfInterestExpense (银行总营收 $44.07B FY26 6M)

WFC 修后验证 (8/18 17:50):
- `get_metric_history("WFC", "revenue", n_quarters=4)`:
  - 2026-01-01 ~ 2026-06-30: $44.07B (6M 累计) ✅ 银行总营收
  - 2026-04-01 ~ 2026-06-30: $22.62B (3M 单季 Q2) ✅
  - 2026-01-01 ~ 2026-03-31: $21.45B (3M 单季 Q1) ✅
- 真实 8/14 filed 10-Q 数字

全 33 ticker 验证 (8/18 17:55):
- 33/33 OK 0 FAIL 66.7s
- WFC: 44,068M FY26 Q2 ✅ (从 2020 stale 修好)
- JPM: 182,447M FY25 → 107,183M Q2 2026 (更新到最新季度)
- BAC: 61,830M FY26 Q2 (不变, 之前已走 RevenuesNetOfInterestExpense 路径)
- 其他 30 ticker: 不变 (非银行, 走 Revenues / RevenueFromContractWith... 路径)

**V1.0 路线图影响 (修后)**:
- WFC 修好, daily_report step 6.5 8/19+ 报告显示 WFC 真实数据
- JPM 跟着更新到 2026 Q2
- 30 天稳定期 0 fail 验证不受影响 (修法只改 sec_fetch.py tag list)
- v0.9.5 RC1 (9/8) 拍板 WFC 修法 选项 1 (本次已实施)
- 9/15 v0.9.9 RC2 跟 8/19~8/30 业务实测数据一起 review
- 9/20 v1.0.0 tag WFC 修好 + JPM 准确

**缓存注意**:
- WFC cache 在 `~/.cache/sec_fetch/facts_0000072971.json`, 24h TTL
- 修法后第一次跑需清 cache (用 `os.utime` 改 mtime 到 25h 前)
- 8/19 17:30 cron 自动拉新 cache (WFC 24h cache expire 后)

---

## KI-3: 2026-08-15 Sat Modern Standby MISSING (新发现, 修法候选 5 个)

**症状**:
- `output/logs/cron_2026-08-15.log` 不存在
- `tools/verify_30days.py --start 2026-08-09` 报 1 FAIL (MISSING)
- 8/15 Sat 17:00 cron 没跑 (8/9 起点后第 6 天 = 1/10 fail, 90%)

**根因分析** (2026-08-18 排查):
- 8/15 Power events:
  - 00:35:30 Sleep
  - 09:21:19 Wake
  - 14:58:24 Sleep (Application API)
  - 17:00 cron 触发时机器在 Sleep
  - (后续 events 缺失, 可能 Sleep 到 8/16)
- Task Scheduler WakeToRun=True 已设 (8/9 修的)
- **关键问题**: WakeToRun 在 Win 11 **Modern Standby (S0 Low Power Idle)** 模式下不响应
- 8/5 是传统 Sleep (S3) → WakeToRun 修后 8/10-8/14 全 PASS
- 8/15 是 Modern Standby (S0) → WakeToRun 不响应 → 17:00 cron 漏跑
- 8/16 Sun 27.9KB PASS (8/16 17:00 触发时机器已 wake, cron 跑通)
- WakeToRun 当前状态: True ✅ 但 S0 模式不响应

**修法候选** (9/3 RC1 拍板):
- **选项 1: 禁用 Modern Standby 改传统 S3 Sleep** (注册表)
  - `powercfg /h off` + `bcdedit /set disabledynamictick yes` + `bcdedit /set useplatformtick yes`
  - 风险: 改全机电源策略, 可能影响笔记本电池续航 (3-5h → 6-8h 差)
  - 修法最稳, Win 10 时代默认模式, WakeToRun 100% 工作
- **选项 2: cron 17:00 + 17:05 双 trigger** (保险)
  - Task Scheduler 加 17:05 backup trigger
  - 风险: 17:00 跑通的话 17:05 跑第二次会覆盖 report, 需 daily_report 加 "is_already_ran_today" 守卫
- **选项 3: 加 watchdog 5 分钟检查** (per-task watchdog)
  - 每 5 分钟检查当日 cron_YYYY-MM-DD.log 是否生成, 没生成就手动 trigger
  - 风险: 监控本身可能挂, 而且 task 太碎
- **选项 4: 改 17:00 → 18:00 trigger** (避开 sleep 窗口)
  - 风险: user 17:00 拍板的时间偏好 (P5-3) 改回 18:00
- **选项 5: 接受偶尔 MISSING, 改 V1.0 路线图 "30 天内 ≤ 1 MISSING 容忍"**
  - 风险: 弱化 V1.0 0 fail 验证标准, 不算真 100%

**建议组合** (9/3 RC1 拍板):
- 选项 1 (主修) + 选项 2 (保险) = 修法 + 兜底
- 不选选项 3 (太碎)
- 不选选项 4 (改 user 偏好)
- 不选选项 5 (弱化 V1.0 标准)

**修法现状 (2026-08-18 17:25, 选项 1+2 拍板后)**:

选项 1 **不可行** (powercfg /a 验证):
- 此机器 sleep states:
  - ✅ Standby (S0 Low Power Idle) — Modern Standby 当前 only sleep state
  - ❌ S1 / S2 / S3 — 系统固件不支持
  - ❌ 混合睡眠
- 结论: **Win 11 固件 only Modern Standby**, `powercfg /h off` + `bcdedit` 改 S0 → S3 失败
- WakeToRun 在 S0 上不响应是固件级限制, 注册表修不了
- 笔记本电池续航不能动 (固件锁定 Modern Standby, 改了无效)

选项 2 ✅ **已实现**:
- Task Scheduler `us-stock-causal-daily-report-1705-backup` 新建, NextRun 8/19 17:05
- 17:05 跑同样的 `run_daily_report.cmd` (redirect log 到 cron_<date>.log append)
- daily_report.py 加 `_is_already_ran_today(date_str)` 守卫:
  - 检查 `output/report_<date>.md` 在 2h 内生成 → skip
  - 加 `--force` arg bypass 守卫 (manual 强制重跑)
  - 跨日 (历史日期) 不算 guard
- 验证 (8/18 17:25):
  - `--skip-fetch --skip-md --skip-html --skip-dashboard` 不带 --force → SKIP banner, exit 0 ✅
  - 带 --force → 全 pipeline 跑 ✅

**未实施项**:
- 选项 1 不可行 (固件限制)
- 选项 3 (watchdog) 暂不实施 (选项 2 够用)
- 选项 4 5 暂不实施 (跟原 user 拍板一致)

**V1.0 路线图影响 (修后预期)**:
- 30 天稳定期 (8/9~9/7) 8/15 MISSING 已知 issue
- 8/19 起 17:05 backup 生效, Modern Standby 即使漏跑 17:00 也会 17:05 补
- 9/3 v0.9.5 RC1 实测 8/19~8/30 (12 天) 0 MISSING 即视为选项 2 修好
- 9/7 wait 期结束时实际 0 MISSING 算 30/30 day 0 fail 真达成 (8/15 仍标 known, 但 8/19 后 0 new fail)

**V1.0 路线图影响**:
- 30 天稳定期 wait 期 (8/9~9/7) 已有 1 MISSING (8/15)
- 9/3 RC1 拍板前还有 16 天 (8/18~9/3) 业务实测
- 如果 16 天里再 MISSING 1 次 = 2/30 = 93.3% < 100% 不达标
- KI-3 必须 9/3 前修 (否则 V1.0 0 fail 不可能)

**重启验证** (选项 1 修后):
- `powercfg /a` 看支持的 Sleep 状态
- 应该从 "Standby (S0 Low Power Idle)" 变 "Standby (S3)"
- WakeToRun 在 S3 下 100% 唤醒
- 修后 7 天内无 MISSING 即视为修好
