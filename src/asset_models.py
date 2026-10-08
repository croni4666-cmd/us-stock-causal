"""Asset-specific mechanics; these calculations do not identify causal effects."""
from __future__ import annotations

from datetime import date, datetime, time
import math
from zoneinfo import ZoneInfo

import pandas as pd

from src.asset_sources import eligible_snapshot, portfolio_weight_complete


ASSET_KINDS = {"QQQ": "equity_etf", "IEF": "treasury_etf", "TLT": "treasury_etf",
               "GLD": "gold_etf", "GC=F": "continuous_futures_quote",
               "^IXIC": "price_index", "^NDX": "price_index",
               **{symbol: "yield_quote" for symbol in ("^IRX", "^FVX", "^TNX", "^TYX")}}


def _finite(value, *, nonnegative=False):
    number = float(value)
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise ValueError("invalid finite numeric value")
    return number


def _endpoints(series: pd.Series, start: str, end: str):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or series.empty:
        raise ValueError("invalid or empty period")
    dates = pd.DatetimeIndex(series.index)
    if dates.hasnans or not dates.is_monotonic_increasing or dates.has_duplicates:
        raise ValueError("series dates must be unique and increasing")
    days = [day.date() for day in dates]
    if len(set(days)) != len(days):
        raise ValueError("expected one daily observation per date")
    try:
        a, b = series.iloc[days.index(first)], series.iloc[days.index(last)]
    except ValueError as exc:
        raise ValueError("exact period endpoint missing; no date filling") from exc
    return _finite(a), _finite(b)


def period_return(series: pd.Series, start: str, end: str) -> float:
    a, b = _endpoints(series, start, end)
    if a <= 0 or b <= 0:
        raise ValueError("prices must be positive")
    return b / a - 1


def return_summary(symbol: str, prices: pd.DataFrame, start: str, end: str) -> dict:
    if symbol not in ASSET_KINDS:
        raise ValueError(f"unsupported asset: {symbol}")
    kind = ASSET_KINDS[symbol]
    result = {"symbol": symbol, "kind": kind, "start": start, "end": end,
              "causal_status": "not_identified", "limitations": []}
    if "close" not in prices:
        raise ValueError("close field missing")
    if kind == "yield_quote":
        a, b = _endpoints(prices["close"], start, end)
        result.update(yield_start_pct=a, yield_end_pct=b, yield_delta_bp=(b - a) * 100)
        result["limitations"].append("yield quote change is not a bond investment return")
        return result
    result["price_return"] = period_return(prices["close"], start, end)
    result["adjusted_return_proxy"] = None
    if kind.endswith("etf") and "adj close" in prices:
        try:
            result["adjusted_return_proxy"] = period_return(prices["adj close"], start, end)
        except ValueError:
            result["limitations"].append("provider-adjusted return endpoints unavailable or invalid")
    result["adjustment_gap"] = (None if result["adjusted_return_proxy"] is None else
                                result["adjusted_return_proxy"] - result["price_return"])
    if kind == "continuous_futures_quote":
        result["limitations"].append("continuous futures quote change excludes roll, collateral and margin effects")
    elif kind == "price_index":
        result["limitations"].append("price index change excludes reinvested dividends; QQQ weights are not index weights")
    else:
        result["limitations"].append("adjusted series is a provider total-return proxy, not an official fund return")
    return result


def equity_contributions(doc: dict, stock_returns: dict, etf_return: float,
                         start: str, mode: str = "point_in_time") -> dict:
    if doc.get("symbol") != "QQQ" or doc.get("kind") != "holdings":
        raise ValueError("only QQQ fund holdings supported; not official index weights")
    if not eligible_snapshot(doc, start, mode):
        return {"status": "unavailable", "reason": "no eligible beginning holdings/availability",
                "causal_status": "not_identified"}
    contributions, missing, covered = [], [], 0.0
    for row in doc["rows"]:
        if row["asset_class"] != "Equity":
            continue
        weight = row.get("weight")
        ticker = row.get("ticker")
        if weight is None or ticker is None or stock_returns.get(ticker) is None:
            missing.append(ticker or row["id"])
            continue
        weight = _finite(weight, nonnegative=True)
        value = _finite(stock_returns[ticker])
        if value < -1:
            raise ValueError("simple stock return below -100%")
        contributions.append({"id": row["id"], "ticker": ticker, "weight": weight,
                              "price_return": value, "contribution": weight * value})
        covered += weight
    explained = sum(row["contribution"] for row in contributions)
    known_weight = sum(row["weight"] for row in doc["rows"] if row.get("weight") is not None)
    non_equity = sum(row["weight"] for row in doc["rows"]
                     if row["asset_class"] != "Equity" and row.get("weight") is not None)
    return {"status": "ok" if contributions else "partial", "method": "fixed beginning-weight price contribution",
            "mode": mode, "as_of": doc["as_of"], "covered_weight": covered,
            "known_weight": known_weight, "non_equity_weight": non_equity,
            "unknown_weight_count": sum(row.get("weight") is None for row in doc["rows"]),
            "contributions": sorted(contributions, key=lambda r: abs(r["contribution"]), reverse=True),
            "missing_tickers": missing, "contribution": explained,
            "etf_price_return": _finite(etf_return), "residual": _finite(etf_return) - explained,
            "causal_status": "not_identified",
            "limitations": ["uncovered holdings, cash, derivatives, dividends, fees and trading remain in residual",
                            "multi-day calculation assumes fixed beginning weights; not daily rebalancing accounting"]}


