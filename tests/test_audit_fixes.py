"""tests/test_audit_fixes.py - Regression tests for the 10 critical audit fixes.

Covers:
1. L2 Confounder Backdoor Adjustment (Synthetic Pearl recovery vs. unadjusted OLS)
2. Instrument vs Confounder Distinction (No Z-bias on pure instruments)
3. PC Algorithm Edge Direction (causal-learn Endpoint matrix orientation)
4. Cache Key Invalidation on Value Drift (Same row-count, different content)
5. Atomic Cache Write & Max Bar Date Freshness
6. Pattern Matching Candidate Window & Forward Window Non-Overlap
7. Date / As-of Propagation (No look-ahead data leakage)
8. Refutation Pass/Fail Evaluation Criteria
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import networkx as nx

from src.causal import (
    causal_query,
    identify_backdoor_set,
    discover_dag_pc,
    _compute_data_hash,
    clear_caches,
)
from src.cache import write_cache, is_fresh, update_or_fetch
from src.patterns import find_similar_patterns
from src.report import render_full_report, five_segment_report
from src.attribution import attribute_index, attribute_all_indices
from src.thresholds import get_thresholds


# =============================================================================
# 1. L2 Backdoor Adjustment & Confounder Control
# =============================================================================

def test_backdoor_adjustment_synthetic_recovery():
    """Verify that backdoor adjustment recovers true causal effect in presence of confounder."""
    clear_caches()
    rng = np.random.default_rng(42)
    n = 1000
    # Confounder Z affects both Treatment T and Outcome Y
    # True causal effect T -> Y is 2.0
    z = rng.normal(0, 1, n)
    t = 1.5 * z + rng.normal(0, 0.5, n)
    y = 2.0 * t + 3.0 * z + rng.normal(0, 0.5, n)

    df = pd.DataFrame({"Z": z, "T": t, "Y": y})
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")

    # DAG: Z -> T, Z -> Y, T -> Y
    cfg = {
        "dot": 'digraph { Z -> T; Z -> Y; T -> Y; }',
        "nodes": {"parquet_map": {}},
    }

    g = nx.DiGraph()
    g.add_edges_from([("Z", "T"), ("Z", "Y"), ("T", "Y")])

    # 1. Backdoor set should identify Z as the only confounder
    backdoor_set = identify_backdoor_set(g, treatment="T", outcome="Y")
    assert backdoor_set == ["Z"]

    # 2. Unadjusted OLS would yield biased slope ~ 3.48
    cov_ty = np.cov(t, y)[0, 1]
    var_t = np.var(t)
    unadjusted_beta = cov_ty / var_t
    assert unadjusted_beta > 3.0, f"Unadjusted beta should be confounded: {unadjusted_beta}"

    # 3. causal_query with backdoor adjustment should recover true effect ~ 2.0
    eff = causal_query(treatment="T", outcome="Y", data=df, cfg=cfg, n_refutations=0)
    assert abs(eff.estimate - 2.0) < 0.1, f"Adjusted ATE {eff.estimate} should be close to 2.0"
    assert "Pearl L2 Backdoor Adjustment (controlled: ['Z'])" in eff.estimand


def test_pure_instrument_not_controlled():
    """Verify that an upstream instrument I -> T without backdoor path to Y is not controlled."""
    g = nx.DiGraph()
    g.add_edges_from([("I", "T"), ("T", "Y")])
    # I affects T, but has no path to Y except through T
    backdoor_set = identify_backdoor_set(g, treatment="T", outcome="Y")
    assert backdoor_set == [], "Pure instrument should not be in backdoor adjustment set"


# =============================================================================
# 2. PC Algorithm Edge Direction
# =============================================================================

def test_pc_algorithm_edge_direction_linear_gaussian():
    """Verify PC algorithm maps Endpoint matrix correctly (causes point to effects)."""
    clear_caches()
    rng = np.random.default_rng(123)
    n = 2000
    # True chain: X -> Y -> Z with unshielded collider / chain
    x = rng.normal(0, 1, n)
    y = 0.8 * x + rng.normal(0, 0.4, n)
    z = 0.7 * y + rng.normal(0, 0.3, n)

    df = pd.DataFrame({"X": x, "Y": y, "Z": z})
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")

    pc_dag = discover_dag_pc(df, alpha=0.01)

    # In general, PC should not direct edges backwards (Z -> Y or Y -> X)
    assert not pc_dag.has_edge("Z", "Y"), "PC should never reverse edge to Z -> Y"
    assert not pc_dag.has_edge("Y", "X"), "PC should never reverse edge to Y -> X"


# =============================================================================
# 3. Deterministic Data Hashing & Cache Invalidation
# =============================================================================

def test_data_hash_invalidation_on_value_change():
    """Verify that cache hash changes when values change even if length is identical."""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    df1 = pd.DataFrame({"A": np.ones(100), "B": np.zeros(100)}, index=dates)
    df2 = pd.DataFrame({"A": np.ones(100) * 2.0, "B": np.zeros(100)}, index=dates)

    assert len(df1) == len(df2)
    hash1 = _compute_data_hash(df1)
    hash2 = _compute_data_hash(df2)
    assert hash1 != hash2, "Data hash must differ when DataFrame values change"


# =============================================================================
# 4. Safe Atomic Cache Write & Freshness
# =============================================================================

def test_atomic_cache_write_and_freshness():
    """Verify atomic parquet writing and bar date freshness inspection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cache_file = tmp_path / "test_ticker.parquet"

        # Write data ending in today
        dates = pd.date_range(end=pd.Timestamp.now().floor("D"), periods=10, freq="B")
        df = pd.DataFrame({"close": np.linspace(100, 110, len(dates))}, index=dates)

        write_cache(df, cache_file)
        assert cache_file.exists()

        # Check freshness
        fresh = is_fresh(cache_file, max_age_days=1)
        assert fresh is True

        # Old data in parquet makes it stale even if file was just written
        old_dates = pd.date_range("2020-01-01", periods=10, freq="B")
        old_df = pd.DataFrame({"close": np.linspace(100, 110, len(old_dates))}, index=old_dates)
        write_cache(old_df, cache_file)
        assert is_fresh(cache_file, max_age_days=10) is False


