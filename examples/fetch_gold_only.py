"""
fetch_gold_only.py - 临时: 只 fetch 黄金期货 + ETF
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src import proxy  # noqa: F401
from src import data, cache

CACHE_ROOT = PROJECT_ROOT / "data" / "raw"

lookback_days = 730
start_date = (pd.Timestamp.now() - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
print(f"Start: {start_date}")

for sym, layer in [("GC=F", "commodities_futures"), ("GLD", "commodities_spot_etf")]:
    t0 = time.time()
    try:
        df, status = cache.update_or_fetch(
            symbol=sym,
            layer=layer,
            fetcher=data.fetch,
            cache_root=CACHE_ROOT,
            start=start_date,
            end=None,
        )
        if df.empty:
            print(f"  {sym:6s} FAIL (no data)")
        else:
            elapsed = time.time() - t0
            last = df.index[-1]
            last_close = df["close"].iloc[-1]
            print(f"  {sym:6s} [{status:11s}] {len(df):>5d} rows  {elapsed:.1f}s  last={last.date()} close={last_close:.2f}")
    except Exception as e:
        print(f"  {sym:6s} ERROR: {type(e).__name__}: {e}")
