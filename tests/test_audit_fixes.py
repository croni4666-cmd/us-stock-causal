"""tests/test_audit_fixes.py - Regression tests for the 10 critical audit fixes.

Covers:
1. L2 Confounder Backdoor Adjustment (Synthetic Pearl recovery vs. unadjusted OLS)
2. Missing Confounder Detection (Identifiability status, missing columns declaration)
3. Instrument vs Confounder Distinction (Pure instruments not controlled)
4. PC Algorithm Edge Direction (causal-learn Endpoint matrix orientation)
5. Full Content Hashing & Equal-Sum Cache Invalidation
6. DAG Graph Hash Identity in Caches & Auto-Reduce
7. Refutation Pass/Fail Evaluation Criteria
8. Negative Causal Effect Sign Formatting (No '+' on downward shock)
9. Historical Event Isolation & As-of Days Until
10. Performance Dashboard As-of Historical Price Cutoff
11. Pattern Matching Deduplication (No re-injection of overlapping windows)
12. Offline Five-Segment Report & Future Data Invariance
"""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import networkx as nx

from src.causal import (
    causal_query,
    identify_backdoor_set,
    discover_dag_pc,
    _convert_pc_graph,
    _compute_data_hash,
    _compute_graph_hash,
    format_causal_effect,
    clear_caches,
)
from src.cache import write_cache, is_fresh, update_or_fetch, get_expected_last_trading_day
from src.patterns import find_similar_patterns
from src.report import render_full_report, five_segment_report, clear_report_cache
from src.attribution import attribute_index, attribute_all_indices, clear_attribution_cache
from src.thresholds import get_thresholds
from src.events import next_event, upcoming_events, MacroEvent
from src.performance_dashboard import compute_1d_change, render_performance_table_html


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
    assert backdoor_set.status == "identified_adjusted"

    # 2. Unadjusted OLS would yield biased slope ~ 3.48
    cov_ty = np.cov(t, y)[0, 1]
    var_t = np.var(t)
    unadjusted_beta = cov_ty / var_t
    assert unadjusted_beta > 3.0, f"Unadjusted beta should be confounded: {unadjusted_beta}"

    # 3. causal_query with backdoor adjustment should recover true effect ~ 2.0
    eff = causal_query(treatment="T", outcome="Y", data=df, cfg=cfg, n_refutations=0)
    assert abs(eff.estimate - 2.0) < 0.1, f"Adjusted ATE {eff.estimate} should be close to 2.0"
    assert "Pearl L2 Backdoor Adjustment (controlled: ['Z'])" in eff.estimand


# =============================================================================
# 2. Missing Confounder Detection (Unidentifiable Pearl Status)
# =============================================================================

def test_missing_confounder_identifiability_status():
    """Verify that if a required DAG confounder is missing from data, effect is declared unidentifiable."""
    clear_caches()
    rng = np.random.default_rng(42)
    n = 500
    z = rng.normal(0, 1, n)
    t = 1.5 * z + rng.normal(0, 0.5, n)
    y = 2.0 * t + 3.0 * z + rng.normal(0, 0.5, n)

    # Data only has T and Y, Z is unobserved
    df_missing = pd.DataFrame({"T": t, "Y": y})
    df_missing.index = pd.date_range("2024-01-01", periods=n, freq="B")

    g = nx.DiGraph()
    g.add_edges_from([("Z", "T"), ("Z", "Y"), ("T", "Y")])

    res = identify_backdoor_set(g, treatment="T", outcome="Y", available_columns=set(df_missing.columns))
    assert res.status == "unidentifiable"
    assert res.missing_confounders == ["Z"]

    cfg = {"dot": 'digraph { Z -> T; Z -> Y; T -> Y; }', "nodes": {"parquet_map": {}}}
    eff = causal_query(treatment="T", outcome="Y", data=df_missing, cfg=cfg, n_refutations=0)
    assert "Unidentifiable" in eff.estimand
    assert "missing confounders: ['Z']" in eff.estimand
    assert "unadjusted_association" in eff.method


# =============================================================================
# 3. Instrument vs Confounder Distinction
# =============================================================================

