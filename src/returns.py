"""
src/returns.py - 收益率计算

Phase 2 基础工具:
  - log return: log(p_t / p_{t-1}),可加性,适合 attribution
  - simple return: p_t / p_{t-1} - 1,直观,适合显示

归因用 log (可加: 5-day 累计 log return = 日 log return 之和)
展示用 simple (用户更熟悉 %)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_returns(
    prices: pd.Series | pd.DataFrame,
    method: str = "log",
    periods: int = 1,
) -> pd.Series | pd.DataFrame:
    """
    计算收益率

    Args:
        prices: Series (单 ticker) 或 DataFrame (多列,每个 ticker 一列)
        method: 'log' / 'simple'
        periods: N 日累计 (1 = 日, 5 = 5 日累计)

    Returns:
        同类型,index 跟 prices 一致,前 `periods` 行是 NaN
    """
    if method == "log":
        rets = np.log(prices / prices.shift(periods))
    elif method == "simple":
        rets = prices.pct_change(periods=periods)
    else:
        raise ValueError(f"method must be 'log' or 'simple', got '{method}'")

    return rets


def cumulative_return(rets: pd.Series, method: str = "log") -> float:
    """
    累计收益率 (from a series of period returns)
    log: exp(sum) - 1
    simple: prod(1 + r) - 1
    """
    rets_clean = rets.dropna()
    if len(rets_clean) == 0:
        return 0.0

    if method == "log":
        return float(np.exp(rets_clean.sum()) - 1)
    elif method == "simple":
        return float((1 + rets_clean).prod() - 1)
    else:
        raise ValueError(f"method must be 'log' or 'simple'")


def rolling_return(
    rets: pd.Series,
    window: int = 5,
    method: str = "log",
) -> pd.Series:
    """
    滚动累计收益率 (e.g., 5-day rolling return)
    """
    if method == "log":
        return rets.rolling(window).sum().apply(np.exp).sub(1)
    elif method == "simple":
        return (1 + rets).rolling(window).apply(np.prod, raw=True).sub(1)
    else:
        raise ValueError(f"method must be 'log' or 'simple'")


if __name__ == "__main__":
    # 自测
    import pandas as pd
    prices = pd.Series([100, 102, 101, 105, 108], name="close")
    print("log return:")
    print(compute_returns(prices, method="log").round(4))
    print("\nsimple return:")
    print(compute_returns(prices, method="simple").round(4))
    print(f"\n5-day cumulative (log):   {cumulative_return(compute_returns(prices, 'log')):.4f}")
    print(f"5-day cumulative (simple): {cumulative_return(compute_returns(prices, 'simple')):.4f}")
    print(f"\n3-day rolling return:")
    print(rolling_return(compute_returns(prices, 'log'), window=3).round(4))
