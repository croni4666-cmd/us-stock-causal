# Phase 5 — 调度设置 (v0.5.1+)

> **🪦 ARCHIVED 2026-07-26** — 飞书 cron 路径整个废弃,跟 user global "hobbyist ceiling" 规则冲突
> (hosted service 需要 token / 维护 channel / 关注"机器人是不是被禁言")。
>
> 新 Phase 5 路径: **本地化调度** — Windows Task Scheduler + 本地 alert log。
> 详见 `ROADMAP.md` (workspace) Phase 5 段。
>
> 本文件保留作 reference, **不进 main flow**。

---

> **v0.5.1 默认不自动跑**。Cron + 飞书推送需要**用户手动配置**。
>
> **Why**: v1 教训 — 拍脑袋设的 17:00 cron 没人看,飞书 webhook 配错导致 spam 整群。
> Phase 5 走"用户先手动跑一次确认,再决定要不要 cron"的路径。
>
> **⏸️ 2026-07-26 整个飞书路径 cancelled, 上面那段是历史**。

---

## 📋 Phase 5 进度 (cancelled 2026-07-26, 改本地化)

| ID | Item | Status | User Action |
|---|---|---|---|
| P5-1 | 飞书 webhook 配置 | 🪦 cancelled | ~~需要: 创建机器人 + 复制 URL~~ — 不需要 (改本地化) |
| P5-2 | 手动跑一次确认 (飞书) | 🪦 cancelled | ~~需要: 跑 `python examples/feishu_push.py`~~ — 改: 跑 `python examples/daily_report.py` 看本地输出 |
| P5-3 | 跟 user 确认 cron 时间 | `proposed` | 候选 17:00 / 16:30 / 22:00 |
| P5-4 | 配置 Windows Task Scheduler (本地 cron) | `proposed` | `scripts/setup_windows_task.ps1` 一键配 |
| P5-3 | 跟 user 确认 cron 时间 | ⏳ | **需要**: 你说"每天 17:00"或"其它" |
| P5-4 | Re-enable cron | ⏳ | **需要**: 你说"OK 跑"再注册 |

---

## 🛠️ P5-1: 飞书 webhook 配置 (3 步, ~5 min)

### 步骤 1: 创建飞书机器人

1. 打开飞书,进**你想接收日报的群**
2. 群设置 → 群机器人 → 添加机器人 → **自定义机器人**
3. 名字:`us-stock-causal-bot` (随便起)
4. 描述:`每日美股因果分析报告 (v0.5.1)` (随便写)
5. 安全设置:勾选**签名校验** (推荐) 或 IP 白名单 (可选)
6. **复制 webhook URL**,格式像:
   ```
   https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

### 步骤 2: 写 webhook URL 到 .env

```bash
# 在项目根目录
G:\Minimax trade market\us-stock-causal\.env

# 内容 (一行,不要引号,不要空格):
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

`.env` 在 `.gitignore` 里,**不会被 commit**。安全。

### 步骤 3: 测试 dry-run

```powershell
cd "G:\Minimax trade market\us-stock-causal"
python examples/feishu_push.py --dry-run
```

应该看到:
```
=== DRY RUN — payload (前 500 字符) ===
{
  "msg_type": "interactive",
  "card": {
    "header": { ... },
    "elements": [ ... ]
  }
}
... (总 XXXX 字符)

✅ Dry run 完成,没真发
```

如果没看到上面,检查 .env 路径和内容。

---

## 🛠️ P5-2: 手动跑一次确认 (1 步, ~30s)

```powershell
python examples/feishu_push.py
```

应该看到:
```
Webhook: https://open.feishu.cn/open-apis/bot/v2/hook/...xxxx
Report date: 2026-07-13
正在推送...
✅ 推送成功!去飞书看
```

**去飞书群看**:
- 顶部 1 行情绪 (VIX/10Y/DXY + 4 指数)
- 4 指数 × 5 段报告
- 底部"自动生成 · 不构成投资建议"

如果飞书没收到:
- 检查 webhook URL (复制时少字符常见)
- 检查机器人有没有被禁言
- 看 log: `logs/*.log` 里的 `[feishu]` 行

---

## ⏰ P5-3: 确认 cron 时间 (跟 user 对齐)

候选时间:
| 时间 | 适合 |
|---|---|
| **17:00 (美股收盘后 1h)** | 当天数据齐全,适合做日报 |
| 16:30 (美股收盘后 30min) | 抢时间看收盘后第一波 |
| 22:00 (亚洲早盘前) | 睡醒看 4 指数 + 5 段 + 顶部情绪 |
| 手动 (无 cron) | 周末想看就看 |

**v1 默认是 17:00**,这是美股主流研报发布时间。
**你可以改** — 我等你确认再注册 cron。

---

## 🛠️ P5-4: Re-enable cron (跟 user 走完 P5-1~3 后,1 条命令)

```powershell
# 注册 daily cron (mavis 平台,不是系统 cron)
mavis cron add us-stock-daily --every 1d --time 17:00 --prompt "Run python examples/feishu_push.py in G:\Minimax trade market\us-stock-causal"
```

**监控 1 周**:
- 每周日看 `mavis cron ls` 确认 us-stock-daily 在跑
- 看飞书群每天 17:00 有没有新消息
- 出问题: `mavis cron disable us-stock-daily`

**禁用**:
```powershell
mavis cron disable us-stock-daily
```

---

## 🪦 已知限制 (v0.5.1)

1. **K 线图不直接发飞书**: 飞书 webhook 图片附件限制 10MB,K 线图 100KB 应该 OK,
   但本脚本 (v0.5.1) 只发文字。需要发图,得用 upload_image API + Im 上传,
   Phase 5.1 后续做。
2. **报告超过 30KB 自动截断**: 5 段报告 ~6KB,远低于限制,但如果以后加更多段,可能截断。
3. **失败不重试**: 飞书 webhook 一次失败就 fail,不会 retry。
   v0.5.2 计划加重试 + dead-letter queue。
4. **没有 timezone 处理**: 报告日期用 `date.today()` (Asia/Shanghai 假设),
   美股夏令时后可能差 1 天。

---

## 🎯 推荐的"用户逐步走"路径

```
Day 1: P5-1 (创建飞书机器人, 5 min)
       ↓
Day 1: P5-2 dry-run (30s, 不真发)
       ↓
Day 1: P5-2 真发一次 (30s)
       ↓
       (看 1 天飞书消息, 确认格式 OK)
       ↓
Day 2: 跟我说"OK 跑" + cron 时间
       ↓
       我注册 cron + 监控 1 周
```

不要一次性全配。**v1 教训**: 拍脑袋 17:00 + 没测 webhook,导致日报 spam 群里 1 周才被发现。
