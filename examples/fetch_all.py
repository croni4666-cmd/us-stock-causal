"""
examples/fetch_all.py - 拉全 49 ticker (Phase 1 gate)

Phase 1 stop 条件 (ROADMAP P1-8):
  - [ ] 49 ticker 全部能拉 ≥ 2 年数据
  - [ ] parquet 缓存能复用,二次拉只取增量
  - [ ] 商品 ticker 期货+现货都尝试拉,缺现货时 warn 跳过
  - [ ] 1 轮拉全 < 1 min (顺序)

跑: python examples/fetch_all.py
输出:
  data/raw/{indices,sectors,macro,commodities_futures,commodities_spot}/*.parquet
  终端打印每 ticker 状态 + 总耗时
"""
from __future__ import annotations

import sys
import time
import yaml
from pathlib import Path

import pandas as pd  # noqa: E402

# proxy + sys.path 必须在 import data / cache 之前
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import proxy  # noqa: F401  (副作用: import 时设 HTTP_PROXY)
from src import data, cache  # noqa: E402

# 强制 UTF-8 输出 (避免 Windows GBK, fetch_all.py print emoji ♻️ 失败)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONFIG_PATH = PROJECT_ROOT / "config" / "tickers.yaml"
CACHE_ROOT = PROJECT_ROOT / "data" / "raw"


def load_universe() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["universe"], cfg.get("fetch", {})


def fetch_layer(
    layer_name: str,
    entries: list[dict],
    fetch_cfg: dict,
    skip_on_fail: bool = False,
) -> dict:
    """
    拉一整层 (indices / sectors / macro / commodities_*).
    Returns: { "ok": int, "fail": int, "rows": int, "elapsed_s": float, "details": [...] }
    """
    lookback_days = fetch_cfg.get("lookback_days", 730)
    start_date = (pd.Timestamp.now() - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = None  # 今天

    ok = fail = 0
    total_rows = 0
    details = []
    t_layer = time.time()

    for entry in entries:
        sym = entry["symbol"]
        optional = entry.get("optional", False)
        t0 = time.time()
        try:
            df, status = cache.update_or_fetch(
                symbol=sym,
                layer=layer_name,
                fetcher=data.fetch,
                cache_root=CACHE_ROOT,
                start=start_date,
                end=end_date,
            )
            elapsed = time.time() - t0
            if df.empty:
                warn = " (skip, no data)" if optional else " (FAIL)"
                details.append(f"  {'⚠️' if optional else '❌'} {sym:8s} [{status:11s}] {warn}  {elapsed:.1f}s")
                if not optional:
                    fail += 1
                # 现货缺数据,optional=True,只 warn 不算 fail
            else:
                ok += 1
                total_rows += len(df)
                marker = "✅" if status == "full" else ("♻️" if status == "incremental" else "💾")
                details.append(f"  {marker} {sym:8s} [{status:11s}] {len(df):>5d} rows  {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - t0
            details.append(f"  ❌ {sym:8s} [error      ] {elapsed:.1f}s  {type(e).__name__}: {e}")
            if not optional:
                fail += 1

    return {
        "ok": ok,
        "fail": fail,
        "rows": total_rows,
        "elapsed_s": time.time() - t_layer,
        "details": details,
    }


def pd_now():
    """避免引入 pandas,内部用"""
    return pd.Timestamp.now()


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.2.0 — fetch_all (Phase 1 gate)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    universe, fetch_cfg = load_universe()
    lookback_days = fetch_cfg.get("lookback_days", 730)
    print(f"Lookback: {lookback_days} days (~{lookback_days/365:.1f} years)")
    print(f"Cache root: {CACHE_ROOT}")
    print()

    grand_total = {"ok": 0, "fail": 0, "rows": 0}
    t0_all = time.time()

    # 1. 指数
    print(f"\n[1/5] 指数 ({len(universe['indices'])} ticker)")
    r = fetch_layer("indices", universe["indices"], fetch_cfg)
    grand_total["ok"] += r["ok"]; grand_total["fail"] += r["fail"]; grand_total["rows"] += r["rows"]
    for d in r["details"]: print(d)
    print(f"  -> {r['ok']} OK / {r['fail']} fail, {r['rows']} rows, {r['elapsed_s']:.1f}s")

    # 2. 行业
    print(f"\n[2/5] 行业 ({len(universe['sectors'])} ticker)")
    r = fetch_layer("sectors", universe["sectors"], fetch_cfg)
    grand_total["ok"] += r["ok"]; grand_total["fail"] += r["fail"]; grand_total["rows"] += r["rows"]
    for d in r["details"]: print(d)
    print(f"  -> {r['ok']} OK / {r['fail']} fail, {r['rows']} rows, {r['elapsed_s']:.1f}s")

    # 3. 宏观
    print(f"\n[3/5] 宏观 ({len(universe['macro'])} ticker)")
    r = fetch_layer("macro", universe["macro"], fetch_cfg)
    grand_total["ok"] += r["ok"]; grand_total["fail"] += r["fail"]; grand_total["rows"] += r["rows"]
    for d in r["details"]: print(d)
    print(f"  -> {r['ok']} OK / {r['fail']} fail, {r['rows']} rows, {r['elapsed_s']:.1f}s")

    # 4. 商品期货
    print(f"\n[4/5] 商品期货 ({len(universe['commodities']['futures'])} ticker)")
    r = fetch_layer("commodities_futures", universe["commodities"]["futures"], fetch_cfg)
    grand_total["ok"] += r["ok"]; grand_total["fail"] += r["fail"]; grand_total["rows"] += r["rows"]
    for d in r["details"]: print(d)
    print(f"  -> {r['ok']} OK / {r['fail']} fail, {r['rows']} rows, {r['elapsed_s']:.1f}s")

    # 5. 商品现货 ETF 代理 (1:1 跟踪商品价格)
    print(f"\n[5/5] 商品现货 ETF ({len(universe['commodities']['spot_etf'])} ticker, 与 14 期货 1:1 配对)")
    r = fetch_layer("commodities_spot_etf", universe["commodities"]["spot_etf"], fetch_cfg, skip_on_fail=True)
    grand_total["ok"] += r["ok"]; grand_total["fail"] += r["fail"]; grand_total["rows"] += r["rows"]
    for d in r["details"]: print(d)
    print(f"  -> {r['ok']} OK / {r['fail']} fail, {r['rows']} rows, {r['elapsed_s']:.1f}s")

    # 总结
    elapsed = time.time() - t0_all
    print()
    print("=" * 72)
    print(f"Phase 1 总结: {grand_total['ok']} OK / {grand_total['fail']} fail")
    print(f"  总行数: {grand_total['rows']:,}")
    print(f"  总耗时: {elapsed:.1f}s (Phase 1 gate 验收: < 60s)")
    status = "✅ 通过" if elapsed < 60 and grand_total["fail"] <= 7 else "⚠️ 部分通过"
    print(f"  状态: {status}")
    print("=" * 72)
    print(f"\n下一步: Phase 2 - 因果分析 (归因分解 + 历史模式匹配 + 关键阈值)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
