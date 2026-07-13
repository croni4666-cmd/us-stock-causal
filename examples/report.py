"""
examples/report.py - 完整 5 段制报告 (Phase 2.3 P2-9)

输出:
  - 控制台: 4 指数 × 5 段
  - output/report_<date>.md: Markdown 完整报告

跑: python examples/report.py
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
from src.report import render_full_report, five_segment_report, render_markdown


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.3.3 - 5-segment report (Phase 2.3 P2-9)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    t0 = time.time()
    today = date.today()

    symbols = ["DIA", "QQQ", "RSP", "QQQE"]

    # 控制台打印
    for sym in symbols:
        print(render_markdown(five_segment_report(sym)))
        print("-" * 72)

    # Markdown 报告
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    md_path = output_dir / f"report_{today.isoformat()}.md"
    md_path.write_text(render_full_report(symbols), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"\n{'=' * 72}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  Report: {md_path}")
    print(f"  总字数: ~{4*600} (4 指数 × ~600 字/段)")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
