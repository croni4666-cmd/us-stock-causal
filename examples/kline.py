"""
examples/kline.py - 4 指数 K 线图 (Phase 3.1 P3-2)

输出:
  - output/kline_<date>.png: 4 subplot 2x2 网格,DIA/QQQ/RSP/QQQE
  - 每 subplot: 1y 蜡烛 + 200 SMA + R1 + S1 (+ 50 SMA 可选)

跑: python examples/kline.py
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from src import proxy  # noqa: F401
from src.kline import plot_4_indices


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.4.0 - 4-index K-line (Phase 3.1 P3-2)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    t0 = time.time()
    today = date.today()

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / f"kline_{today.isoformat()}.png"

    symbols = ["DIA", "QQQ", "RSP", "QQQE"]
    fig = plot_4_indices(symbols=symbols, output_path=out_path, show=False)

    elapsed = time.time() - t0
    size_kb = out_path.stat().st_size / 1024 if out_path.exists() else 0
    print(f"\n{'=' * 72}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  K-line: {out_path} ({size_kb:.0f} KB)")
    print(f"  Symbols: {symbols}")
    print(f"  Lookback: 1y (252 trading days)")
    print(f"  Annotations: 200 SMA + R1 + S1 + 50 SMA")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