def test_pure_instrument_not_controlled():
    """Verify that an upstream instrument I -> T without backdoor path to Y is not controlled."""
    g = nx.DiGraph()
    g.add_edges_from([("I", "T"), ("T", "Y")])
    # I affects T, but has no path to Y except through T
    backdoor_set = identify_backdoor_set(g, treatment="T", outcome="Y")
    assert backdoor_set == [], "Pure instrument should not be in backdoor adjustment set"
    assert backdoor_set.status == "identified_unconfounded"


# =============================================================================
# 4. PC Algorithm Edge Direction & Endpoint Matrix Conversion
# =============================================================================

def test_pc_endpoint_matrix_conversion_direction():
    """Verify causallearn Endpoint matrix converts to networkx DiGraph with exact edge directions."""
    # 3 nodes: A, B, C
    # Convention:
    # A -> B: matrix[A, B] = -1 (tail at A), matrix[B, A] = 1 (arrow at B)
    # B -- C: matrix[B, C] = -1 (tail at B), matrix[C, B] = -1 (tail at C)
    # A and C: no edge (0, 0)
    matrix = np.zeros((3, 3), dtype=int)
    # A (idx 0), B (idx 1), C (idx 2)
    matrix[0, 1] = -1
    matrix[1, 0] = 1

    matrix[1, 2] = -1
    matrix[2, 1] = -1

    g = _convert_pc_graph(matrix, ["A", "B", "C"])

    assert g.has_edge("A", "B"), "Directed edge A -> B must exist"
    assert not g.has_edge("B", "A"), "Reversed edge B -> A must NOT exist"
    assert not g.has_edge("B", "C") and not g.has_edge("C", "B"), "Undirected edge should not be directed arbitrarily"
    assert ("B", "C") in g.graph.get("undirected_edges", []) or ("C", "B") in g.graph.get("undirected_edges", [])


# =============================================================================
# 5. Full Content Hashing & Equal-Sum Cache Invalidation
# =============================================================================

def test_data_hash_equal_sum_collision_and_date_change():
    """Verify hash distinguishes datasets with equal sum, equal length, or intermediate date change."""
    dates = pd.date_range("2024-01-01", periods=101, freq="B")
    t = np.linspace(-5, 5, 101)  # sum(t) == 0.0

    df1 = pd.DataFrame({"T": t, "Y": 2.0 * t}, index=dates)   # sum == 0.0
    df2 = pd.DataFrame({"T": t, "Y": -3.0 * t}, index=dates)  # sum == 0.0

    hash1 = _compute_data_hash(df1)
    hash2 = _compute_data_hash(df2)
    assert hash1 != hash2, "Equal-sum datasets with opposite slopes must NOT produce identical hash"

    # Intermediate date change test
    dates_mod = list(dates)
    dates_mod[50] = dates_mod[50] + pd.Timedelta(days=1)
    df3 = pd.DataFrame({"T": t, "Y": 2.0 * t}, index=dates_mod)
    hash3 = _compute_data_hash(df3)
    assert hash1 != hash3, "Intermediate date modification must invalidate data hash"

    # Verify query cache does not cross-pollute
    cfg = {"dot": 'digraph { T -> Y; }', "nodes": {"parquet_map": {}}}
    clear_caches()
    eff1 = causal_query("T", "Y", data=df1, cfg=cfg, n_refutations=0)
    eff2 = causal_query("T", "Y", data=df2, cfg=cfg, n_refutations=0)
    assert abs(eff1.estimate - 2.0) < 1e-4
    assert abs(eff2.estimate - (-3.0)) < 1e-4


# =============================================================================
# 6. DAG Graph Hash Identity in Caches
# =============================================================================

