"""
examples/data_quality.py - Phase 1 数据质量 gate

P1-10 验收: 在 Phase 2 因果分析之前,必须保证所有 parquet 数据干净。
跑这个 gate 失败的话,Phase 2 跑出来的归因也没意义。

检查项 (每个 parquet):
  1. 存在性      — 文件存在且非空
  2. 列名规范    — 必须有 open/high/low/close/volume
  3. 无 NaN      — 核心列 (OHLC) 不能有 NaN
  4. 单调索引    — DatetimeIndex 必须递增
  5. 无重复日期  — index 不能有重复
  6. 价格合法    — close > 0, high >= low
  7. 成交量合法  — volume >= 0
  8. 时效性      — 最新日期距今 < 7 个日历日 (考虑周末/节假日)

跑: python examples/data_quality.py
输出: 每个 parquet 的 PASS/FAIL + 失败原因 + 总体验收
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CACHE_ROOT = PROJECT_ROOT / "data" / "raw"
REQUIRED_COLS = {"open", "high", "low", "close", "volume"}
MAX_STALENESS_DAYS = 7


def check_one(parquet_path: Path) -> tuple[bool, list[str]]:
    """
    单个 parquet 跑所有检查。
    Returns: (overall_pass, list_of_failure_messages)
    """
    errors: list[str] = []

    # 1. 存在性
    if not parquet_path.exists():
        return False, ["file not found"]
    if parquet_path.stat().st_size == 0:
        return False, ["file empty"]

    # 读 parquet
    try:
        df = pd.read_parquet(parquet_path)
    except Exception as e:
        return False, [f"read error: {e}"]

    if df.empty:
        return False, ["empty dataframe"]

    # 2. 列名规范
    missing_cols = REQUIRED_COLS - set(df.columns)
    if missing_cols:
        errors.append(f"missing cols: {missing_cols}")

    # 只检查核心列
    core_cols = [c for c in REQUIRED_COLS if c in df.columns]

    # 3. 无 NaN
    nan_counts = df[core_cols].isna().sum()
    if nan_counts.any():
        nan_details = {c: int(n) for c, n in nan_counts.items() if n > 0}
        errors.append(f"NaN: {nan_details}")

    # 4. 单调索引
    if not df.index.is_monotonic_increasing:
        errors.append("index not monotonic")

    # 5. 无重复
    n_dup = df.index.duplicated().sum()
    if n_dup > 0:
        errors.append(f"duplicate dates: {n_dup}")

    # 6. 价格合法
    if "close" in df.columns:
        n_neg_close = (df["close"] <= 0).sum()
        if n_neg_close:
            errors.append(f"close <= 0: {n_neg_close} rows")
    if {"high", "low"}.issubset(set(df.columns)):
        n_inverted = (df["high"] < df["low"]).sum()
        if n_inverted:
            errors.append(f"high < low: {n_inverted} rows (inverted)")

    # 7. 成交量合法
    if "volume" in df.columns:
        n_neg_vol = (df["volume"] < 0).sum()
        if n_neg_vol:
            errors.append(f"volume < 0: {n_neg_vol} rows")

    # 8. 时效性
    last_date = df.index.max()
    if pd.notna(last_date):
        days_stale = (pd.Timestamp.now().normalize() - pd.Timestamp(last_date).normalize()).days
        if days_stale > MAX_STALENESS_DAYS:
            errors.append(f"stale: last={last_date.date()}, {days_stale} days ago")

    return (len(errors) == 0), errors


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.2.1 — data_quality (Phase 1 gate P1-10)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Cache root: {CACHE_ROOT}")
    print("=" * 72)

    # 扫描所有 parquet
    all_parquets = sorted(CACHE_ROOT.rglob("*.parquet"))
    if not all_parquets:
        print(f"❌ 没有 parquet 文件,先跑 fetch_all.py")
        return 1

    print(f"扫描到 {len(all_parquets)} 个 parquet\n")

    # 按层分组
    by_layer: dict[str, list[Path]] = {}
    for p in all_parquets:
        layer = p.parent.name
        by_layer.setdefault(layer, []).append(p)

    overall_pass = 0
    overall_fail = 0
    all_errors: list[str] = []

    for layer in sorted(by_layer.keys()):
        print(f"[{layer}] {len(by_layer[layer])} files")
        for pq in sorted(by_layer[layer]):
            # 从 layer/filename 反推 ticker
            rel = pq.relative_to(CACHE_ROOT).as_posix()
            passed, errors = check_one(pq)
            n_rows = len(pd.read_parquet(pq)) if pq.exists() and pq.stat().st_size > 0 else 0
            if passed:
                overall_pass += 1
                print(f"  ✅ {pq.stem:8s}  {n_rows:>4d} rows")
            else:
                overall_fail += 1
                print(f"  ❌ {pq.stem:8s}  {n_rows:>4d} rows  {' | '.join(errors)}")
                for e in errors:
                    all_errors.append(f"{rel}: {e}")
        print()

    # 总结
    print("=" * 72)
    total = overall_pass + overall_fail
    if overall_fail == 0:
        print(f"✅ Phase 1 数据质量 gate 通过: {overall_pass}/{total} parquet 全 PASS")
        print(f"   可以安全进入 Phase 2 (因果分析)")
        return 0
    else:
        print(f"⚠️ Phase 1 数据质量 gate 部分失败: {overall_pass}/{total} PASS, {overall_fail} FAIL")
        print(f"\n失败明细:")
        for e in all_errors:
            print(f"  - {e}")
        print(f"\n建议:重跑 fetch_all.py 更新缓存,或调查根本原因")
        return 1


if __name__ == "__main__":
    sys.exit(main())
