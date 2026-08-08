# USER_GUIDE — us-stock-causal

> **怎么用**: 数据拉 / 改 DAG / 跑 daily / 解读输出 / FAQ
> **目标读者**: 跑通 daily cron, 改 DAG, 解读报告
> **v0.8.5** (2026-08-08)

---

## 目录

1. [快速开始](#1-快速开始)
2. [数据怎么拉](#2-数据怎么拉)
3. [怎么改 DAG](#3-怎么改-dag)
4. [怎么跑 daily report](#4-怎么跑-daily-report)
5. [怎么解读输出](#5-怎么解读输出)
6. [FAQ](#6-faq)
7. [常见问题排查](#7-常见问题排查)

---

## 1. 快速开始

### 1.1 装依赖

```bash
# Windows + Clash 代理
pip install -r requirements.txt --proxy http://127.0.0.1:10808

# 验证
python -c "import dowhy, econml, yfinance, pandas, networkx, causallearn; print('OK')"
```

### 1.2 拉数据 (47 ticker 全)

```bash
# 全拉一次 (2-3 min, 含 14 期货 + 12 ETF)
python examples/fetch_all.py

# 增量拉 (每天 daily cron 自动跑, ~30s)
python examples/fetch_all.py  # 同样命令, cache 自动增量
```

输出:
- `data/raw/indices/DIA.parquet` (4 指数, ~28KB each)
- `data/raw/sectors/XLK.parquet` (11 行业, ~29KB each)
- `data/raw/macro/_TNX.parquet` (6 macro, ^前缀变 _)
- `data/raw/commodities_futures/GC_F.parquet` (14 期货, =F 变 _F)
- `data/raw/commodities_spot_etf/GLD.parquet` (12 ETF, normal)
- 总结: 47 ticker / 47 parquet (47 OK / 0 fail)

### 1.3 跑 daily report

```bash
# 完整跑 (冷跑 ~9s, 含 L1/L2/L3 因果分析)
python examples/daily_report.py

# 跳过 fetch (用 cache, ~8.5s, daily cron 实际路径)
python examples/daily_report.py --skip-fetch

# 跳过 HTML/dashboard (smoke test 路径, ~8.5s)
python examples/daily_report.py --skip-fetch --skip-html --skip-dashboard
```

### 1.4 配 Windows cron (17:00 daily)

```cmd
:: admin cmd
cd "G:\Minimax trade market\us-stock-causal"
scripts\install_task.cmd

:: 验证
schtasks /Query /TN "us-stock-causal-daily-report"
```

---

## 2. 数据怎么拉

### 2.1 47 ticker 配置 (config/tickers.yaml)

```yaml
universe:
  indices:        # 4 指数
    - {symbol: DIA}     # 道指
    - {symbol: QQQ}     # 纳指
    - {symbol: RSP}     # 等权 S&P 500
    - {symbol: QQQE}    # 等权纳指
  sectors:        # 11 行业 (State Street XL*)
    - {symbol: XLK, gics: "Information Technology"}
    - {symbol: XLF, gics: "Financials"}
    # ... (XLK/XLF/XLV/XLE/XLY/XLP/XLI/XLU/XLB/XLRE/XLC)
  macro:          # 6 宏观
    - {symbol: ^VIX}    # CBOE 波动率
    - {symbol: DXY}     # 美元指数
    - {symbol: ^IRX}    # 13W 国债
    # ... (^IRX/^FVX/^TNX/^TYX/DXY/^VIX)
  commodities:     # 14 期货 + 12 现货 ETF
    futures: [...]  # GC=F/SI=F/PL=F/... (14 期货)
    spot_etf: [...] # GLD/SLV/PPLT/... (12 ETF, BAL/JO DELISTED 跳过)
```

### 2.2 加新 ticker

```yaml
# 1. 加到 config/tickers.yaml
sectors:
  - {symbol: XLE, gics: "Energy"}

# 2. 拉数据
python examples/fetch_all.py

# 3. 跑 daily 验证
python examples/daily_report.py --skip-fetch
```

### 2.3 重抓 (P7-5 baseline)

```bash
# 月度 / 半月度重抓 (P7-5 残差 baseline 漂移, 见 FAQ)
python -m src.residual_regression capture

# 验证
ls -la data/baseline/
```

### 2.4 强制重拉 (cache miss)

```bash
# 单 ticker
rm data/raw/indices/DIA.parquet
python examples/fetch_all.py

# 全重拉
rm -rf data/raw/indices data/raw/sectors data/raw/macro data/raw/commodities_*
python examples/fetch_all.py
```

---

## 3. 怎么改 DAG

### 3.1 DAG 配置文件 (config/causal_dag.yaml)

```yaml
dag_name: "Phase 9.x: ..."
dot: |
  digraph causal_p9_x {
    // 节点
    TNX [label="^TNX (10Y)"];
    XLK [label="XLK (Tech)"];
    DIA [label="DIA"];
    // ...

    // 边 (P9-1.7 47 节点 172 边)
    TNX -> XLK;  // 利率 → 科技股
    TNX -> DIA;  // 利率 → 道指
    // ...
  }

# 节点元数据
nodes:
  treatments: [TNX, IRX, FVX, TYX, VIX, DXY, ...]  # 47 节点
  outcomes: [DIA, QQQ, RSP, QQQE]
  parquet_map:
    TNX: "data/raw/macro/_TNX.parquet"
    # ...
```

### 3.2 加新节点

```yaml
# 1. 加节点
NG_F [label="NG=F (Nat Gas)"];

# 2. 加边 (从 NG_F 到 XL*)
NG_F -> XLE;  # 天然气 → 能源股
NG_F -> XLU;  # 天然气 → 公用事业 (电力)

# 3. 加 parquet_map
NG_F: "data/raw/commodities_futures/NG_F.parquet"

# 4. 验证 acyclic
python -c "from src.causal import load_dag_config, load_dag_graph; import networkx as nx; g = load_dag_graph(load_dag_config()); print('Acyclic:', nx.is_directed_acyclic_graph(g), 'Nodes:', g.number_of_nodes(), 'Edges:', g.number_of_edges())"
```

### 3.3 加新因果 query

```python
# 在 examples/daily_report.py:step_causal 加新 query
eff = causal_mod.causal_query("VIX", "QQQ", n_refutations=1, data=data, cfg=cfg)
print(f"VIX → QQQ ATE: {eff.estimate:.4f} (p={eff.p_value:.3f})")
```

### 3.4 验证 DAG 不破坏 daily cron

```bash
# 改完跑 1 次完整 daily
python examples/daily_report.py --skip-fetch

# 跑 smoke test 验证
python tests/test_smoke.py
```

---

## 4. 怎么跑 daily report

### 4.1 命令行选项

```bash
python examples/daily_report.py [options]

options:
  --date YYYY-MM-DD    # 报告日期 (默认今天)
  --skip-fetch         # 跳过 yfinance 拉数据 (用 cache)
  --skip-md            # 跳过 markdown 报告
  --skip-html          # 跳过 HTML 报告 (K-line SVG)
  --skip-dashboard     # 跳过性能 dashboard
  --quiet              # 不打 banner
```

### 4.2 8 步内容

| Step | 名称 | 跳过标志 | 耗时 (cold) |
|---|---|---|---|
| 1 | fetch | `--skip-fetch` | 0 (skip) / 30s (run) |
| 2 | attribution | — | 0.7s |
| 3 | residual_regression | — | 0.9s |
| 4 | markdown_report | `--skip-md` | 5.1s (含 L2/L3/PC/CATE) |
| 5 | html_report | `--skip-html` | skip |
| 6 | performance_dashboard | `--skip-dashboard` | skip |
| 7 | check_alerts | — | 0.3s |
| 8 | causal | — | 0.06s (cache hit) |
| **Total** | | | **9.0s** |

### 4.3 输出文件

```
output/
├── report_2026-08-08.md          # 5 段制报告 + 因果机制段
├── report_2026-08-08.html        # K 线图 + dashboard
├── dashboard_2026-08-08.html     # 性能 dashboard
├── alerts_2026-08-08.json        # 异常告警 (5 类 check)
├── logs/
│   └── cron_2026-08-08.log       # cron 执行日志
data/cache/alerts/
└── alerts_2026-08-08.json        # P8-6 告警 log
```

### 4.4 daily cron 验证

```bash
# 看 17:00 是否真的跑了
schtasks /Query /TN "us-stock-causal-daily-report" /V /FO LIST

# 看最近 7 天 cron log
ls output/logs/cron_*.log | tail -7 | xargs -I {} sh -c 'echo "=== {} ==="; head -20 {}'
```

---

## 5. 怎么解读输出

### 5.1 Markdown 报告结构

```markdown
# 📊 美股每日分析报告 (5 段制) — 2026-08-08

**生成时间**: 2026-08-08 14:30:00
**模型**: Phase 2 全套 + Phase 3 顶部情绪 + Phase 9 Pearl 因果

## 顶部情绪 (1d / 5d / 20d)
- 1d: VIX 15.1 (-2.3%) / TNX 4.25% (+0.5%) / DXY 102.5 (-0.2%)
- 5d: ...

## 因果机制 (Phase 9.0 Pearl-style)
- **L2 干预**: VIX `do(+1%)` → QQQ 预期↓ 0.1226 (-12.26%, p<0.001); 反驳测试 1/3 通过
- **L2 干预**: TNX `do(+1%)` → QQQ 预期↑ 0.0915 (+9.15%, p<0.001); 反驳测试 1/3 通过
- **DAG 验证 (P9-1.1 PC vs 手工)**: ✅ 重叠 6 边; PC 学出 50 边, 手工 172 边
- **CATE 异质性 (P9-1.4)**: VIX→QQQ 按 VIX 切 3 群, 异质性比 1.37x (低 VIX 群强 37%)

## DIA — 2026-08-08 (5 日报告)
**① 5 日行情**: 5 日累计 +3.20%, 最好 2026-08-04 (+1.73%), 最差 2026-08-06 (-0.85%)
**② 5 日归因**: 主导 XLK+1.01% / XLY+0.61% / XLI+0.58%, 残差 +0.47%
**③ 关键阈值**: 支撑 $538.19, 200 SMA above +9.36%, 52w 92.1%, R1 $548.20
**④ 历史相似**: 20d pattern 相似 top 10, 5d fwd avg +0.21% / win 50%
**⑤ 风险**: 信号矛盾 score=0.67(mixed); 4d 后 CPI

## QQQ — 2026-08-08 (5 日报告)
... (类似 DIA)
```

### 5.2 5 段含义

| 段 | 内容 | 怎么用 |
|---|---|---|
| **① 5 日行情** | 累计收益 + 最好/最差日 | 看整体方向 |
| **② 5 日归因** | 行业 ETF 加权贡献 + 残差 | 看哪些行业推动了涨跌 |
| **③ 关键阈值** | 支撑/阻力/200 SMA/52w 位置/R1 | 看技术位 |
| **④ 历史相似** | 20d 模式 top 10, 5d fwd 收益分布 | 看历史经验 |
| **⑤ 风险** | 信号矛盾 score + 4d 内事件 | 看矛盾 / 风险事件 |

### 5.3 因果机制段 (Phase 9)

| 元素 | 含义 |
|---|---|
| **L2 干预** | do(T +1%) → O 预期变化 (Pearl do-calculus, 强干预语义) |
| **L3 反事实** | 实际值 vs 反事实值 (Pearl 3 层, 强反事实) |
| **DAG 验证** | PC algorithm 跟手工 DAG 重叠率 (P9-1.1) |
| **CATE 异质性** | 跨 sub-population 异质性 (P9-1.4) |

### 5.4 告警 (P8-6)

```json
{
  "as_of": "2026-08-08",
  "alerts": [
    {
      "type": "vix_spike",
      "subject": "data/raw/macro/_VIX.parquet",
      "message": "VIX > 30 或 1 日涨幅 > 15%",
      "severity": "warning"
    }
  ]
}
```

5 类告警:
- **stale**: parquet 2 工作日没更新
- **residual**: 残差回归 1.5x 漂移 (P7-5 baseline)
- **vix_spike**: VIX > 30 或 1 日 +15%
- **ticker_fail**: yfinance 限流 / parquet < 1KB
- **parquet_corrupt**: pandas 读失败 / 0 行

### 5.5 Windows toast 通知 (P8-7)

告警触发时弹窗 (plyer). 弹窗在 17:00 cron 跑完后出现, timeout 10s 自动消失.

---

## 6. FAQ

### Q1: yfinance 拉数据 5xx 失败怎么办?

**A**: P8-5 tenacity 自动 retry 3 重 (1s/2s/4s). 仍失败用 cache. 看 `data/cache/retry_log.json` (audit trail):

```bash
cat data/cache/retry_log.json | python -m json.tool | tail -30
```

### Q2: DAG 改成有环了怎么办?

**A**: smoke test `test_dag_acyclic_47_nodes_v085_p92` 会 fail, 提示不是 DAG. 改 `config/causal_dag.yaml`, 删环边.

### Q3: daily cron 跑超 10s 怎么办?

**A**: P9-1.5.5 + P9-1.5.5.5 OLS path 已加 (3500x 加速). 仍超 10s:
1. 看哪步慢: `python examples/daily_report.py --skip-fetch --verbose` 看 8 步 elapsed_s
2. 大概率是 PC algorithm (47 节点 ~1.5s), 已加 _PC_CACHE
3. 仍超, 看 FAQ Q5 P7-5 baseline 漂移

### Q4: 报告里 "残差 +0.47%" 是什么意思?

**A**: 5 日 真实涨跌 = 行业 ETF 加权预测 + 残差. 残差 > 0 表明实际比预测涨得多 (有非行业因素). 残差 > 0.5% 业务上是正常噪声.

### Q5: P7-5 baseline 漂移 1.5x 怎么修?

**A**: P7-5 baseline 是月度/半月度重抓的. 漂移 > 1.5x 表明市场 regime 变化. 修法:

```bash
# 重抓 baseline (用今天数据)
python -m src.residual_regression capture

# 验证
ls -la data/baseline/residuals_v*.json
```

跟 daily cron 节奏: 月度 / 半月度. (实际 v0.6.9h 经验: 3 天 5d 残差漂移 12-15x, 必须月度或更频繁重抓.)

### Q6: VIX→QQQ ATE 跟 ROADMAP 估的 -0.12 对不上?

**A**: ATE = -0.1226 (21 节点 -0.1232, 35 节点 -0.1226, 47 节点 -0.1226) 总效应守恒. 跟 ROADMAP 估的 -0.12 ± 0.01 范围 OK.

### Q7: BAL / JO 期货怎么处理?

**A**: BAL (cotton iPath ETN) + JO (coffee iPath ETN) 2018 DELISTED, yfinance 不可拉. **期货 CT_F/KC_F 已加到 DAG (batch 4)**, 但 **没有 spot ETF 节点** (batch 5 跳过). DAG 实际 47 节点 (设计 49 - 2 delisted).

### Q8: 加新 ticker 到 DAG 后 daily_report fail 怎么排查?

**A**:
1. 跑 `python examples/fetch_all.py` 验证 ticker fetch OK
2. 跑 `python -c "from src.causal import load_dag_graph; g = load_dag_graph(); print('Acyclic:', __import__('networkx').is_directed_acyclic_graph(g))"` 验证 acyclic
3. 跑 `python tests/test_smoke.py` 验证 smoke test 全过

### Q9: P9-1.7 batch 5 边设计为什么不加 ETF→industry direct?

**A**: 12 ETF 跟 14 期货 1:1 配对, 加 ETF→industry 跟 batch 4 期货→industry 重复 (26 边 commodity→industry 已 cover). 走 **ETF→期货→industry** 中介链 (GLD→GC_F→XLB) 比 ETF→industry direct 更经济.

### Q10: 性能 profile 怎么跑?

**A**:
```bash
python -c "
import time
from examples.daily_report import run_daily_report
import os
os.environ['US_STOCK_CAUSAL_FAST'] = '1'
t0 = time.time()
r = run_daily_report(date_str='2026-08-08', skip_fetch=True, skip_html=True, skip_dashboard=True, verbose=False)
print(f'Total: {time.time()-t0:.2f}s')
for n, s in r['steps'].items():
    print(f'  {n}: {s[\"elapsed_s\"]}s')
"
```

---

## 7. 常见问题排查

### 7.1 daily cron 没跑

```bash
# 1. 看 task 是否还在
schtasks /Query /TN "us-stock-causal-daily-report"

# 2. 看最近 log
ls -la output/logs/cron_*.log | tail -3

# 3. 手动跑 1 次
python examples/daily_report.py --skip-fetch
```

### 7.2 Windows toast 不弹

```bash
# 1. 验证 plyer 装好
pip show plyer

# 2. 手动触发
python -c "from src.notify import notify_text; notify_text('test', 'test message', timeout=5)"
```

### 7.3 smoke test fail

```bash
# 1. 跑 verbose
python -m pytest tests/test_smoke.py -v 2>&1 | grep -E "FAIL|assert" | head -20

# 2. 跑单个 test
python -m pytest tests/test_smoke.py::test_dag_acyclic_47_nodes_v085_p92 -v
```

### 7.4 47 节点 DAG load 慢 (>5s)

```bash
# 检查 Pydot cache
python -c "from src.causal import _GRAPH_CACHE; print('Graph cache size:', len(_GRAPH_CACHE))"
# 应 1 (47 节点 yaml 一次解析后 cache)

# 手动 warm cache
python -c "from src.causal import load_dag_graph, load_dag_config; g = load_dag_graph(load_dag_config()); print('Loaded:', g.number_of_nodes(), 'nodes')"
```

### 7.5 daily_report 含 stale alert

```bash
# 1. 看是哪个 ticker stale
cat data/cache/alerts/alerts_$(date +%Y-%m-%d).json | python -m json.tool | grep -A 3 stale

# 2. 强制重拉
rm data/raw/<layer>/<ticker>.parquet
python examples/fetch_all.py
```

### 7.6 怎么 disable 一个 ticker (临时)

```yaml
# config/tickers.yaml
sectors:
  - {symbol: XLK, gics: "Technology", optional: true}  # 加 optional: true
```

`optional: true` 标记的 ticker fetch 失败不报错 (warn only). 用于已知数据源不稳的 ticker.

### 7.7 proxy 换了端口

```bash
# 修改 env var (永久化写到 system env)
[System.Environment]::SetEnvironmentVariable("HTTPS_PROXY", "http://127.0.0.1:10808", "User")

# 验证
echo $env:HTTPS_PROXY
```

### 7.8 想恢复旧版本 (rollback)

```bash
# 看 commit log
git log --oneline -10

# 回到 v0.8.0 (上一个稳定)
git checkout d7f96ca

# 验证
python tests/test_smoke.py
```

---

## 附录: 模块结构 (src/)

```
src/
├── proxy.py              # 代理设置 (Clash 10808)
├── data.py               # yfinance 封装 (P8-5 tenacity 集成)
├── cache.py              # parquet 增量缓存
├── retry.py              # tenacity 统一 retry 抽象 (P8-5)
├── fetch_*.py            # 拉数据子模块 (per layer)
├── attribution.py        # L1 归因 (Phase 2)
├── patterns.py           # 历史相似模式
├── thresholds.py         # 支撑/阻力/SMA
├── performance_dashboard.py  # 性能 dashboard
├── report.py             # 5 段制 markdown 报告 (v0.7.5 LRU cache)
├── report_html.py        # HTML 报告 + K 线
├── residual_regression.py  # P7-5 baseline 残差回归
├── residual.py           # 残差时间序列 + 健康评估
├── signals.py            # 顶部情绪信号
├── macro.py              # 宏观数据
├── etf_holdings.py       # ETF 持仓 (N-30D)
├── etf_holdings_parser.py  # N-30D HTML 解析
├── events.py             # 事件加载
├── events_gdelt.py       # GDELT 1h cache
├── sector_weights.py     # 行业 ETF 权重
├── sector_weights_live.py  # 1d cache (P7-4)
├── kline.py              # K 线图
├── checks/               # P8-1~6 异常检测
│   ├── stale.py
│   ├── residual.py
│   ├── vix_spike.py
│   ├── ticker_fail.py
│   └── parquet_corrupt.py
├── alert_logger.py       # P8-6 告警 log
├── notify.py             # P8-7 Windows toast (plyer)
├── yfinance_rate_limit.py  # 限流状态 cache
└── causal.py             # P9 Pearl 因果 (L1/L2/L3)
```

详见 [ARCHITECTURE.md](./ARCHITECTURE.md).
