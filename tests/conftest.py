"""tests/conftest.py - Global pytest configuration and offline test fixtures.

Provides an autouse session fixture that ensures minimal synthetic parquet data
exists in `data/raw/` so that tests (including `test_smoke.py` and `test_audit_fixes.py`)
can pass completely offline on a fresh, clean checkout without requiring pre-existing
market parquet files or network access.
"""
from __future__ import annotations

import os
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAG_CONFIG = PROJECT_ROOT / "config" / "causal_dag.yaml"


@pytest.fixture(scope="session", autouse=True)
def ensure_test_market_parquets():
    """Ensure minimal offline market parquets exist for CI and clean clones.
    
    If data/raw is missing parquet files (as in a clean git checkout where data/raw/*.parquet
    is ignored), generates synthetic OHLCV data for all 47 DAG symbols (indices, sectors,
    macro, commodities) spanning 504 business days with realistic returns.
    """
    if not DAG_CONFIG.exists():
        return

    with open(DAG_CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    parquet_map = cfg.get("nodes", {}).get("parquet_map", {})
    if not parquet_map:
        return

    # Check if any key files are missing
    missing_paths = []
    for node, rel_path in parquet_map.items():
        pq_path = PROJECT_ROOT / rel_path
        if not pq_path.exists() or pq_path.stat().st_size < 100:
            missing_paths.append((node, pq_path))

    if not missing_paths:
        return

    # Generate synthetic 504-day trading calendar
    dates = pd.bdate_range(end="2026-07-24", periods=504)
    rng = np.random.default_rng(42)

    for node, pq_path in missing_paths:
        pq_path.parent.mkdir(parents=True, exist_ok=True)
        # Generate random walk with small daily returns (std=0.012)
        rets = rng.normal(loc=0.0003, scale=0.012, size=len(dates))
        base_price = 100.0
        if "VIX" in node:
            base_price = 18.0
            rets = rng.normal(loc=0.0, scale=0.04, size=len(dates))
        elif "TNX" in node:
            base_price = 4.2
            rets = rng.normal(loc=0.0, scale=0.015, size=len(dates))
        elif node in ("DIA", "QQQ", "RSP", "QQQE"):
            base_price = 350.0

        close = base_price * np.exp(np.cumsum(rets))
        # Ensure prices remain strictly positive
        close = np.clip(close, a_min=1.0, a_max=None)
        
        noise = rng.normal(0, 0.002, size=len(dates))
        open_p = close * (1.0 + noise)
        high_p = np.maximum(open_p, close) * (1.0 + rng.uniform(0.001, 0.008, size=len(dates)))
        low_p = np.minimum(open_p, close) * (1.0 - rng.uniform(0.001, 0.008, size=len(dates)))
        vol = rng.integers(500_000, 10_000_000, size=len(dates))

        df = pd.DataFrame(
            {
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close,
                "volume": vol,
            },
            index=dates,
        )
        df.to_parquet(pq_path)
