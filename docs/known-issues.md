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

**重现验证**:
```python
from sec_fetch import get_metric_history
hist = get_metric_history("WFC", "revenue", n_quarters=4)
# 返回 2020-09-30 / 2020-06-30 / 2020-03-31 全是 2020 财年
# 真实 WFC 2026 Q2 营收 $21.5B 不在返回里
```

**V1.0 路线图影响**:
- 不破坏 30 天稳定期 wait 期 (Shadow mode 不接 daily_report)
- v0.9.5 RC1 (9/8) 拍板 WFC 修法选项 1-4
- 9/15 v0.9.9 RC2 修完
- 9/20 v1.0.0 tag 时 WFC 必须修好 (否则 daily_report SEC 段 WFC 行 = stale data 污染报告)