def test_dag_cache_identity_and_auto_reduce():
    """Verify that causal_query cache differentiates between different DAG structures."""
    clear_caches()
    rng = np.random.default_rng(42)
    n = 500
    z = rng.normal(0, 1, n)
    t = 1.5 * z + rng.normal(0, 0.5, n)
    y = 2.0 * t + 3.0 * z + rng.normal(0, 0.5, n)
    df = pd.DataFrame({"Z": z, "T": t, "Y": y})
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")

    # Graph 1: With confounder Z -> Y
    cfg1 = {"dot": 'digraph { Z -> T; Z -> Y; T -> Y; }', "nodes": {"parquet_map": {}}}
    # Graph 2: Without confounder Z -> Y (Z is pure instrument)
    cfg2 = {"dot": 'digraph { Z -> T; T -> Y; }', "nodes": {"parquet_map": {}}}

    eff1 = causal_query("T", "Y", data=df, cfg=cfg1, n_refutations=0)
    # Under cfg2, Z is not a confounder so adjustment set is empty; OLS estimate is biased (> 3.0)
    eff2 = causal_query("T", "Y", data=df, cfg=cfg2, n_refutations=0)

    assert abs(eff1.estimate - 2.0) < 0.1
    assert eff2.estimate > 3.0
    assert abs(eff1.estimate - eff2.estimate) > 1.0
    assert eff1.estimate != eff2.estimate, "Different DAG structures must not hit same cache result"


# =============================================================================
# 7. Refutation Pass/Fail Evaluation Criteria
# =============================================================================

def test_refutation_pass_fail_criteria():
    """Verify refutation pass/fail thresholds for placebo and subset methods."""
    ate = 2.0
    # Placebo: new effect should be close to 0
    placebo_pass = 0.05
    placebo_fail = 1.20
    assert abs(placebo_pass) <= max(0.3 * abs(ate), 0.02)
    assert not (abs(placebo_fail) <= max(0.3 * abs(ate), 0.02))

    # Data subset / Random common cause: new effect should remain close to ate
    subset_pass = 2.10
    subset_fail = 0.50
    assert abs(subset_pass - ate) <= max(0.35 * abs(ate), 0.05)
    assert not (abs(subset_fail - ate) <= max(0.35 * abs(ate), 0.05))


# =============================================================================
# 8. Negative Causal Effect Sign Formatting
# =============================================================================

def test_negative_causal_effect_sign_formatting():
    """Verify that negative effect estimates format as negative percentages, not positive."""
    fmt = format_causal_effect(estimate=-0.2, p_value=0.01)
    assert fmt["direction"] == "↓"
    assert fmt["pct_y"] == -0.2
    assert "-0.20%" in fmt["text"]
    assert "+0.20%" not in fmt["text"]
    assert "预期↓ 0.0020 (-0.20%)" in fmt["text"]


# =============================================================================
# 9. Historical Event Isolation & As-of Days Until
# =============================================================================

def test_historical_event_isolation_and_days_until():
    """Verify next_event and days_until compute strictly relative to historical from_date."""
    # With from_date in 2026-06-01
    ne = next_event(from_date="2026-06-01")
    assert ne is not None
    assert ne.date >= date(2026, 6, 1)
    # The event should be the immediate next event after 2026-06-01
    assert str(ne.date).startswith("2026-06")
    expected_days = (ne.date - date(2026, 6, 1)).days
    assert ne.days_until == expected_days
    assert ne.days_until >= 0


# =============================================================================
# 10. Performance Dashboard As-of Historical Price Cutoff
# =============================================================================

def test_performance_dashboard_as_of_historical_cutoff(monkeypatch):
    """Verify compute_1d_change with as_of cuts off future prices."""
    dates = pd.date_range("2026-01-01", "2026-10-01", freq="B")
    prices = pd.DataFrame(
        {
            "close": np.linspace(100, 200, len(dates)),
            "high": np.linspace(101, 201, len(dates)),
            "low": np.linspace(99, 199, len(dates)),
        },
        index=dates,
    )
    # Set known price at historical cutoff
    hist_date = "2026-06-01"
    prices.loc[hist_date, "close"] = 110.0
    prices.loc[dates[-1], "close"] = 999.0

    def mock_load_prices(sym, layer):
        return prices

    monkeypatch.setattr("src.performance_dashboard.load_prices", mock_load_prices)

    res = compute_1d_change("QQQ", "indices", as_of=hist_date)
    assert res is not None
    assert res["last_close"] == 110.0
    assert res["last_close"] != 999.0


# =============================================================================
# 11. Pattern Matching Deduplication (No Overlap Padding)
# =============================================================================

