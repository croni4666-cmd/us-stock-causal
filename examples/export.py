"""
examples/export.py - 数据集导出 CLI (Phase 4 P4-1)

从 parquet cache 导出到 CSV / Parquet / Excel,支持时间窗口 + 多 ticker。

跑:
  python examples/export.py --tickers DIA,QQQ,RSP,QQQE --format csv
  python examples/export.py --tickers XLK,XLF --start 2025-01-01 --format excel
  python examples/export.py --tickers QQQ --start 2024-01-01 --end 2024-12-31 --format all

数据源: data/raw/<layer>/<safe_name>.parquet (从 src.thresholds.load_prices)
输出:  data/export/<format>/<ticker>.<ext>  或用户指定 --output-dir
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from loguru import logger

from src.thresholds import load_prices
from src import proxy  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export ticker OHLCV data to CSV/Parquet/Excel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python examples/export.py --tickers DIA,QQQ --format csv
  python examples/export.py --tickers QQQ --start 2025-01-01 --format excel
  python examples/export.py --tickers XLK,XLF,XLE --format all --output-dir data/myexport
        """,
    )
    parser.add_argument(
        "--tickers", required=True,
        help="Comma-separated ticker symbols (e.g. DIA,QQQ,XLK)"
    )
    parser.add_argument(
        "--layer", default="indices",
        choices=["indices", "sectors", "macro", "commodities_futures", "commodities_spot"],
        help="Layer where the ticker data is cached (default: indices)"
    )
    parser.add_argument(
        "--start", default=None,
        help="Start date YYYY-MM-DD (default: earliest in cache)"
    )
    parser.add_argument(
        "--end", default=None,
        help="End date YYYY-MM-DD (default: latest in cache)"
    )
    parser.add_argument(
        "--format", default="csv",
        choices=["csv", "parquet", "excel", "all"],
        help="Output format (default: csv)"
    )
    parser.add_argument(
        "--output-dir", default="data/export",
        help="Output directory (default: data/export)"
    )
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",")]
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"us-stock-causal v0.5.0 - data export (Phase 4 P4-1)")
    print(f"Tickers: {tickers}")
    print(f"Layer: {args.layer}")
    print(f"Format: {args.format}")
    print(f"Date range: {args.start or 'earliest'} → {args.end or 'latest'}")
    print(f"Output dir: {output_dir.relative_to(PROJECT_ROOT) if output_dir.is_relative_to(PROJECT_ROOT) else output_dir}")
    print("=" * 72)

    t0 = time.time()
    total_rows = 0
    ok_count = 0
    err_count = 0

    for ticker in tickers:
        try:
            df = load_prices(ticker, args.layer)
            # 时间窗口
            if args.start:
                df = df[df.index >= args.start]
            if args.end:
                df = df[df.index <= args.end]

            n = len(df)
            total_rows += n

            # 写出
            if args.format in ("csv", "all"):
                p = output_dir / f"{ticker}.csv"
                df.to_csv(p)
            if args.format in ("parquet", "all"):
                p = output_dir / f"{ticker}.parquet"
                df.to_parquet(p)
            if args.format in ("excel", "all"):
                p = output_dir / f"{ticker}.xlsx"
                df.to_excel(p)

            print(f"  ✅ {ticker:8s} ({args.layer:18s}): {n:>5d} rows, "
                  f"{df.index[0].date()} → {df.index[-1].date()}")
            ok_count += 1
        except FileNotFoundError:
            print(f"  ❌ {ticker:8s}: cache file not found (先跑 fetch_all.py)")
            err_count += 1
        except Exception as e:
            print(f"  ❌ {ticker:8s}: {type(e).__name__}: {e}")
            err_count += 1

    elapsed = time.time() - t0
    print(f"\n{'=' * 72}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  ✅ {ok_count}/{len(tickers)} ok ({total_rows:,} rows total)")
    if err_count:
        print(f"  ❌ {err_count} failed")
    print(f"  Output: {output_dir}")
    print(f"{'=' * 72}")
    return 0 if err_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
