"""Isolated, deterministic offline market data; live tests require --integration."""
from __future__ import annotations
import importlib
import json
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", help="Run live market/provider tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires real external providers")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="live providers require --integration"))


@pytest.fixture(scope="session")
def market_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("offline-market")
    shutil.copytree(PROJECT_ROOT / "config", root / "config")
    shutil.copytree(PROJECT_ROOT / "data" / "baseline", root / "data" / "baseline")
    config_path = root / "config" / "sector_weights.json"
    weights = json.loads(config_path.read_text(encoding="utf-8"))
    # Synthetic weights and prices are one known model, not historical market claims.
    weights["_meta"]["as_of"] = "2024-01-01"
    config_path.write_text(json.dumps(weights), encoding="utf-8")
    cfg = yaml.safe_load((root / "config" / "causal_dag.yaml").read_text(encoding="utf-8"))
    dates = pd.bdate_range(end="2026-07-24", periods=760)
    rng = np.random.default_rng(42)
    returns = {node: rng.normal(.0001, .005, len(dates)) for node in cfg["nodes"]["parquet_map"]}
    returns["VIX"] = rng.normal(0, .04, len(dates))
    returns["TNX"] = rng.normal(0, .015, len(dates))
    sectors = ["XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU", "XLB", "XLRE", "XLC"]
    for sector in sectors:
        returns[sector] = -.12 * returns["VIX"] + .10 * returns["TNX"] + .02 * returns["DXY"] + rng.normal(.0001, .001, len(dates))
    returns["XLB"] += .05 * returns["GC_F"]
    returns["XLE"] += .10 * returns["CL_F"]
    for index in ("DIA", "QQQ", "RSP", "QQQE"):
        returns[index] = sum(weights[index].get(s, 0) * returns[s] for s in sectors) + rng.normal(0, .0001, len(dates))
    for node, relative in cfg["nodes"]["parquet_map"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        close = 100 * np.exp(np.cumsum(returns[node]))
        pd.DataFrame({"open": close * 1.001, "close": close, "high": close * 1.005,
                      "low": close * .995, "volume": 1000000}, index=dates).to_parquet(path)
    (root / "output").mkdir()
    return root


@pytest.fixture(autouse=True)
def isolated_market(monkeypatch, market_root, request):
    if "integration" in request.node.keywords:
        yield
        return
    monkeypatch.setenv("US_STOCK_PROXY", "off")
    from src import attribution, causal, report, sector_weights_live
    for name in ("attribution", "thresholds", "causal", "report", "sector_weights_live",
                 "alert_logger", "retry", "yfinance_rate_limit", "residual_regression"):
        module = importlib.import_module("src." + name)
        monkeypatch.setattr(module, "PROJECT_ROOT", market_root)
    monkeypatch.setattr(attribution, "CACHE_ROOT", market_root / "data" / "raw")
    monkeypatch.setattr(importlib.import_module("src.thresholds"), "CACHE_ROOT", market_root / "data" / "raw")
    for module in (attribution, sector_weights_live):
        monkeypatch.setattr(module, "WEIGHTS_PATH", market_root / "config" / "sector_weights.json")
    monkeypatch.setattr(sector_weights_live, "CACHE_DIR", market_root / "data" / "cache")
    from examples import daily_report
    monkeypatch.setattr(daily_report, "OUTPUT_DIR", market_root / "output")
    monkeypatch.setattr(daily_report, "ALERT_DIR", market_root / "data" / "cache" / "alerts")
    monkeypatch.setattr(daily_report, "CACHE_DIR", market_root / "data" / "cache" / "sec_filings")
    from src import alert_logger, retry, yfinance_rate_limit, residual_regression
    monkeypatch.setattr(alert_logger, "ALERT_DIR", market_root / "data" / "cache" / "alerts")
    monkeypatch.setattr(retry, "RETRY_LOG", market_root / "data" / "cache" / "retry_log.json")
    monkeypatch.setattr(yfinance_rate_limit, "RATE_LIMIT_CACHE", market_root / "data" / "cache" / "yfinance_rate_limit.json")
    monkeypatch.setattr(residual_regression, "DEFAULT_BASELINE", market_root / "data" / "baseline" / "residuals_v069p.json")
    for name in ("stale", "vix_spike", "parquet_corrupt", "ticker_fail"):
        module = importlib.import_module("src.checks." + name)
        if hasattr(module, "DATA_RAW"):
            monkeypatch.setattr(module, "DATA_RAW", market_root / "data" / "raw")
        if hasattr(module, "RATE_LIMIT_PATH"):
            monkeypatch.setattr(module, "RATE_LIMIT_PATH", yfinance_rate_limit.RATE_LIMIT_CACHE)
    scratch = market_root / "scratch"
    scratch.mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    monkeypatch.setenv("US_STOCK_PROXY", "off")
    monkeypatch.setenv("US_STOCK_NOTIFY", "0")
    import requests
    def offline(*args, **kwargs):
        raise requests.ConnectionError("external requests disabled in offline tests")
    monkeypatch.setattr(requests.sessions.Session, "request", offline)
    from curl_cffi.requests import Session
    monkeypatch.setattr(Session, "request", offline)
    attribution.clear_attribution_cache()
    causal.clear_caches()
    report.clear_report_cache()
    yield
    attribution.clear_attribution_cache()
    causal.clear_caches()
    report.clear_report_cache()
