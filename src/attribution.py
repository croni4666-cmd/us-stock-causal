"""
src/attribution.py - 归因分解

v0.3.0 基础版: 用 sector weights 直接计算,不拟合。
  predicted_return = Σ_s weight_s × sector_s_return
  residual = actual - predicted
  residual 越小,归因越准 (理论上 < 0.5% daily)

Phase 2.1 计划加 regression-based attribution:
  r_index = α + β_sector × r_sector + γ × Δyield + δ × ΔVIX + ε
  (加入 macro 因子,残差会更小,归因更全)
"""
from __future__ import annotations

import json
import functools
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from src.returns import compute_returns, cumulative_return

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = PROJECT_ROOT / "data" / "raw"
WEIGHTS_PATH = PROJECT_ROOT / "config" / "sector_weights.json"
SECTOR_TICKERS = ["XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU", "XLB", "XLRE", "XLC"]


def load_sector_weights(use_live_cache: bool = True) -> dict:
    """读 sector weights — P7-4 加 1d cache 选项

    Args:
        use_live_cache: True (默认) 优先读 data/cache/sector_weights_live_<date>.json,
                       过期走 pull (cp config/sector_weights.json). False 直接读 config
    """
    if use_live_cache:
        from src.sector_weights_live import load_live_or_static
        return load_live_or_static()
    with open(WEIGHTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_prices(symbol: str, layer: str) -> pd.Series:
    """从 parquet 读 close 列

    v0.9.5 RC1 prep (P10-1 性能优化): @lru_cache 避免重复读 parquet
    - 1st call: ~0.05s (pd.read_parquet + Series slice)
    - 2nd call: < 1ms (lru_cache 命中)
    - daily_report 12+12=24 次 attribute_index 调用 → 只第 1 次真读
    - cache 跟 process 同寿, daily cron 1 process 1 run 收益最大
    """
    safe = symbol.replace("^", "_").replace("=", "_").replace(".", "_")
    pq = CACHE_ROOT / layer / f"{safe}.parquet"
    if not pq.exists():
        raise FileNotFoundError(f"{pq} 不存在,先跑 fetch_all.py")
    df = pd.read_parquet(pq)
    return df["close"]


@functools.lru_cache(maxsize=128)
def get_sector_returns(start: str, end: str) -> pd.DataFrame:
    """读 11 行业 + 4 指数,返回 log returns DataFrame

    v0.9.5 RC1 prep (P10-1 性能优化): @lru_cache 跨调用复用
    - 1st call: ~0.5s (15 parquet read + log return compute)
    - 2nd call: < 5ms (lru_cache 命中, 避免重复 read 15 个 parquet)
    - daily_report 12+12=24 次调用, 1 次真算 + 23 次 cache hit
    """
    rets = {}
    for s in SECTOR_TICKERS:
        prices = load_prices(s, "sectors")
        rets[s] = compute_returns(prices.loc[start:end], method="log")
    for idx in ["DIA", "QQQ", "RSP", "QQQE"]:
        prices = load_prices(idx, "indices")
        rets[idx] = compute_returns(prices.loc[start:end], method="log")
    return pd.DataFrame(rets).dropna(how="all")


def attribute_index(
    index_symbol: str,
    date: str | None = None,
    lookback_days: int = 1,
    method: str = "log",
) -> dict:
    """
    归因 1 个指数的当日 / 近期表现

    Args:
        index_symbol: 'DIA' / 'QQQ' / 'RSP' / 'QQQE'
        date: YYYY-MM-DD, None = 最新可用日
        lookback_days: 1 = 当日, 5 = 5 日累计
        method: 'log' / 'simple'

    Returns:
        {
            'index': 'QQQ',
            'date': '2026-07-10',
            'lookback_days': 1,
            'actual_return_pct': 0.5,
            'sector_contributions_pct': {'XLK': 0.4, 'XLF': 0.05, ...},
            'predicted_return_pct': 0.45,
            'residual_pct': 0.05,
            'top_drivers': ['XLK', 'XLC', ...]
        }
    """
    weights_data = load_sector_weights()
    if index_symbol not in weights_data:
        raise ValueError(f"{index_symbol} 没有 sector weights 配置")
    weights = weights_data[index_symbol]
    # 去掉 _meta 和 note
    weights = {k: v for k, v in weights.items() if k in SECTOR_TICKERS}

    # 读 returns
    # 拉 2y 数据,后续按 date 切片
    start_pull = "2024-01-01"
    end_pull = date or datetime.now().strftime("%Y-%m-%d")
    rets = get_sector_returns(start_pull, end_pull)

    if date is None:
        end_date = rets.index[-1]
    else:
        end_date = pd.Timestamp(date)
        if end_date not in rets.index:
            # 用 end_date 之前最近一天
            end_date = rets.index[rets.index <= end_date][-1]

    if lookback_days == 1:
        window = [end_date]
    else:
        idx_pos = rets.index.get_loc(end_date)
        start_pos = max(0, idx_pos - lookback_days + 1)
        window = rets.index[start_pos:idx_pos + 1]

    # 累计归因
    sector_contribs = {}
    for s, w in weights.items():
        if w > 0:
            if lookback_days == 1:
                sector_contribs[s] = w * rets.loc[end_date, s]
            else:
                # 累计: log return 可加
                sector_contribs[s] = w * rets.loc[window, s].sum()

    actual = rets.loc[window, index_symbol].sum() if lookback_days > 1 else rets.loc[end_date, index_symbol]
    predicted = sum(sector_contribs.values())
    residual = actual - predicted

    # 按贡献绝对值排序
    sorted_contribs = dict(sorted(sector_contribs.items(), key=lambda x: -abs(x[1])))

    return {
        "index": index_symbol,
        "date": str(end_date.date()),
        "lookback_days": lookback_days,
        "method": method,
        "actual_return_pct": round(actual * 100, 3),
        "sector_contributions_pct": {s: round(v * 100, 3) for s, v in sorted_contribs.items()},
        "predicted_return_pct": round(predicted * 100, 3),
        "residual_pct": round(residual * 100, 3),
        "top_drivers": list(sorted_contribs.keys())[:3],
    }


def attribute_all_indices(
    date: str | None = None,
    lookback_days: int = 1,
    symbols: list[str] | None = None,
) -> list[dict]:
    """多指数归因 (v0.6.7 P6-3: symbols 参数支持自定义列表)"""
    if symbols is None:
        symbols = ["DIA", "QQQ", "RSP", "QQQE"]
    return [
        attribute_index(idx, date=date, lookback_days=lookback_days)
        for idx in symbols
    ]


if __name__ == "__main__":
    # 自测:DIA 当日
    import sys
    print("=== DIA 当日 ===")
    r = attribute_index("DIA")
    print(f"actual:    {r['actual_return_pct']:+.3f}%")
    print(f"predicted: {r['predicted_return_pct']:+.3f}%")
    print(f"residual:  {r['residual_pct']:+.3f}%")
    print(f"top 3:    {r['top_drivers']}")
    print()
    print("=== QQQ 5 日累计 ===")
    r = attribute_index("QQQ", lookback_days=5)
    print(f"actual:    {r['actual_return_pct']:+.3f}%")
    print(f"predicted: {r['predicted_return_pct']:+.3f}%")
    print(f"residual:  {r['residual_pct']:+.3f}%")
    for s, v in r["sector_contributions_pct"].items():
        if abs(v) > 0.05:
            print(f"  {s}: {v:+.3f}%")
