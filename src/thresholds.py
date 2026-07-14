"""
src/thresholds.py - 关键阈值检测

Phase 2.1 (P2-6) 关键阈值:
  - SMA20 / SMA50 / SMA200 (短期/中期/长期均线)
  - Pivot points (经典 floor trader pivots: P/R1/R2/R3, S1/S2/S3)
  - 52-week high/low
  - 当前位置 (above/below SMA, position in 52w range)

**因果意义**:
  - 200 SMA 是"市场长期情绪分水岭",在 SMA 上方 = 多头,下方 = 空头
  - Pivot R1/R2 是短期阻力,S1/S2 是短期支撑
  - 突破 52w high 是"动能信号",跌破 52w low 是"弱势信号"
  - 这些阈值是"接下来 1-3 个月的关注点",不是"明天的预测"
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = PROJECT_ROOT / "data" / "raw"


def safe_name(symbol: str) -> str:
    return symbol.replace("^", "_").replace("=", "_").replace(".", "_")


def load_prices(symbol: str, layer: str) -> pd.DataFrame:
    safe = safe_name(symbol)
    pq = CACHE_ROOT / layer / f"{safe}.parquet"
    if not pq.exists():
        raise FileNotFoundError(f"{pq} 不存在,先跑 fetch_all.py")
    return pd.read_parquet(pq)


def compute_smas(close: pd.Series, windows: list[int] = None) -> dict[str, float]:
    """
    计算 SMA,返回 {sma_20, sma_50, sma_100, sma_150, sma_200}

    v0.6.0 (P6-6): 默认 windows 从 [20, 50, 200] 扩到 [20, 50, 100, 150, 200]
    100/150 是机构 Gann 周期线 (半年/季度),看图必备。
    """
    if windows is None:
        windows = [20, 50, 100, 150, 200]
    result = {}
    for w in windows:
        if len(close) >= w:
            result[f"sma_{w}"] = float(close.rolling(w).mean().iloc[-1])
        else:
            result[f"sma_{w}"] = float("nan")
    return result


def position_vs_sma(close: float, sma: float) -> dict:
    """价格相对 SMA 的位置"""
    if sma == 0 or pd.isna(sma):
        return {"position": "N/A", "pct": None, "above": None}
    pct = (close - sma) / sma * 100
    return {
        "position": "above" if close > sma else "below",
        "pct": round(pct, 2),
        "above": close > sma,
    }


def compute_pivots(df: pd.DataFrame) -> dict[str, float]:
    """
    经典 floor trader pivot points (基于昨日 H/L/C):
      P  = (H + L + C) / 3
      R1 = 2P - L,  S1 = 2P - H
      R2 = P + (H - L),  S2 = P - (H - L)
      R3 = H + 2(P - L),  S3 = L - 2(H - P)
    """
    if len(df) < 2:
        raise ValueError("需要至少 2 天数据计算 pivot")

    # 昨日的 H/L/C
    prev = df.iloc[-2]
    h = float(prev["high"])
    l = float(prev["low"])
    c = float(prev["close"])
    p = (h + l + c) / 3

    return {
        "pivot": round(p, 2),
        "r1": round(2 * p - l, 2),
        "s1": round(2 * p - h, 2),
        "r2": round(p + (h - l), 2),
        "s2": round(p - (h - l), 2),
        "r3": round(h + 2 * (p - l), 2),
        "s3": round(l - 2 * (h - p), 2),
    }


def compute_52w_range(close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
    """52 周 (252 交易日) high/low 和当前在区间的位置"""
    window = 252
    if len(close) < window:
        window = len(close)

    recent_close = close.iloc[-window:]
    recent_high = high.iloc[-window:]
    recent_low = low.iloc[-window:]

    h = float(recent_high.max())
    l = float(recent_low.min())
    last = float(close.iloc[-1])

    if h == l:
        position_pct = 50.0
    else:
        position_pct = round((last - l) / (h - l) * 100, 1)

    return {
        "high": round(h, 2),
        "low": round(l, 2),
        "current": round(last, 2),
        "position_pct": position_pct,  # 0% = 52w low, 100% = 52w high
        "pct_from_high": round((last - h) / h * 100, 2) if h > 0 else None,
        "pct_from_low": round((last - l) / l * 100, 2) if l > 0 else None,
    }


def get_thresholds(symbol: str, layer: str = "indices") -> dict:
    """
    一次性算出某 ticker 的所有关键阈值

    Returns:
        {
            'symbol': 'QQQ',
            'date': '2026-07-10',
            'last_close': 725.5,
            'smas': {'sma_20': 720.0, 'sma_50': 710.0, 'sma_200': 680.0},
            'vs_sma': {'sma_20': {'position': 'above', 'pct': 0.76}, ...},
            'pivots': {'pivot': 720.0, 'r1': 730.0, 's1': 715.0, ...},
            'range_52w': {'high': 750, 'low': 600, 'current': 725.5, 'position_pct': 83.3, ...}
        }
    """
    df = load_prices(symbol, layer)
    close = df["close"]
    high = df["high"]
    low = df["low"]

    smas = compute_smas(close)
    vs_sma = {k: position_vs_sma(float(close.iloc[-1]), v) for k, v in smas.items() if not pd.isna(v)}
    pivots = compute_pivots(df)
    range_52w = compute_52w_range(close, high, low)

    return {
        "symbol": symbol,
        "date": str(close.index[-1].date()),
        "last_close": round(float(close.iloc[-1]), 2),
        "smas": {k: round(v, 2) for k, v in smas.items()},
        "vs_sma": vs_sma,
        "pivots": pivots,
        "range_52w": range_52w,
    }


if __name__ == "__main__":
    # 自测
    import sys
    for idx in ["DIA", "QQQ", "RSP", "QQQE"]:
        print(f"\n=== {idx} ===")
        t = get_thresholds(idx)
        print(f"last close: ${t['last_close']}")
        print(f"  SMA20:  ${t['smas']['sma_20']} ({t['vs_sma']['sma_20']['position']} {t['vs_sma']['sma_20']['pct']:+.2f}%)")
        print(f"  SMA50:  ${t['smas']['sma_50']} ({t['vs_sma']['sma_50']['position']} {t['vs_sma']['sma_50']['pct']:+.2f}%)")
        print(f"  SMA200: ${t['smas']['sma_200']} ({t['vs_sma']['sma_200']['position']} {t['vs_sma']['sma_200']['pct']:+.2f}%)")
        print(f"  Pivot:  ${t['pivots']['pivot']}, R1 ${t['pivots']['r1']}, S1 ${t['pivots']['s1']}")
        r = t['range_52w']
        print(f"  52w:    high ${r['high']} / low ${r['low']}, position {r['position_pct']}%")
