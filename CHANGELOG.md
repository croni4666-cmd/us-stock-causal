# Changelog

All notable changes to us-stock-causal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Phase 1: 数据层扩展 (5 标的 + 10 行业 ETF + 3 宏观 = 18 ticker)
- Phase 2: 因果分析 (归因分解 + 历史模式匹配 + 关键阈值)
- Phase 3: 简洁呈现 (5 段制报告 + 1 张 K 线图)
- Phase 4: 自分析工具 (`pa export` + `pa notebook` + sample notebook)
- Phase 5: 调度 (cron + 飞书推送, gated on 1-4)

## [0.1.0] - 2026-07-13

### Added
- **OpenBB Platform SDK 4.7.2** 装好 (清华镜像, ~300 MB)
- **Clash 代理自动检测** (`src/proxy.py`)
  - 探测 8 个常见 Clash 端口 (7897/7899/7890/7891/10809/10808/1080/8080/8888)
  - 支持 spec: `auto` / `off` / `clash:7897` / `http://x:1234`
  - 默认 auto, 检测到就用, 没检测到就警告
- **AAPL 端到端 demo** (`examples/demo_aapl.py`)
  - 拉 AAPL 1.5 年 OHLCV via OpenBB (provider=yfinance)
  - 计算 SMA(20/50/200)
  - mplfinance 画 K 线 + 3 均线 (117 KB PNG)
  - parquet 缓存 (28.8 KB / 380 rows)
- **项目结构** (src/ + data/ + output/ + logs/ + tests/ + examples/)
- **.gitignore** 排除 data/* / output/* / logs / __pycache__ / .venv
- **requirements.txt** 锁定 openbb[ta] / mplfinance / plotly / pandas 等

### Verified
- OpenBB + Clash proxy: 1 个 ticker 0.5s 拉到 380 行
- K 线图生成: 1.5 年 + 3 SMA 叠加, 117 KB PNG
- AAPL 当前: $315.32, 收盘 above 200 日均线 $272.45

### Known Issues
- matplotlib font 警告: "Failed to find font weight medium" — 不影响输出, 字体回退
- 报告本里看到 `findfont: ... semibold/medium` 警告, 7-8 次, 已知 matplotlib 在 Windows 上对中文字体问题, 不影响英文 K 线图
- (本版本无主动告警,等 Phase 3 写完报告再处理)

### Not Yet Implemented (等 Phase 1+)
- 多 ticker 拉取
- 归因分解
- 历史模式匹配
- 关键阈值检测
- 飞书推送
- cron 调度
