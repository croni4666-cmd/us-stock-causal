#!/usr/bin/env python3
"""
examples/nvda_counterfactual.py - Phase 9.1 NVDA 专属反事实分析

为 2026-07-27 NVDA 暴跌 (-4.99%) 跑因果归因 + 反事实估计。
DAG 扩展: 在 Phase 9.0 (macro -> 4 指数) 基础上加:
  - NVDA (target)
  - 半导体板块 peers: AMD, SMH, TSM
  - 替代效应: AAPL (AI capex 切换)
  - OIL (CL=F, 同日 -8.55%)

跑 3 件事:
  1. L2 ATE: TNX / VIX / OIL -> NVDA (5y 数据, DoWhy 4 步)
  2. L3 反事实 (Pearl 简化, econml CausalForestDML):
     - 7/27 假设 OIL=0 (油价没跌)
     - 7/27 假设 VIX=0 (恐慌没升)
     - 7/27 假设 AAPL=0 (没"端侧 AI 切换"叙事)
  3. Attribution: 把 NVDA 当日 -4.99% 拆成 macro / sector / catalyst 块

用法: python examples/nvda_counterfactual.py
"""
from __future__ import annotations

import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from pathlib import Path
import io

# UTF-8 强制 (Windows GBK 防御)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---- 抓 NVDA 数据 (yfinance, 代理) ----
from src.proxy import setup_proxy
setup_proxy()
import yfinance as yf
import pandas as pd
import numpy as np

OUT = PROJECT_ROOT / "output"
OUT.mkdir(exist_ok=True)

# === DAG 定义 (手工经济理论) ===
# Nodes: macro [TNX, VIX, OIL] + sector [AMD, SMH, TSM] + substitution [AAPL] + target [NVDA]
# 边 (基于经济理论):
#   - VIX -> NVDA  (恐慌抛售)
#   - TNX -> NVDA  (利率压制估值)
#   - OIL -> VIX   (需求担忧 -> 恐慌)
#   - OIL -> NVDA  (risk-off 联动, NVDA beta > 1)
#   - AMD -> NVDA  (同板块传染)
#   - SMH -> NVDA  (sector ETF 携带)
#   - TSM -> NVDA  (fab 供应链, NVDA 是 TSM 大客户)
#   - AAPL -> NVDA (AI capex 替代效应, AAPL "端侧 AI" 越强, NVDA "云端 capex" 越弱)
#   - unobserved [AI_capex_concern] -> NVDA / AAPL (latent confounder, 不可观测)
#
# 简化: 不加 DXY (7/27 数据没拉到), 不画 mediator (Phase 9.2+ 再加)

DAG_DOT = """
digraph nvda_jul27 {
  // 节点
  TNX [label="^TNX (10Y)"];
  VIX [label="^VIX"];
  OIL [label="CL=F (Oil)"];
  AMD [label="AMD"];
  SMH [label="SMH"];
  TSM [label="TSM"];
  AAPL [label="AAPL"];
  NVDA [label="NVDA (target)"];

  // 边
  TNX -> NVDA;
  VIX -> NVDA;
  OIL -> VIX;
  OIL -> NVDA;
  AMD -> NVDA;
  SMH -> NVDA;
  TSM -> NVDA;
  AAPL -> NVDA;
}
"""

# === Tickers 配置 ===
TICKERS = {
    "TNX": "^TNX",
    "VIX": "^VIX",
    "OIL": "CL=F",
    "AMD": "AMD",
    "SMH": "SMH",
    "TSM": "TSM",
    "AAPL": "AAPL",
    "NVDA": "NVDA",
}

CACHE_DIR = PROJECT_ROOT / "data" / "raw" / "nvda_cf_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _fetch_one(node, sym, period):
    """拉一个 ticker, 写 cache"""
    import time
    cache_p = CACHE_DIR / f"{node}.parquet"
    # 7 天内 cache 直接读
    if cache_p.exists():
        age_days = (pd.Timestamp.now() - pd.Timestamp.fromtimestamp(cache_p.stat().st_mtime)).days
        if age_days < 7:
            log_ret = pd.read_parquet(cache_p)
            if len(log_ret) > 100:
                return node, log_ret
    t0 = time.time()
    try:
        h = yf.Ticker(sym).history(period=period, interval="1d")
        if len(h) < 100:
            return node, None
        c = h["Close"].sort_index()
        log_ret = np.log(c / c.shift(1)).dropna()
        log_ret.to_frame("log_ret").to_parquet(cache_p)
        print(f"  [fetch] {sym:6s} -> {node:6s}  rows={len(log_ret):4d}  last={c.index[-1].strftime('%Y-%m-%d')}  1d={log_ret.iloc[-1]*100:+.2f}%  ({time.time()-t0:.1f}s)")
        return node, log_ret
    except Exception as e:
        print(f"  [err] {sym}: {e}  ({time.time()-t0:.1f}s)")
        return node, None