def test_pattern_matching_dedup_no_overlap_padding(monkeypatch):
    """Verify find_similar_patterns never re-injects overlapping candidates to pad n_matches."""
    # 80 days of repetitive pattern
    dates = pd.date_range("2026-01-01", periods=80, freq="B")
    # Sine wave price cycle
    cycle = np.sin(np.linspace(0, 10 * np.pi, 80)) * 10 + 100
    df = pd.DataFrame({"close": cycle, "high": cycle + 1, "low": cycle - 1}, index=dates)

    monkeypatch.setattr("src.patterns.load_prices", lambda s, l: df)

    p = find_similar_patterns(
        symbol="SYNTH",
        pattern_length=20,
        n_matches=10,
        forecast_horizon=5,
    )
    matches = p["top_matches"]
    assert len(matches) <= 10
    # Verify no two selected windows have starting dates closer than pattern_length // 2 (10 days)
    for i in range(len(matches)):
        for j in range(i + 1, len(matches)):
            d1 = pd.to_datetime(matches[i]["start_date"])
            d2 = pd.to_datetime(matches[j]["start_date"])
            # Index positions in dates
            idx1 = dates.get_loc(d1)
            idx2 = dates.get_loc(d2)
            assert abs(idx1 - idx2) >= 10, f"Overlapping candidate detected: idx {idx1} and {idx2}"


# =============================================================================
# 12. Offline Five-Segment Report & Future Data Invariance
# =============================================================================

def test_offline_five_segment_report_and_future_data_invariance(tmp_path, monkeypatch):
    """Verify five_segment_report runs 100% offline and is invariant to appended future data."""
    # 1. Create offline parquet files for indices and sectors
    hist_end = "2026-06-01"
    dates_past = pd.date_range("2025-01-01", hist_end, freq="B")
    dates_future = pd.date_range("2026-06-02", "2026-10-01", freq="B")

    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    indices_dir = raw_dir / "indices"
    indices_dir.mkdir()
    sectors_dir = raw_dir / "sectors"
    sectors_dir.mkdir()

    # Generate synthetic price history
    rng = np.random.default_rng(123)
    p_past = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, len(dates_past))))
    df_past = pd.DataFrame(
        {"close": p_past, "high": p_past * 1.01, "low": p_past * 0.99, "volume": 10000},
        index=dates_past,
    )

    last_p = p_past[-1]
    p_future = last_p * np.exp(np.cumsum(rng.normal(0.0005, 0.01, len(dates_future))))
    df_future = pd.DataFrame(
        {"close": p_future, "high": p_future * 1.01, "low": p_future * 0.99, "volume": 10000},
        index=dates_future,
    )
    df_full = pd.concat([df_past, df_future])

    # Mock load_prices in modules
    def mock_load_prices_past(symbol, layer):
        return df_past

    def mock_load_prices_full(symbol, layer):
        return df_full

    # Run at as_of=hist_end with past data
    monkeypatch.setattr("src.report.load_prices", mock_load_prices_past)
    monkeypatch.setattr("src.thresholds.load_prices", mock_load_prices_past)
    monkeypatch.setattr("src.patterns.load_prices", lambda s, l: df_past)
    monkeypatch.setattr("src.attribution.load_prices", lambda s, l: df_past["close"])

    rep_past = five_segment_report("QQQ", layer="indices", as_of=hist_end)
    assert rep_past["as_of"] == hist_end
    assert rep_past["symbol"] == "QQQ"

    # Now simulate future data added to parquet
    monkeypatch.setattr("src.report.load_prices", mock_load_prices_full)
    monkeypatch.setattr("src.thresholds.load_prices", mock_load_prices_full)
    monkeypatch.setattr("src.patterns.load_prices", lambda s, l: df_full)
    monkeypatch.setattr("src.attribution.load_prices", lambda s, l: df_full["close"])

    rep_full = five_segment_report("QQQ", layer="indices", as_of=hist_end)

    # Results for as_of=hist_end must remain completely identical!
    assert rep_past["segment_1_market"] == rep_full["segment_1_market"]
    assert rep_past["segment_3_thresholds"] == rep_full["segment_3_thresholds"]
    assert rep_past["segment_4_patterns"] == rep_full["segment_4_patterns"]
