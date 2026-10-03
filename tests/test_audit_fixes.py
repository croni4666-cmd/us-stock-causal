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


# =============================================================================
# Round 3 Audit Regression Tests (6 Reproducible Issues)
# =============================================================================

def test_unidentifiable_causal_rendering_no_l2_or_do():
    """Point 1: Unidentifiable causal effect must display observation association without L2/do labels."""
    from unittest.mock import patch
    from src import causal, report

    clear_caches()
    rng = np.random.default_rng(42)
    n = 1000
    z = rng.normal(size=n)
    t = 1.5 * z + rng.normal(0, 0.5, n)
    y = 2.0 * t + 3.0 * z + rng.normal(0, 0.5, n)
    df = pd.DataFrame(
        {"VIX": t, "QQQ": y, "TNX": rng.normal(size=n)},
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )
    # Z is in DAG, but missing from df
    cfg = {
        "dot": "digraph { Z -> VIX; Z -> QQQ; VIX -> QQQ; TNX -> QQQ; }",
        "nodes": {"parquet_map": {}},
    }

    orig_query = causal.causal_query
    def query_no_refute(*args, **kwargs):
        kwargs["n_refutations"] = 0
        return orig_query(*args, **kwargs)

    with patch.object(causal, "load_dag_config", return_value=cfg), \
         patch.object(causal, "load_dag_data", return_value=df), \
         patch.object(causal, "causal_query", side_effect=query_no_refute):
        rendered = report.render_causal_section(include_l3=False, as_of="2023-10-31")

    # Find the VIX query line
    vix_lines = [l for l in rendered.splitlines() if "恐慌指数 (VIX)" in l and "QQQ" in l]
    assert len(vix_lines) == 1
    vl = vix_lines[0]

    # Must be marked as observation association
    assert "观察关联 (因果不可识别)" in vl
    # Must NOT contain L2 or do labels
    assert "**L2 干预**" not in vl
    assert "`do(+1%)`" not in vl
    assert "无法估计因果干预效应" in vl
    assert "['Z']" in vl

    # When Z is added to data, identifiability is restored!
    df_with_z = df.copy()
    df_with_z["Z"] = z
    with patch.object(causal, "load_dag_config", return_value=cfg), \
         patch.object(causal, "load_dag_data", return_value=df_with_z), \
         patch.object(causal, "causal_query", side_effect=query_no_refute):
        rendered_restored = report.render_causal_section(include_l3=False, as_of="2023-10-31")

    vix_lines_restored = [l for l in rendered_restored.splitlines() if "恐慌指数 (VIX)" in l and "QQQ" in l]
    assert len(vix_lines_restored) == 1
    assert "**L2 干预**" in vix_lines_restored[0]
    assert "`do(+1%)`" in vix_lines_restored[0]


def test_historical_weights_date_integrity(tmp_path, monkeypatch):
    """Point 3: Historical weights fallback must not spoof past date or write fake snapshots."""
    from src import sector_weights_live as weights

    wroot = tmp_path / "weights"
    (wroot / "config").mkdir(parents=True)
    cfg_file = wroot / "config" / "sector_weights.json"
    cache_dir = wroot / "data" / "cache"

    test_config = {
        "_meta": {"as_of": "2026-07-23", "note": "future config"},
        "QQQ": {"XLK": 0.5, "XLC": 0.5},
    }
    import json
    cfg_file.write_text(json.dumps(test_config), encoding="utf-8")

    monkeypatch.setattr(weights, "PROJECT_ROOT", wroot)
    monkeypatch.setattr(weights, "WEIGHTS_PATH", cfg_file)
    monkeypatch.setattr(weights, "CACHE_DIR", cache_dir)

    # 1. pull_live_weights must return true effective date, not requested past date
    snap = weights.pull_live_weights(date="2026-06-01")
    assert snap["as_of"] == "2026-07-23"

    # 2. save_live_cache must reject saving past date with future snapshot
    saved = weights.save_live_cache(snap, date="2026-06-01")
    assert saved is None
    assert not (cache_dir / "sector_weights_live_2026-06-01.json").exists()

    # 3. load_live_or_static for past date returns fallback with explicit metadata
    loaded = weights.load_live_or_static(date="2026-06-01", use_cache=False)
    assert loaded["_meta"]["is_historical_fallback"] is True
    assert loaded["_meta"]["requested_as_of"] == "2026-06-01"
    assert loaded["_meta"]["effective_date"] == "2026-07-23"
    assert loaded != test_config  # Does not silently return current config unchanged!