def treasury_profile(doc: dict) -> dict:
    if doc.get("symbol") not in ("IEF", "TLT") or doc.get("kind") != "holdings":
        raise ValueError("expected official Treasury ETF holdings")
    bonds = [r for r in doc["rows"] if r["asset_class"] == "Fixed Income"]
    known = [r for r in bonds if r.get("weight") is not None and r.get("duration_years") is not None]
    missing = [r["id"] for r in bonds if r not in known]
    # Money market/cash durations, if supplied, contribute using their original
    # signed portfolio weight. Bond coverage is reported separately.
    weighted = sum(_finite(r["weight"]) * _finite(r["duration_years"], nonnegative=True)
                   for r in doc["rows"] if r.get("weight") is not None and r.get("duration_years") is not None)
    return {"symbol": doc["symbol"], "as_of": doc["as_of"], "bond_count": len(bonds),
            "bond_weight": sum(r["weight"] for r in bonds if r.get("weight") is not None),
            "duration_covered_weight": sum(r["weight"] for r in known),
            "weighted_duration_years": weighted, "missing_duration_ids": missing,
            "unknown_weight_count": sum(r.get("weight") is None for r in doc["rows"]),
            "known_weight": sum(r["weight"] for r in doc["rows"] if r.get("weight") is not None),
            "complete": bool(bonds) and not missing and portfolio_weight_complete(doc["rows"]) and all(r.get("weight") is not None and
                           r.get("duration_years") is not None for r in doc["rows"]),
            "method": "portfolio-weighted issuer effective durations; linear parallel-shift approximation",
            "causal_status": "not_identified"}


def duration_effect(duration_years: float, yield_delta_bp: float) -> float:
    return -_finite(duration_years, nonnegative=True) * _finite(yield_delta_bp) / 10000


def gold_archive_metrics(doc: dict, start: str, end: str, mode: str = "point_in_time") -> dict:
    if mode not in ("point_in_time", "retrospective"):
        raise ValueError("mode must be point_in_time or retrospective")
    if doc.get("symbol") != "GLD" or doc.get("kind") != "gold_archive":
        raise ValueError("expected GLD official archive")
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("invalid period")
    cutoff = datetime.combine(date.fromisoformat(end), time(16, 30), ZoneInfo("America/New_York"))
    captured = datetime.fromisoformat(doc["available_at"])
    if captured.tzinfo is None:
        raise ValueError("availability timestamp requires timezone")
    if mode == "point_in_time" and captured > cutoff:
        return {"status": "unavailable", "reason": "archive obtained after analysis cutoff",
                "causal_status": "not_identified"}
    records = {r["date"]: r for r in doc["rows"]}
    if start not in records or end not in records:
        return {"status": "unavailable", "reason": "exact GLD archive dates unavailable; no forward fill",
                "causal_status": "not_identified"}
    a, b = records[start], records[end]
    def change(key):
        if a.get(key) is None or b.get(key) is None:
            return None
        first, last = _finite(a[key]), _finite(b[key])
        if first <= 0 or last <= 0:
            raise ValueError("gold values must be positive")
        return last / first - 1
    return {"status": "ok", "mode": mode, "start": start, "end": end,
            "price_return": change("close"), "nav_return_1030": change("nav_1030"),
            "backing_change": change("ounces_per_share"),
            "ounces_per_share": b.get("ounces_per_share"), "premium_pct_1615": b.get("premium_pct_1615"),
            "causal_status": "not_identified",
            "limitations": ["different pricing times", "independent licensed gold benchmark unavailable",
                            "backing change is measured, not automatically attributed to management fees"]}
