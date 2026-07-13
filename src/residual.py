"""
src/residual.py - 残差分析

Phase 2.1 (P2-4) 残差深入:
  - 跟踪 attribution 残差时间序列
  - 检测异常日 (|residual| > N σ)
  - 评估 weights 稳定性 (mean ≈ 0, std 小)
  - 给出"weights 是否需更新"建议

**为什么重要**:
  残差大 = 2 个可能:
    A. weights 过时 (predictable, 季度更新可修复)
    B. 特殊事件 (财报/政策/反垄断,要调查)
  区分 A vs B: 残差时间序列是否系统偏移 (A) vs 单日异常 (B)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from src.attribution import attribute_index


def compute_residual_timeseries(
    index_symbol: str,
    lookback_days: int = 60,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    算指定指数最近 N 天的残差时间序列

    Returns: DataFrame with columns [date, actual, predicted, residual]
    """
    # 拉 2y 数据,再切片
    from src.attribution import get_sector_returns
    rets = get_sector_returns("2024-01-01", end_date or pd.Timestamp.now().strftime("%Y-%m-%d"))

    if index_symbol not in rets.columns:
        raise ValueError(f"{index_symbol} 不在 returns 里")
    idx_rets = rets[index_symbol].dropna()

    # 取最近 N 天
    window = idx_rets.iloc[-lookback_days:]

    results = []
    for date in window.index:
        r = attribute_index(index_symbol, date=str(date.date()), lookback_days=1)
        results.append({
            "date": date.date(),
            "actual_pct": r["actual_return_pct"],
            "predicted_pct": r["predicted_return_pct"],
            "residual_pct": r["residual_pct"],
        })

    return pd.DataFrame(results)


def detect_anomalies(
    residuals: pd.DataFrame,
    threshold_std: float = 2.0,
) -> pd.DataFrame:
    """
    找 |residual| > N σ 的异常日
    """
    mean = residuals["residual_pct"].mean()
    std = residuals["residual_pct"].std()
    threshold = threshold_std * std

    anomalies = residuals[residuals["residual_pct"].abs() > threshold].copy()
    anomalies["z_score"] = (anomalies["residual_pct"] - mean) / std
    return anomalies


def assess_weight_health(residuals: pd.DataFrame) -> dict:
    """
    评估 weights 健康度:
      - mean residual: 接近 0 = 权重无系统偏移
      - std residual: 小 = 权重准
      - 残差 vs 0 的 t-test p-value: 大 = 残差均值与 0 无显著差异
    """
    from scipy import stats

    mean = float(residuals["residual_pct"].mean())
    std = float(residuals["residual_pct"].std())
    n = len(residuals)

    if n < 5:
        t_stat, p_value = 0.0, 1.0
    else:
        t_stat, p_value = stats.ttest_1samp(residuals["residual_pct"], 0)

    # 评估
    if abs(mean) < 0.05 and p_value > 0.1:
        health = "ok"
        advice = "weights 健康,无需更新"
    elif abs(mean) < 0.15 and p_value > 0.05:
        health = "watch"
        advice = "权重有轻微偏差,继续观察"
    else:
        health = "stale"
        advice = "权重可能过时,建议季度更新"

    return {
        "mean_residual_pct": round(mean, 4),
        "std_residual_pct": round(std, 4),
        "n_days": n,
        "t_stat": round(float(t_stat), 3),
        "p_value": round(float(p_value), 4),
        "health": health,
        "advice": advice,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    for idx in ["DIA", "QQQ", "RSP", "QQQE"]:
        print(f"\n=== {idx} 残差分析 (60 天) ===")
        ts = compute_residual_timeseries(idx, lookback_days=60)
        h = assess_weight_health(ts)
        print(f"  mean:   {h['mean_residual_pct']:+.3f}%")
        print(f"  std:    {h['std_residual_pct']:.3f}%")
        print(f"  t-test: t={h['t_stat']}, p={h['p_value']}")
        print(f"  health: {h['health']} ({h['advice']})")
        anomalies = detect_anomalies(ts, threshold_std=2.0)
        if len(anomalies):
            print(f"  anomalies (|z|>2): {len(anomalies)} 天")
            for _, a in anomalies.head(3).iterrows():
                print(f"    {a['date']} actual {a['actual_pct']:+.2f}% / predicted {a['predicted_pct']:+.2f}% / residual {a['residual_pct']:+.2f}% (z={a['z_score']:+.2f})")
        else:
            print(f"  anomalies: 无")