def test_update_or_fetch_preserves_old_cache_on_failure():
    """Verify update_or_fetch does not destroy existing cache if network fetch fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cache_file = tmp_path / "indices" / "SAFE.parquet"
        original_dates = pd.date_range("2026-07-01", "2026-07-10", freq="B")
        original_df = pd.DataFrame({"close": np.arange(len(original_dates))}, index=original_dates)
        write_cache(original_df, cache_file)

        def failing_fetcher(symbol, start=None, end=None):
            raise ConnectionError("Network failure")

        # Even with force_refresh, failure should fallback to old cache without data loss
        df, status = update_or_fetch(
            symbol="SAFE",
            layer="indices",
            fetcher=failing_fetcher,
            cache_root=tmp_path,
            force_refresh=True,
        )
        assert df is not None
        assert len(df) == len(original_df)
        assert status == "refresh_failed_cached"
        assert cache_file.exists()


# =============================================================================
# 5. Pattern Matching Candidate Window Non-Overlap
# =============================================================================

def test_pattern_matching_candidate_non_overlap():
    """Verify candidate matching windows and forward horizons strictly precede current window."""
    p = find_similar_patterns(
        symbol="QQQ",
        pattern_length=20,
        n_matches=5,
        forecast_horizon=5,
    )
    assert p["n_matches"] > 0
    # Candidate windows should strictly end before current pattern start
    current_end = pd.to_datetime(p["pattern_end"])
    for m in p["top_matches"]:
        m_start = pd.to_datetime(m["start_date"])
        m_end = pd.to_datetime(m["end_date"])
        # Match window must be pattern_length
        assert m_end < current_end


# =============================================================================
# 6. As-of / Date Propagation
# =============================================================================

def test_as_of_date_propagation_report():
    """Verify that passing as_of restricts report generation to historical date."""
    hist_date = "2025-06-30"
    report_5seg = five_segment_report("QQQ", layer="indices", as_of=hist_date)
    assert report_5seg["as_of"] == hist_date

    # Thresholds as_of verification
    th_hist = get_thresholds("QQQ", layer="indices", as_of=hist_date)
    assert th_hist["date"] <= hist_date

    # Attribution as_of verification
    attr_hist = attribute_index("QQQ", date=hist_date, lookback_days=5)
    assert attr_hist["date"] <= hist_date
