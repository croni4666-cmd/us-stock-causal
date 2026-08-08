# ARCHITECTURE — us-stock-causal

> **怎么改**: 模块结构 / 数据流 / 缓存层 / 性能 / 扩展点
> **目标读者**: 改源码 / 加新功能 / 优化性能
> **v0.8.5** (2026-08-08)

---

## 目录

1. [系统总览](#1-系统总览)
2. [模块结构](#2-模块结构)
3. [数据流](#3-数据流)
4. [缓存层 (4 个 module-level cache)](#4-缓存层)
5. [性能优化路径](#5-性能优化路径)
6. [Pearl 3 层因果 (P9)](#6-pearl-3-层因果-p9)
7. [扩展点](#7-扩展点)
8. [测试架构](#8-测试架构)

---

## 1. 系统总览

```
┌─────────────────────────────────────────────────────────────┐
│  examples/daily_report.py (8 步编排)                          │
└────────┬────────────────────────────────────────────────────┘
         │
         ├─→ step 1: examples/fetch_all.py  (拉 47 ticker)
         │     └─→ src/data.py:fetch()  (P8-5 tenacity retry)
         │           └─→ yfinance → parquet
         │
         ├─→ step 2-3: src/attribution.py + src/residual_regression.py
         │     (L1 关联归因 + P7-5 残差回归)
         │
         ├─→ step 4: src/report.py:render_full_report()  (5 段制)
         │     └─→ src/causal.py:causal_query() + counterfactual_query() + cate_heterogeneity() + discover_dag_pc()
         │     (P9 Pearl L1/L2/L3 + PC algorithm)
         │
         ├─→ step 5-6: src/report_html.py + src/performance_dashboard.py
         │
         ├─→ step 7: src/checks/*  (P8-1~6 5 类异常)
         │     └─→ src/alert_logger.py + src/notify.py (plyer toast)
         │
         └─→ step 8: src/causal.py (causal section 摘要)
```

---

## 2. 模块结构

### 2.1 数据层

| 模块 | 职责 | 关键函数 |
|---|---|---|
| `src/proxy.py` | Clash 代理设置 | `setup_proxy()`, `is_proxied()` |
| `src/data.py` | yfinance 封装 (P8-5 tenacity) | `fetch(symbol, start, end, auto_adjust)` |
| `src/cache.py` | parquet 增量缓存 | `update_or_fetch()`, `cache_path()`, `read_cache()`, `write_cache()` |
| `src/retry.py` | tenacity 统一 retry 抽象 | `retry_yfinance()`, `retry_gdelt()`, `retry_io()` |
| `src/yfinance_rate_limit.py` | 限流状态 cache | `is_rate_limited()`, `record_rate_limit()` |
| `examples/fetch_all.py` | 47 ticker 全拉 | `main()`, `fetch_layer()` |

### 2.2 分析层 (Phase 2)

| 模块 | 职责 | 关键函数 |
|---|---|---|
| `src/attribution.py` | L1 归因 (4 指数 × 3 窗口) | `attribute_all_indices()`, `attribute_index()` |
| `src/sector_weights.py` | 11 行业 ETF 权重 | `load_sector_weights()` |
| `src/sector_weights_live.py` | 1d live cache (P7-4) | `load_live_or_static()`, `save_live_cache()` |
| `src/patterns.py` | 历史相似模式 (20d → 5d fwd) | `find_similar_patterns()` |
| `src/thresholds.py` | 支撑/阻力/200 SMA | `load_prices()`, `compute_pivots()` |
| `src/signals.py` | 顶部情绪 (VIX/TNX/DXY) | `macro_topline()` |
| `src/residual.py` | 残差时间序列 | `compute_residual_timeseries()`, `assess_weight_health()` |
| `src/residual_regression.py` | P7-5 残差回归 baseline | `capture_residuals()`, `compare_to_baseline()` |

### 2.3 呈现层 (Phase 3)

| 模块 | 职责 | 关键函数 |
|---|---|---|
| `src/report.py` | 5 段制 markdown + 因果机制段 (v0.7.5 LRU cache) | `render_full_report()`, `render_causal_section()` |
| `src/report_html.py` | HTML 报告 + K 线 | `render_html_report()` |
| `src/performance_dashboard.py` | 性能 dashboard | `render_performance_table()` |
| `src/kline.py` | K 线 + SMA + 事件线 | `draw_candles()`, `draw_events()` |

### 2.4 异常层 (Phase 8)

| 模块 | 职责 | 关键函数 |
|---|---|---|
| `src/checks/stale.py` | P8-1 stale parquet | `check()` |
| `src/checks/residual.py` | P8-2 残差回归 (复用 P7-5) | `check()` |
| `src/checks/vix_spike.py` | P8-3 VIX 异动 | `check()` |
| `src/checks/ticker_fail.py` | P8-4 ticker 失败 | `check()` |
| `src/checks/parquet_corrupt.py` | P8-5 parquet 损坏 | `check()` |
| `src/alert_logger.py` | 告警 log 写盘 | `make_alert()`, `write_alerts()`, `print_alerts()` |
| `src/notify.py` | Windows toast (P8-7) | `notify_if_alerts()`, `notify_text()` |

### 2.5 因果层 (Phase 9, Pearl)

| 模块 | 职责 | 关键函数 |
|---|---|---|
| `src/causal.py` | DAG 加载 + L2/L3 因果 (P9-1.1~1.7) | `causal_query()`, `counterfactual_query()`, `cate_heterogeneity()`, `discover_dag_pc()`, `load_dag_config()`, `load_dag_graph()`, `load_dag_data()` |
| `config/causal_dag.yaml` | 47 节点 172 边手工 DAG | DOT format |

### 2.6 调度层 (Phase 5)

| 模块 | 职责 |
|---|---|
| `examples/daily_report.py` | 8 步编排 (fetch→attribution→residual→md→html→dashboard→alerts→causal) |
| `scripts/install_task.cmd` | Windows Task Scheduler 17:00 daily 注册 |
| `scripts/run_daily_report.ps1` | cron 执行脚本 (隐藏窗口) |

---

## 3. 数据流

### 3.1 fetch 阶段

```
config/tickers.yaml
    ↓ (load_universe)
universe = {indices, sectors, macro, commodities.futures, commodities.spot_etf}
    ↓ (fetch_layer)
    for entry in entries:
        data.fetch(symbol, start, end)  ← tenacity retry_yfinance (3 重 1s/2s/4s)
            ↓
        yfinance.Ticker(symbol).history(...)
            ↓
        cache.update_or_fetch(...)  ← parquet 增量缓存
            ↓
        data/raw/<layer>/<safe_name>.parquet
```

### 3.2 analysis 阶段

```
data/raw/<layer>/*.parquet (47 parquet)
    ↓ (load_dag_data, inner join on date)
aligned DataFrame (516 rows × 47 cols, log return)
    ↓
causal.py:causal_query(treatment, outcome, data, cfg)
    ↓
    OLS: sm.OLS(y, X).fit()  ← statsmodels
    ↓
    refutation: _refute_with_ols()  ← P9-1.5.5 OLS path (35 节点 3 重 ~50ms)
    ↓
    CausalEffect dataclass (estimate, p_value, std_error, refutation)
```

### 3.3 report 阶段

```
causal.py:causal_query() + counterfactual_query() + cate_heterogeneity() + discover_dag_pc()
    ↓
report.py:render_causal_section()  ← 1 段因果机制
    ↓
report.py:five_segment_report(sym)  ← 4 指数 × 5 段
    ↓
report.py:render_full_report(INDICES)  ← date-based LRU cache (v0.7.5)
    ↓
output/report_<date>.md
```

---

## 4. 缓存层 (4 个 module-level cache)

us-stock-causal 用 6 个 module-level cache 优化性能, 全部 `clear_caches()` 一键清空.

### 4.1 缓存清单

| Cache | 位置 | Key | Value | 大小 (典型) |
|---|---|---|---|---|
| `_DATA_CACHE` | `src/causal.py` | `(start, end, parquet_mtimes)` | 516×47 DataFrame | 1 entry |
| `_FIT_CACHE` | `src/causal.py` | `(T, O, controls, n_obs)` | CausalForestDML model | 5-10 entries |
| `_SCM_CACHE` | `src/causal.py` | `(n_nodes, n_edges, n_obs, sorted_node_names)` | gcm.InvertibleSCM | 1 entry |
| `_REFUTE_CACHE` | `src/causal.py` | `(T, O, n_obs, n_refutations)` | dict (refutation 结果) | 5-10 entries |
| `_PC_CACHE` | `src/causal.py` (v0.8.0) | `(date, alpha, data_shape, data_hash)` | nx.DiGraph | 1 entry |
| `_GRAPH_CACHE` | `src/causal.py` (v0.7.5) | `md5(cfg["dot"])` | nx.DiGraph | 1 entry |
| `_REPORT_CACHE` | `src/report.py` (v0.7.5) | `(date.today(), tuple(symbols), layer)` | str (md) | 1-7 entries (date rollover) |
| `LRU Cache` | `src/retry.py` | (no LRU, append-only log) | retry_log.json | 100+ entries (audit trail) |

### 4.2 cache 失效场景

| Cache | 何时失效 |
|---|---|
| `_DATA_CACHE` | parquet 文件 mtime 变 (新数据) |
| `_FIT_CACHE` | (T, O, controls, n_obs) 任一参数变 |
| `_SCM_CACHE` | DAG 节点/边数变 或 n_obs 变 |
| `_REFUTE_CACHE` | (T, O, n_obs, n_refutations) 任一参数变 |
| `_PC_CACHE` | 隔天 (date key 变) / alpha 变 / data 改 |
| `_GRAPH_CACHE` | cfg["dot"] 改 (md5 不同) |
| `_REPORT_CACHE` | 隔天 / symbols 变 / layer 变 |

### 4.3 显式清理

```python
from src import causal as cm
result = cm.clear_caches()
# 返回: {"data_cleared": 1, "fit_cleared": 5, "scm_cleared": 1,
#        "refute_cleared": 5, "pc_cleared": 1, "graph_cleared": 1}
```

`src/report.py:_REPORT_CACHE` 不在 `clear_caches()` 里 (报告是 process-local 缓存, daily cron 1 process 1 run 不需要外部清).

### 4.4 文件级 cache (parquet)

- `data/raw/<layer>/<safe_name>.parquet` (47 文件, ~1.5 MB 总)
- `data/baseline/residuals_v<ver>.json` (P7-5 baseline, ~3 KB)
- `data/cache/alerts/alerts_<date>.json` (P8-6 告警, ~1 KB/day)
- `data/cache/sector_weights_live_<date>.json` (P7-4 1d cache, ~3 KB)
- `data/cache/retry_log.json` (P8-5 retry audit, append, 几 KB/月)
- `data/cache/yfinance_rate_limit.json` (限流状态, 几 KB)

---

## 5. 性能优化路径

### 5.1 v0.6.9f → v0.6.9l → v0.7.0 → v0.7.5 → v0.8.0 优化时序

| 版本 | 优化 | 加速 | daily cron |
|---|---|---|---|
| v0.6.9 baseline | — | 1x | 82s |
| v0.6.9f (P9-1.5.5) | L2 refutation 3 重 → 1 重 + cache | 4.8x | 17s |
| v0.6.9k (P9-1.5.5 升级) | LARGE_DAG_THRESHOLD=20 auto-fallback | 53x (21 节点 175s → 3.3s) | 17s |
| v0.6.9l (P9-1.5.5 升级) | OLS refutation 路径 (3500x) | 3500x (vs DoWhy 21 节点) | 17s |
| v0.7.0 (batch 4) | DAG 21 → 35 节点 | 仍 OLS path | 14s |
| v0.7.5 | Pydot cache + LRU report cache | 1.6x | 8.6s |
| v0.8.0 (batch 5) | DAG 35 → 47 节点 + PC cache | 1.3x | 9.0s |

### 5.2 当前性能 (v0.8.5, 47 节点)

```
daily_report cold run:
  Step 1 fetch:        0.0s (skip, 实际 30s)
  Step 2 attribution:  0.7s
  Step 3 residual:     0.9s
  Step 4 markdown:     5.1s  (含 PC + CATE cold)
  Step 5 html:         skip
  Step 6 dashboard:    skip
  Step 7 alerts:       0.3s
  Step 8 causal:       0.06s (cache hit, 跨 step 共享)
  Total:               ~9.0s
```

### 5.3 性能 profile 工具

```bash
# 全 profile
python -c "
import time, os
os.environ['US_STOCK_CAUSAL_FAST'] = '1'
from examples.daily_report import run_daily_report
t0 = time.time()
r = run_daily_report(date_str='2026-08-08', skip_fetch=True, skip_html=True, skip_dashboard=True, verbose=False)
print(f'Total: {time.time()-t0:.2f}s')
for n, s in r['steps'].items():
    print(f'  {n}: {s[\"elapsed_s\"]}s')
"

# 单 step profile
python -c "
import time
from src import causal as cm
cm.clear_caches()
cfg = cm.load_dag_config()
data = cm.load_dag_data(cfg=cfg)
t0 = time.time()
cm.causal_query('VIX', 'QQQ', n_refutations=1)
print(f'L2 cold: {time.time()-t0:.2f}s')
t0 = time.time()
cm.causal_query('VIX', 'QQQ', n_refutations=1)
print(f'L2 warm: {time.time()-t0:.3f}s')
"
```

### 5.4 未来优化方向 (V1.0 后)

| 优化 | 估计省 | 复杂度 |
|---|---|---|
| PC algorithm 异步 (跟 CATE 并行) | 0.5-1s | 中 (asyncio) |
| CATE n_quantiles 3 → 2 (daily report) | 0.5s | 低 (1 行) |
| GDELT retry 推 v0.7.0 (跟 1h cache) | 35s 等待 (但 daily cron 不会卡) | 低 |
| 4 国债 yield curve 跨 query 共享 fit | 0.3s | 中 |

---

## 6. Pearl 3 层因果 (P9)

### 6.1 三层因果阶梯

```
L1 关联 (P(Y|X)):  "看到" — Phase 2 attribution 已写在每段报告里
   ↓
L2 干预 (P(Y|do(X))):  "做" — src/causal.py:causal_query()
   ↓
L3 反事实 (P(Y_x|X',Y')):  "如果当初" — src/causal.py:counterfactual_query()
```

### 6.2 L2 do-calculus 实现

```python
# src/causal.py
def causal_query(treatment, outcome, data, cfg, n_refutations=1, refute_method="auto"):
    """Pearl L2: 4 步 (model → identify → estimate → refute)"""
    g = load_dag_graph(cfg)
    n_nodes = g.number_of_nodes()

    # Step 1+2: OLS (绕开 DoWhy linear_regression 已知 bug)
    X = sm.add_constant(data[[treatment]])
    y = data[outcome]
    ols = sm.OLS(y, X).fit()
    ate = ols.params[treatment]  # ATE
    p_value = ols.pvalues[treatment]

    # Step 3: refutation
    if n_refutations > 0:
        if n_nodes >= LARGE_DAG_THRESHOLD or refute_method == "ols":
            # OLS path (3500x 加速, 完全跳过 DoWhy)
            refutation = _refute_with_ols(treatment, outcome, data, g, ate, n_refutations)
        else:
            # DoWhy path (小 DAG 审稿场景)
            model = CausalModel(data, treatment, outcome, graph=g)
            identified = model.identify_effect()
            refutation = _get_refutation_cached(treatment, outcome, data, g, n_refutations)

    return CausalEffect(estimate=ate, p_value=p_value, refutation=refutation, method=...)
```

### 6.3 L3 反事实实现

```python
# src/causal.py
def counterfactual_query(date, treatment, outcome, cf_value, data, cfg, method="scm"):
    """Pearl L3: 严格反事实 (SCM) 或近似 (EconML)"""
    g = load_dag_graph(cfg)
    if method == "scm":
        # gcm.InvertibleSCM (严格, P9-1.3)
        scm = gcm.InvertibleStructuralCausalModel(g)
        scm.fit(data)
        cf = scm.counterfactual(treatment=treatment, outcome=outcome,
                                  observed={treatment: actual_value},
                                  intervention={treatment: cf_value})
    else:
        # econml CausalForestDML (近似)
        est = CausalForestDML(...)
        est.fit(...)
        cate = est.effect(X_query)
    return CounterfactualResult(date, actual_outcome, counterfactual_outcome, delta)
```

### 6.4 DAG 验证 (P9-1.1)

```python
# PC algorithm 跟手工 DAG 对比
pc_dag = discover_dag_pc(data, alpha=0.05)  # 47 节点 ~1.5s, cache hit 0s
manual_dag = load_dag_graph(cfg)
cmp = compare_dags(manual_dag, pc_dag)
# overlap_rate: 47 节点 ~3.5% (172 边 / ~50 PC 边, 重叠 6 边)
```

### 6.5 CATE 异质性 (P9-1.4)

```python
# 按 heterogeneity_var 切 N 群, 共享 _FIT_CACHE 跨群
cate = cate_heterogeneity("VIX", "QQQ", "VIX", n_quantiles=3, data, cfg)
# q0 (low VIX):  CATE = -0.0505
# q1 (mid VIX):  CATE = -0.0388
# q2 (high VIX): CATE = -0.0368
# 异质性比: 1.37x (低 VIX 群强 37%)
```

---

## 7. 扩展点

### 7.1 加新 macro / industry / commodity

```yaml
# 1. config/tickers.yaml 加 ticker
sectors:
  - {symbol: XLU, gics: "Utilities"}

# 2. 拉数据
python examples/fetch_all.py

# 3. config/causal_dag.yaml 加节点 + 边 (DAG 仍 acyclic)
XLU [label="XLU (Utility)"];
XLU -> DIA;  # 公用事业 → 道指

# 4. 验证
python -c "from src.causal import load_dag_graph; import networkx as nx; g = load_dag_graph(); print('Acyclic:', nx.is_directed_acyclic_graph(g))"

# 5. 跑 daily
python examples/daily_report.py --skip-fetch
```

### 7.2 加新 L2 因果 query

```python
# 在 examples/daily_report.py:step_causal 加新 query
eff = causal_mod.causal_query("DXY", "QQQ", n_refutations=1, data=data, cfg=cfg)
print(f"DXY → QQQ ATE: {eff.estimate:.4f}")
```

### 7.3 加新异常 check

```python
# src/checks/my_alert.py
def check(date_str: str) -> list[dict]:
    """我的新 check"""
    alerts = []
    # ... 检查逻辑
    if bad_condition:
        alerts.append(alert_logger.make_alert(
            alert_type="my_alert",
            subject="...",
            message="...",
            severity="warning",
        ))
    return alerts

# examples/daily_report.py:step_check_alerts 加
from src.checks import my_alert
checks = [..., ("my_alert", my_alert.check)]
```

### 7.4 加新 L3 反事实方法

```python
# src/causal.py
def counterfactual_query(date, treatment, outcome, cf_value, data, cfg, method="scm"):
    if method == "my_method":
        # 你的实现
        pass
    elif method == "scm":
        # gcm.InvertibleSCM
        pass
    elif method == "econml":
        # CausalForestDML
        pass
```

### 7.5 加新 cache 类型

```python
# src/causal.py
def load_dag_graph(cfg):
    # 加新 cache
    cache_key = compute_key(cfg)
    if cache_key in _NEW_CACHE:
        return _NEW_CACHE[cache_key]
    g = parse_graph(cfg)
    _NEW_CACHE[cache_key] = g
    return g

# 同步加 clear_caches()
def clear_caches():
    n_new = len(_NEW_CACHE)
    _NEW_CACHE.clear()
    return {..., "new_cleared": n_new}
```

### 7.6 改 daily_report 编排

```python
# examples/daily_report.py
def run_daily_report(date_str, skip_fetch=False, skip_md=False, ...):
    steps = {}
    steps["fetch"] = step_fetch(skip=skip_fetch)
    # ... 8 步
    return {"date": date_str, "elapsed_s": total, "steps": steps}
```

### 7.7 加新 sector weights 来源

```python
# src/sector_weights_live.py
def load_live_or_static(date=None, use_cache=True):
    """目前 cp config/sector_weights.json 到 cache. 加新源:"""
    if source == "openbb_etf":
        return openbb_etf_pull(date)
    elif source == "static":
        return static_load()
```

---

## 8. 测试架构

### 8.1 测试层级

| 层级 | 文件 | 数量 | 跑法 |
|---|---|---|---|
| smoke | `tests/test_smoke.py` | 80 (v0.8.5) | `python tests/test_smoke.py` (~180s) |
| pytest | 同上 | 同上 | `python -m pytest tests/test_smoke.py -v` |

### 8.2 测试分类

| 类别 | 数量 | 范围 |
|---|---|---|
| 模块 import + 关键函数 | 10 | 13 个 src module 都能 import |
| 报告结构 (5 段制) | 5 | 顶部情绪 + 5 段 × 4 指数 |
| K 线 + 事件 | 12 | 5 SMA / 200 SMA / 事件线 / SVG / 52w padding |
| Performance dashboard | 2 | render table + HTML |
| Daily report step 1-8 | 8 | 端到端 8 步 |
| residual regression (P7-5) | 2 | 残差 baseline + 漂移 |
| Check alerts (P8-1~6) | 6 | 5 类 check + toast |
| Pearl 因果 (P9) | 15 | DAG load / L2 / L3 / CATE / PC algorithm / counterfactual |
| P8-5 tenacity | 2 | retry + data.fetch |
| v0.7.5 cache | 2 | Pydot + LRU report |
| v0.8.0 PC cache | 1 | PC algorithm date cache |
| v0.8.5 DAG 端到端 | 5 | L1/L2/L3/CATE/DAG acyclic |
| v0.8.5 backtest | 2 | Q1 2025 + 残差漂移 |
| v0.8.5 辅助 | 7 | perf / cache invalidation / 配对 / yield curve |
| **总** | **80** | |

### 8.3 测试运行

```bash
# 全跑
python tests/test_smoke.py

# pytest 模式 (详细输出)
python -m pytest tests/test_smoke.py -v

# 单 test
python -m pytest tests/test_smoke.py::test_dag_acyclic_47_nodes_v085_p92 -v

# 性能断言测试
python -m pytest tests/test_smoke.py::test_full_perf_47_nodes_v085_p105 -v
```

### 8.4 测试阈值自适应

许多测试有 OS load 余量, 例如:

```python
cache_threshold = 0.20 + 0.02 * n_nodes  # 21 节点 0.62s, 47 节点 1.14s
assert t2 < cache_threshold, f"cache hit 应 < {cache_threshold}s"
```

阈值随节点数线性缩放, 避免 OS load 抖动导致 flake.

---

## 附录: 性能里程碑 (v0.6.9 → v0.8.5)

| 版本 | daily cron | L2 21 节点 | L2 35 节点 | L2 47 节点 |
|---|---|---|---|---|
| v0.6.9 (基线) | 82s | 175s (3 重 DoWhy) | — | — |
| v0.6.9f (P9-1.5.5) | 17s | 17s (1 重 DoWhy) | — | — |
| v0.6.9k (auto-fallback) | 17s | 3.3s (0 重) | — | — |
| v0.6.9l (OLS path) | 17s | 50ms (3 重 OLS) | — | — |
| v0.7.0 (batch 4) | 14s | — | 2.5s (含 DoWhy build) | — |
| v0.7.5 (cache) | 8.6s | — | 1.1s | — |
| v0.8.0 (batch 5) | 9.0s | — | — | 1.1s (含 DoWhy build) |
| v0.8.5 (测试 80+) | 9.0s | — | — | 1.1s |

每次性能提升都有 commit msg 详细分析, 详见 `CHANGELOG.md` 对应版本段.