def load_nvda_dag_data(period="2y"):
    """从 yfinance 拉 9 ticker 2y 日线, 算 log return, inner join 对齐."""
    from concurrent.futures import ThreadPoolExecutor

    print(f"[load] 从 yfinance 拉 {len(TICKERS)} ticker, period={period} (并发 4)")
    raw = {}
    # 并发拉取 (yfinance I/O bound)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_fetch_one, n, s, period) for n, s in TICKERS.items()]
        for f in futures:
            node, log_ret = f.result()
            if log_ret is not None:
                raw[node] = log_ret

    if not raw:
        raise RuntimeError("[load] 无 ticker 加载成功")

    # 期货/股票交易日历可能错位 (CL=F 比 SPY 多 ~2 天), 用 outer + ffill
    aligned = pd.concat(raw.values(), axis=1, join="outer")
    aligned.columns = list(raw.keys())
    aligned = aligned.sort_index().ffill().dropna(how="any")
    print(f"[load] 对齐后: {len(aligned)} 个交易日, 范围 {aligned.index[0].date()} ~ {aligned.index[-1].date()}")
    return aligned


def parse_dag(dot: str):
    """解析 DOT 成 networkx DiGraph"""
    import networkx as nx
    import pydot
    g = nx.DiGraph(nx.drawing.nx_pydot.from_pydot(pydot.graph_from_dot_data(dot)[0]))
    assert nx.is_directed_acyclic_graph(g), "DAG 有环!"
    return g


def causal_query_ate(treatment, outcome, data, g):
    """Pearl 4 步: identify + estimate (用 statsmodels OLS 绕 DoWhy bug) + refute"""
    import pydot, networkx as nx
    from dowhy import CausalModel
    import statsmodels.api as sm

    # DoWhy 主要用于 identify (DAG 验证) + refute
    try:
        # DoWhy 要 nx.DiGraph 或 dot 文件路径
        model = CausalModel(
            data=data.reset_index(drop=True),  # 去掉 date index, DoWhy 不接受
            treatment=treatment,
            outcome=outcome,
            graph=g,
            common_causes=None,
        )
        identified = model.identify_effect(proceed_when_unidentifiable=True)

        # estimate 用 OLS 绕开 DoWhy linear_regression estimator 已知 bug
        X = sm.add_constant(data[treatment])
        y = data[outcome]
        ols = sm.OLS(y, X).fit()
        ate = float(ols.params[treatment])
        p_val = float(ols.pvalues[treatment])
        std_err = float(ols.bse[treatment])

        # refute 用 DoWhy
        try:
            est_dowhy = model.estimate_effect(
                identified,
                method_name="backdoor.linear_regression",
                control_value=0,
                treatment_value=1,
            )
            ref1 = model.refute_estimate(
                identified, est_dowhy, method_name="random_common_cause"
            )
            ref2 = model.refute_estimate(
                identified, est_dowhy, method_name="placebo_treatment_refuter"
            )
            ref3 = model.refute_estimate(
                identified, est_dowhy, method_name="data_subset_refuter"
            )
            refutation = {
                "random_common_cause": {"new_effect": float(ref1.new_effect)},
                "placebo": {"new_effect": float(ref2.new_effect)},
                "data_subset": {"new_effect": float(ref3.new_effect)},
            }
        except Exception as e:
            refutation = {"refute_error": str(e)}

        return {
            "ate": ate,
            "p_value": p_val,
            "std_err": std_err,
            "estimand": str(identified),
            "refutation": refutation,
            "n_obs": len(data),
        }
    except Exception as e:
        return {"error": str(e), "ate": np.nan, "p_value": np.nan}


