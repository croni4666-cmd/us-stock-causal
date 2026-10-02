#!/usr/bin/env python3
"""
examples/nvda_cf_lite.py - NVDA 7/27 反事实分析 (轻量版, 不用 DoWhy/econml)

直接用 statsmodels OLS 算 ATE + L3 反事实, 不用 DoWhy/econml 避免 import 慢.
方法学跟 causal.py 一样, 只是省略 DoWhy 包装.

跑法: python examples/nvda_cf_lite.py
"""
from __future__ import annotations
import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.proxy import setup_proxy
setup_proxy()

import yfinance as yf
import pandas as pd
import numpy as np
import statsmodels.api as sm

CACHE = Path(__file__).resolve().parent.parent / "data" / "raw" / "nvda_cf_cache"
OUT = Path(__file__).resolve().parent.parent / "output"

TICKERS = {
    "TNX": "^TNX", "VIX": "^VIX", "OIL": "CL=F",
    "AMD": "AMD", "SMH": "SMH", "TSM": "TSM",
    "AAPL": "AAPL", "NVDA": "NVDA",
}


def load_data(period="2y"):
    """从 cache 读 (无 yfinance 拉取).
    时区修复: 各 ticker yfinance index tz 不一致 (NY -04:00 vs Chicago -05:00),
    先 normalize 到 00:00:00 + tz_localize(None) 转 naive 再 concat.
    """
    raw = {}
    for node, sym in TICKERS.items():
        p = CACHE / f"{node}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if isinstance(df, pd.DataFrame) and "log_ret" in df.columns:
                s = df["log_ret"]
            else:
                s = df.iloc[:, 0]
            # 时区归一: 去掉时分秒, 去掉时区
            s.index = s.index.normalize().tz_localize(None)
            raw[node] = s
    aligned = pd.concat(raw.values(), axis=1, join="outer")
    aligned.columns = list(raw.keys())
    aligned = aligned.sort_index().ffill().dropna(how="any")
    return aligned


def causal_ate_ols(treatment, outcome, data, controls=None):
    """Pearl 简化: 多变量 OLS, treatment 是主解释变量"""
    if controls is None:
        controls = [c for c in data.columns if c not in (treatment, outcome)]
    X = sm.add_constant(data[[treatment] + controls])
    y = data[outcome]
    ols = sm.OLS(y, X).fit()
    return {
        "ate": float(ols.params[treatment]),
        "p_value": float(ols.pvalues[treatment]),
        "std_err": float(ols.bse[treatment]),
        "r2": float(ols.rsquared),
        "n_obs": int(ols.nobs),
        "controls": controls,
    }


def counterfactual_linear(date, treatment, outcome, cf_value, data, controls=None):
    """L3 反事实 (Pearl 简化): cf_outcome = actual + ATE * (cf - actual)"""
    if controls is None:
        controls = [c for c in data.columns if c not in (treatment, outcome)]
    ate_res = causal_ate_ols(treatment, outcome, data, controls)
    date_ts = pd.Timestamp(date)
    if date_ts not in data.index:
        idx = data.index.get_indexer([date_ts], method="ffill")[0]
        date_ts = data.index[idx]
    actual_t = float(data.loc[date_ts, treatment])
    actual_y = float(data.loc[date_ts, outcome])
    delta = ate_res["ate"] * (cf_value - actual_t)
    cf_y = actual_y + delta
    return {
        "actual_t": actual_t, "actual_y": actual_y,
        "cf_t": cf_value, "cf_y": cf_y,
        "delta": delta, "ate": ate_res["ate"], "p_value": ate_res["p_value"],
    }