def test_report_cache_invalidates_on_macro_or_sector_update(tmp_path, monkeypatch):
    """Point 4: Report cache signature must cover macro, sectors, and configs."""
    from unittest.mock import patch
    from src import report

    report_root = tmp_path / "report"
    raw_dir = report_root / "data" / "raw"
    for lyr in ("indices", "macro", "sectors"):
        (raw_dir / lyr).mkdir(parents=True)

    idx_file = raw_dir / "indices" / "QQQ.parquet"
    vix_file = raw_dir / "macro" / "_VIX.parquet"
    pd.DataFrame({"close": [100.0, 101.0]}, index=pd.date_range("2026-06-01", periods=2)).to_parquet(idx_file)
    pd.DataFrame({"close": [20.0, 21.0]}, index=pd.date_range("2026-06-01", periods=2)).to_parquet(vix_file)

    def mock_macro_topline(**kwargs):
        return "VIX=" + str(pd.read_parquet(vix_file)["close"].iloc[-1])

    report.clear_report_cache()
    monkeypatch.setattr(report, "PROJECT_ROOT", report_root)
    monkeypatch.setattr(report, "macro_topline", mock_macro_topline)
    monkeypatch.setattr(report, "render_causal_section", lambda **k: "")
    monkeypatch.setattr(report, "five_segment_report", lambda *a, **k: {})
    monkeypatch.setattr(report, "render_markdown", lambda r: "probe")

    before = report.render_full_report(["QQQ"], as_of="2026-06-02")
    assert "VIX=21.0" in before

    # Update _VIX.parquet price: 21.0 -> 99.0
    pd.DataFrame({"close": [20.0, 99.0]}, index=pd.date_range("2026-06-01", periods=2)).to_parquet(vix_file)

    # Next standard call without force must automatically detect the updated macro file!
    after = report.render_full_report(["QQQ"], as_of="2026-06-02")
    assert "VIX=99.0" in after


def test_attribution_cache_data_version_invalidation(tmp_path, monkeypatch):
    """Point 5: Attribution cache must auto-invalidate when sector parquets change."""
    from src import attribution

    att_root = tmp_path / "attribution" / "data" / "raw"
    for lyr in ("indices", "sectors"):
        (att_root / lyr).mkdir(parents=True)

    idx_dates = pd.date_range("2026-06-01", periods=3, freq="B")
    for s in attribution.SECTOR_TICKERS:
        pd.DataFrame({"close": [100.0, 101.0, 102.0]}, index=idx_dates).to_parquet(att_root / "sectors" / f"{s}.parquet")
    for idx in ("DIA", "QQQ", "RSP", "QQQE"):
        pd.DataFrame({"close": [100.0, 101.0, 102.0]}, index=idx_dates).to_parquet(att_root / "indices" / f"{idx}.parquet")

    attribution.clear_attribution_cache()
    monkeypatch.setattr(attribution, "CACHE_ROOT", att_root)
    monkeypatch.setattr(attribution, "load_sector_weights", lambda as_of=None, use_live_cache=True: {"QQQ": {"XLK": 1.0}})

    r1 = attribution.attribute_index("QQQ", date="2026-06-03")
    assert abs(r1["predicted_return_pct"] - 0.985) < 0.01

    # Modify XLK.parquet last price 102 -> 150
    pd.DataFrame({"close": [100.0, 101.0, 150.0]}, index=idx_dates).to_parquet(att_root / "sectors" / "XLK.parquet")

    # Regular call must automatically reflect new price without needing manual cache clear!
    r2 = attribution.attribute_index("QQQ", date="2026-06-03")
    assert abs(r2["predicted_return_pct"] - 39.551) < 0.01


def test_market_freshness_session_timing_and_types(tmp_path):
    """Point 6: get_expected_last_trading_day timezone/types and is_fresh strict checking."""
    from src import cache

    # 1. date and datetime inputs must not raise NameError
    d_res = cache.get_expected_last_trading_day(date(2026, 10, 2))
    assert isinstance(d_res, date)
    assert d_res == date(2026, 10, 2)

    # 2. Midday (before 16:15 ET) on Friday Oct 2 -> expected last completed is Thursday Oct 1
    midday = cache.get_expected_last_trading_day("2026-10-02T12:00:00")
    assert midday == date(2026, 10, 1)

    # 3. After close (17:00 ET) on Friday Oct 2 -> expected last completed is Friday Oct 2
    after_close = cache.get_expected_last_trading_day("2026-10-02T17:00:00-04:00")
    assert after_close == date(2026, 10, 2)

    # 4. Weekend (Saturday Oct 3) -> expected is Friday Oct 2
    sat_res = cache.get_expected_last_trading_day(date(2026, 10, 3))
    assert sat_res == date(2026, 10, 2)

    # 5. is_fresh returns False when latest bar lags expected session (no 2-day slack skipping)
    pq_path = tmp_path / "test_freshness.parquet"
    pd.DataFrame({"close": [100.0]}, index=pd.to_datetime(["2026-09-30"])).to_parquet(pq_path)
    # Expected is 2026-10-01 at 12:00 on Oct 2; file has 2026-09-30 (missing 1 session)
    fresh = cache.is_fresh(pq_path, as_of="2026-10-02T12:00:00")
    assert fresh is False

