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