def main():
    print("=" * 70)
    print("Phase 9.1 LITE: NVDA 7/27 因果归因 + 反事实 (statsmodels OLS)")
    print("=" * 70)

    data = load_data(period="2y")
    print(f"\n[load] {len(data)} trading days, {data.shape[1]} tickers")
    print(f"  范围: {data.index[0].date()} ~ {data.index[-1].date()}")
    print(f"  Tickers: {list(data.columns)}")

    target = "2026-07-27"
    target_ts = pd.Timestamp(target)
    if target_ts not in data.index:
        idx = data.index.get_indexer([target_ts], method="ffill")[0]
        target_ts = data.index[idx]
    print(f"\n[target] {target_ts.date()}")
    print(f"  NVDA actual: {data.loc[target_ts, 'NVDA']*100:+.2f}%")
    for c in ["OIL", "VIX", "AAPL", "TNX", "SMH", "AMD", "TSM"]:
        print(f"  {c:6s} actual: {data.loc[target_ts, c]*100:+.2f}%")

    # === L2 ATE ===
    print("\n" + "=" * 70)
    print("L2 ATE (5y 多变量 OLS, controls = 其他 7 ticker)")
    print("=" * 70)
    ate_results = {}
    for t in ["VIX", "TNX", "OIL", "AMD", "SMH", "TSM", "AAPL"]:
        r = causal_ate_ols(t, "NVDA", data)
        ate_results[t] = r
        sig = "***" if r["p_value"] < 0.001 else ("**" if r["p_value"] < 0.01 else ("*" if r["p_value"] < 0.05 else ""))
        print(f"  {t:5s} -> NVDA:  ATE={r['ate']:+.4f}  p={r['p_value']:.4f}{sig}  SE={r['std_err']:.4f}  R²={r['r2']:.3f}")

    # === L3 Counterfactual ===
    print("\n" + "=" * 70)
    print(f"L3 反事实 ({target_ts.date()}): cf_outcome = actual + ATE * (cf - actual)")
    print("=" * 70)
    cf_results = {}
    for t in ["OIL", "VIX", "AAPL", "AMD", "SMH", "TSM", "TNX"]:
        r = counterfactual_linear(target_ts, t, "NVDA", 0.0, data)
        cf_results[t] = r
        print(f"  {t:5s}=0% :  NVDA {r['actual_y']*100:+.2f}%  ->  CF {r['cf_y']*100:+.2f}%   "
              f"差 {r['delta']*100:+.2f}%  (ATE={r['ate']:+.3f} p={r['p_value']:.3f})")

    # === Attribution ===
    print("\n" + "=" * 70)
    print("Attribution: NVDA 7/27 实际归因拆解")
    print("=" * 70)
    print(f"  实际 NVDA: {data.loc[target_ts, 'NVDA']*100:+.2f}%")
    print()
    print("  假设每个 treatment 都是 0% (即 '假设没有当天变动'):")
    print("  解释力 = delta (CF - actual)")
    explained = 0
    for t in ["OIL", "VIX", "AAPL", "AMD", "SMH", "TSM", "TNX"]:
        d = cf_results[t]["delta"] * 100
        explained += d
        print(f"    {t:5s}  delta = {d:+.2f}%  (实际 {data.loc[target_ts, t]*100:+.2f}%)")
    unexplained = data.loc[target_ts, "NVDA"] * 100 - explained
    print(f"  ---")
    print(f"  7 变量解释力合计: {explained:+.2f}%")
    print(f"  NVDA 实际:      {data.loc[target_ts, 'NVDA']*100:+.2f}%")
    print(f"  剩余 (残差):    {unexplained:+.2f}%  (来自未建模 catalyst / 时间序列动量 / 板块 β)")
    print()
    print("  注: ATE 是简单线性近似, 残差可能高. 7 个 treatment 不能完全 orthogonal,")
    print("      所以 'delta 合计' 跟 '实际值' 之间会有大 gap — 这是线性归因的本质限制.")

    # === 写报告 ===
    report = OUT / "nvda_cf_2026-07-27.txt"
    with open(report, "w", encoding="utf-8") as f:
        f.write(f"Phase 9.1 LITE: NVDA 7/27 因果归因 + 反事实\n")
        f.write(f"Date: {target_ts.date()}\n")
        f.write(f"Data: {len(data)} trading days, {data.shape[1]} tickers\n")
        f.write(f"Method: statsmodels OLS (Pearl 简化, 不用 DoWhy/econml)\n\n")
        f.write(f"=== L2 ATE ===\n")
        for t, r in ate_results.items():
            f.write(f"  {t:5s} -> NVDA:  ATE={r['ate']:+.4f}  p={r['p_value']:.4f}  SE={r['std_err']:.4f}\n")
        f.write(f"\n=== L3 Counterfactual ===\n")
        for t, r in cf_results.items():
            f.write(f"  {t:5s}=0 :  NVDA {r['actual_y']*100:+.2f}%  ->  CF {r['cf_y']*100:+.2f}%   delta {r['delta']*100:+.2f}%\n")
        f.write(f"\n=== Attribution ===\n")
        f.write(f"  7 变量解释力合计: {explained:+.2f}%\n")
        f.write(f"  NVDA 实际:      {data.loc[target_ts, 'NVDA']*100:+.2f}%\n")
        f.write(f"  剩余 (残差):    {unexplained:+.2f}%\n")
    print(f"\n[report] {report}")


if __name__ == "__main__":
    main()
