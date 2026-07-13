# us-stock-causal

> 一手数据 + 因果分析 — 看涨跌的"为什么",不是"看多看空"投票
> v0.1.0 — Phase 0 done (2026-07-13)

## 这是什么

不是研报生成器。**是让你能自己看到"为什么涨/为什么跌"的工具**。

每天 1 个 ticker,5 分钟内能告诉你:
- 过去 5 天为什么这么走 (归因分解)
- 接下来 3 个关键阈值在哪 (支撑/阻力/财报)
- 历史相似模式后续如何 (模式匹配)

数据自己拉,模型自己跑,数据可导出,Jupyter 可分析。

## 路线图

看 [`G:\Minimax trade market\ROADMAP.md`](../ROADMAP.md) (workspace 级 ROADMAP, 单一事实源)。

当前进度: **Phase 0 done** → Phase 1 in progress (5 标的 + 10 行业 ETF + 3 宏观)

## 5 分钟跑通

```bash
# 1. 装依赖 (清华镜像, ~5 min)
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 跑 AAPL demo (验证 OpenBB + Clash 代理 + K 线图)
python examples/demo_aapl.py

# 3. 输出
#   data/raw/AAPL.parquet (28.8 KB, 380 rows)
#   output/AAPL_demo.png   (117 KB K 线 + 3 SMA)
```

## 当前进度

| Phase | 状态 | 关键交付物 |
|---|---|---|
| 0. Setup | ✅ | OpenBB + Clash + AAPL demo |
| 1. 数据层 | ⏳ next | 18 ticker 拉全 (5 + 10 + 3) |
| 2. 因果分析 | 📋 planned | 归因 + 模式匹配 + 阈值 |
| 3. 简洁呈现 | 📋 planned | 5 段制报告 |
| 4. 自分析 | 📋 planned | `pa export` + `pa notebook` |
| 5. 调度 | 📋 planned | cron + 飞书 (gated on 1-4) |

## 设计原则 (vs v1/v2)

| 维度 | v1/v2 | v3 (本项目) |
|---|---|---|
| **底层** | 自写 fetch + Clash hack | OpenBB Platform SDK (30+ 源) |
| **数据** | 5 个股 | 5 标的 + 10 行业 ETF + 3 宏观 |
| **分析** | 投票出"看多/看空" | 归因 + 模式匹配 + 阈值 |
| **输出** | 311 行 7 张表 | 5 段文字 + 1 张 K 线图 |
| **维护** | 全自己 | OpenBB 社区 (周更) |

## 为什么换方向

v1/v2 (us-stock-daily) 失败原因: 输出了"看多/看空"投票结论,跟大 V 喊单没区别。
用户原话: **"看多看空这种评论性内容你只要混迹对应股市的社交圈子都能得到消息。假如不掌控数据、没有一手信息和模型,我还不如直接去看研报。"**

## 约束

- **本地存储**: ~90 GB free (C/E/F/G,D 移动硬盘不计)
- **不花一分钱**: 免费 tier (yfinance / AlphaVantage / FRED)
- **单人维护**: 借 OpenBB 社区, 不自己 fork
- **优雅降级**: 单 ticker 失败不阻塞

## License

个人项目,非开源