def counterfactual_query_cf(date, treatment, outcome, cf_value, data, g):
    """Pearl L3 简化反事实: 用 CausalForestDML 算 CATE, 推 CF.
    公式: counterfactual_outcome = actual_outcome + CATE * (cf_value - actual_treatment)
    注: 严格 L3 需要 SCM, 这里 CATE 是简化近似.
    """
    from econml.dml import CausalForestDML
    from sklearn.ensemble import RandomForestRegressor

    # 选其他 macro + sector 作 controls (排除 treatment 和 outcome)
    controls = [c for c in data.columns if c not in (treatment, outcome)]

    # DoWhy DAG 隐含的 backdoor set 简化: controls
    X = data[controls].values
    T = data[treatment].values
    Y = data[outcome].values

    est = CausalForestDML(
        model_y=RandomForestRegressor(n_estimators=20, max_depth=4, random_state=42),
        model_t=RandomForestRegressor(n_estimators=20, max_depth=4, random_state=42),
        n_estimators=100,
        random_state=42,
    )
    est.fit(Y=Y, T=T, X=X, W=X)

    date_ts = pd.Timestamp(date)
    if date_ts not in data.index:
        idx = data.index.get_indexer([date_ts], method="ffill")[0]
        if idx < 0:
            return {"error": f"{date} 找不到"}
        date_ts = data.index[idx]
    actual_t = float(data.loc[date_ts, treatment])
    actual_y = float(data.loc[date_ts, outcome])
    x_q = data.loc[[date_ts], controls].values
    cate = float(est.effect(x_q))
    delta = cate * (cf_value - actual_t)
    cf_y = actual_y + delta
    return {
        "actual_treatment": actual_t,
        "actual_outcome": actual_y,
        "counterfactual_treatment": cf_value,
        "counterfactual_outcome": cf_y,
        "delta": delta,
        "cate": cate,
    }


