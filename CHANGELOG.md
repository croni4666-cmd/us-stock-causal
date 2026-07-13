# Changelog

All notable changes to us-stock-causal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- v0.2.1: 14 spot ETF 代理 (GLD/SLV/PPLT/PALL/CPER/USO/BNO/UNG/WEAT/CORN/SOYB/CANE/BAL/JO),补 =X 不可用的缺口
- Phase 2: 因果分析 (归因分解 + 历史模式匹配 + 关键阈值)
- Phase 3: 简洁呈现 (5 段制报告 + 1 张 K 线图)
- Phase 4: 自分析工具 (`pa export` + `pa notebook` + sample notebook)
- Phase 5: 调度 (cron + 飞书推送, gated on 1-4)

## [0.2.0] - 2026-07-13

### Added
- **49 ticker 数据集**(实际 35 个 parquet, 14 商品现货 =X 不可用 skip)
  - 4 指数: DIA / QQQ / RSP / QQQE
  - 11 行业 ETF (GICS 全 11,含 XLC Communication Services)
  - 6 宏观: ^VIX / DXY → DX-Y.NYB / ^IRX / ^FVX / ^TNX / ^TYX (完整 yield curve)
  - 14 商品期货 (=F): GC=F / SI=F / PL=F / PA=F / HG=F / CL=F / BZ=F / NG=F / ZW=F / ZC=F / ZS=F / SB=F / CT=F / KC=F
- **`src/data.py`** yfinance 统一封装 (替代 OpenBB commodity API 缺失问题)
  - ticker alias: DXY → DX-Y.NYB (yfinance 真实名字)
  - retry 3 次 + 指数 backoff
  - 列名小写 + DatetimeIndex + 去 tz
- **`src/cache.py`** parquet 增量缓存
  - 缓存 < 1 天 → 直接返回 (cached)
  - 缓存 > 1 天 → 增量更新 (incremental)
  - 无缓存 → 全量拉 (full)
  - safe_name: ^VIX → _VIX, GC=F → GC_F
- **`config/tickers.yaml`** 49 ticker 4 层分类 + GICS 标注 + 各层 description
- **`examples/fetch_all.py`** 一键拉全 49 ticker,带进度 + 缓存复用

### Verified
- 35/35 non-optional ticker 成功 (4 指数 + 11 行业 + 6 宏观 + 14 期货)
- 17,493 rows 总数据, 858 KB parquet
- Phase 1 fetch 实际耗时 ~40s (35 个 ticker × ~1s)
- 缓存复用: 二次跑 0.1s 完成 (cached status)

### Known Issues
- **14 商品现货 (=X) yfinance 不可用**: GC=X / SI=X / CL=X / GC=X 等 ticker 在 yfinance
  返回空数据 (8s timeout × 14 = 112s 浪费)。OpenBB `commodity.price.spot` 只支持 FRED provider
  (宏观数据,无商品)。**Workaround**: 用现货 ETF 代理 (GLD/SLV/USO 等),计划 v0.2.1 实现
- (继承 v0.1.0) matplotlib font warning on Windows (cosmetic)

### Design Pivot (重要)
- **OpenBB Platform SDK 不是 commodity 数据的好后端**: `obb.commodity.price.historical`
  方法不存在,`obb.commodity.price.spot` 只支持 FRED。**v0.2.0 改用 yfinance 直接拉**,
  OpenBB 退到 Phase 4 自分析工具再考虑 (那时可能用 OpenBB 跑 Jupyter)

### Not Yet Implemented (等 Phase 2+)
- 归因分解 (ret_ticker = α + β·ret_market + γ·ret_sector + ε)
- 历史模式匹配 (DTW 或欧式距离)
- 关键阈值检测 (支撑/阻力/财报)
- 报告生成 (5 段制)
- 飞书推送
- cron 调度
- 自分析工具 (Jupyter / sample notebook)

## [0.1.0] - 2026-07-13

### Added
- OpenBB Platform SDK 4.7.2 装好
- Clash 代理自动检测 (8 端口)
- AAPL 端到端 demo (380 rows / SMA20/50/200 / K 线图 / parquet)
- 项目结构 + git init + .gitignore + requirements.txt + README

### Verified
- 1 个 AAPL ticker 0.5s 拉到 380 行
- K 线图生成 117 KB PNG
- git commit `6f1ff7a` (9 files / 514 lines)