def main():
    print("=" * 70)
    print("Phase 9.1: NVDA 7/27 暴跌 - 因果归因 + 反事实")
    print("=" * 70)

    # ---- 1. 加载数据 + DAG ----
    data = load_nvda_dag_data(period="2y")
    g = parse_dag(DAG_DOT)
    print(f"\nDAG: {len(g.nodes)} 节点, {len(g.edges)} 边")
    print("  Nodes:", list(g.nodes))
    print("  Edges:", [(u, v) for u, v in g.edges])

    # ---- 2. L2 ATE: macro -> NVDA ----
    print("\n" + "=" * 70)
    print("L2 干预: 5y 平均处理效应 (Pearl 4 步: identify + estimate + refute)")
    print("=" * 70)
    ate_results = {}
    for t in ["VIX", "TNX", "OIL"]:
        r = causal_query_ate(t, "NVDA", data, g)
        ate_results[t] = r
        if "ate" in r and not np.isnan(r["ate"]):
            print(f"\n  {t} -> NVDA:")
            print(f"    ATE  = {r['ate']:+.4f}  ({r['ate']*100:+.2f}% NVDA / +1% {t})")
            print(f"    p    = {r['p_value']:.4f}  (sig={'YES' if r['p_value']<0.05 else 'no'})")
            print(f"    SE   = {r['std_err']:.4f}")
            for k, v in r.get("refutation", {}).items():
                if isinstance(v, dict) and "new_effect" in v:
                    print(f"    refute {k:20s}: {v['new_effect']:+.4f}")
        else:
            print(f"\n  {t} -> NVDA: ERROR {r.get('error')}")

    # ---- 3. L3 反事实: 2026-07-27 ----
    target_date = "2026-07-27"
    print("\n" + "=" * 70)
    print(f"L3 反事实 ({target_date}): Pearl 简化, CausalForestDML CATE 近似")
    print("=" * 70)

    cf_results = {}
    # CF 1: OIL 不变 (假设 7/27 油价没有 -8.55% 暴跌)
    cf_results["OIL=0"] = counterfactual_query_cf(target_date, "OIL", "NVDA", 0.0, data, g)
    # CF 2: VIX 不变 (假设 7/27 恐慌没有 +0.48% 升)
    cf_results["VIX=0"] = counterfactual_query_cf(target_date, "VIX", "NVDA", 0.0, data, g)
    # CF 3: AAPL 不变 (假设 7/27 端侧 AI 切换叙事没有发生, AAPL 不涨)
    cf_results["AAPL=0"] = counterfactual_query_cf(target_date, "AAPL", "NVDA", 0.0, data, g)

    for k, r in cf_results.items():
        if "error" not in r:
            print(f"\n  {k}:")
            print(f"    实际 {r['actual_treatment']*100:+5.2f}% (treatment) / {r['actual_outcome']*100:+5.2f}% (NVDA)")
            print(f"    反事实 treatment: {r['counterfactual_treatment']*100:+5.2f}%")
            print(f"    反事实 NVDA: {r['counterfactual_outcome']*100:+5.2f}%")
            print(f"    差值: {r['delta']*100:+.2f}% (CATE={r['cate']:+.3f})")
        else:
            print(f"\n  {k}: {r['error']}")

    # ---- 4. Attribution 拆解 ----
    print("\n" + "=" * 70)
    print("Attribution: NVDA 7/27 实际 -4.99% 拆解 (Pearl 视角)")
    print("=" * 70)
    actual_nvda = float(data.loc[target_date, "NVDA"]) * 100 if target_date in str(data.index) else None
    if target_date in [d.strftime("%Y-%m-%d") for d in data.index]:
        target_ts = pd.Timestamp(target_date)
        actual_nvda = float(data.loc[target_ts, "NVDA"]) * 100
        actual_oil = float(data.loc[target_ts, "OIL"]) * 100
        actual_vix = float(data.loc[target_ts, "VIX"]) * 100
        actual_aapl = float(data.loc[target_ts, "AAPL"]) * 100
        actual_tnx = float(data.loc[target_ts, "TNX"]) * 100
        actual_smh = float(data.loc[target_ts, "SMH"]) * 100
        actual_amd = float(data.loc[target_ts, "AMD"]) * 100
        actual_tsm = float(data.loc[target_ts, "TSM"]) * 100

        print(f"  日期: {target_date}")
        print(f"  NVDA 实际: {actual_nvda:+.2f}%")
        print(f"  ---")
        print(f"  各 treatment 当日实际值:")
        for k, v in [("OIL", actual_oil), ("VIX", actual_vix), ("AAPL", actual_aapl),
                     ("TNX", actual_tnx), ("SMH", actual_smh), ("AMD", actual_amd), ("TSM", actual_tsm)]:
            print(f"    {k:6s}  1d={v:+.2f}%")
        print(f"  ---")
        print(f"  反事实归因 (假设 treatment=0):")
        if "delta" in cf_results.get("OIL=0", {}):
            print(f"    OIL 不跌 (0%):   NVDA 变成 {cf_results['OIL=0']['counterfactual_outcome']*100:+.2f}% "
                  f"(差 {cf_results['OIL=0']['delta']*100:+.2f}%)")
            print(f"    VIX 不升 (0%):   NVDA 变成 {cf_results['VIX=0']['counterfactual_outcome']*100:+.2f}% "
                  f"(差 {cf_results['VIX=0']['delta']*100:+.2f}%)")
            print(f"    AAPL 不涨 (0%):  NVDA 变成 {cf_results['AAPL=0']['counterfactual_outcome']*100:+.2f}% "
                  f"(差 {cf_results['AAPL=0']['delta']*100:+.2f}%)")

            total_explained = sum(
                cf_results[k]["delta"] for k in ["OIL=0", "VIX=0", "AAPL=0"]
            ) * 100
            print(f"  ---")
            print(f"  OIL+VIX+AAPL 三个 CF 差值合计: {total_explained:+.2f}%")
            print(f"  (剩余 = NVDA 实际 - 解释部分 = 板块传染/AI capex 担忧/其他)")

    print("\n" + "=" * 70)
    print("Phase 9.1 done")
    print("=" * 70)

    # ---- 5. 写报告到 file (UTF-8, 防 PowerShell GBK 崩) ----
    report_path = OUT / "nvda_cf_2026-07-27.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Phase 9.1: NVDA 7/27 暴跌反事实分析\n")
        f.write(f"=" * 70 + "\n")
        f.write(f"Date: {target_date}\n")
        f.write(f"Data: {len(data)} trading days, period 2y\n")
        f.write(f"DAG: {len(g.nodes)} nodes, {len(g.edges)} edges\n\n")
        f.write(f"L2 ATE (Pearl 4 步):\n")
        for t, r in ate_results.items():
            if "ate" in r and not np.isnan(r["ate"]):
                f.write(f"  {t} -> NVDA:  ATE={r['ate']:+.4f}  p={r['p_value']:.4f}  SE={r['std_err']:.4f}\n")
                for k, v in r.get("refutation", {}).items():
                    if isinstance(v, dict) and "new_effect" in v:
                        f.write(f"    refute {k}: new_effect={v['new_effect']:+.4f}\n")
        f.write(f"\nL3 反事实 ({target_date}):\n")
        for k, r in cf_results.items():
            if "error" not in r:
                f.write(f"  {k}:\n")
                f.write(f"    actual_t={r['actual_treatment']*100:+.2f}%  actual_y={r['actual_outcome']*100:+.2f}%\n")
                f.write(f"    cf_t={r['counterfactual_treatment']*100:+.2f}%  cf_y={r['counterfactual_outcome']*100:+.2f}%\n")
                f.write(f"    delta={r['delta']*100:+.2f}%  CATE={r['cate']:+.3f}\n")
    print(f"\n报告写入: {report_path}")


if __name__ == "__main__":
    main()
