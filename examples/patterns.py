"""
examples/patterns.py - 4 指数历史模式匹配 (Phase 2.2 P2-5)

输出: 4 指数 × 20d pattern match × 5d forward 统计
跑: python examples/patterns.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from src import proxy  # noqa: F401
from src.patterns import find_similar_patterns


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.3.2 - pattern match (Phase 2.2 P2-5)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    results = {}
    for sym in ["DIA", "QQQ", "RSP", "QQQE"]:
        print(f"\n--- {sym} ---")
        r = find_similar_patterns(sym, pattern_length=20, n_matches=5, forecast_horizon=5)
        results[sym] = r
        print(f"current pattern ends: {r['pattern_end']}")
        print(f"  5d forward (top 5 similar):")
        print(f"    avg {r['avg_forward_return']:+.2f}% / median {r['median_forward_return']:+.2f}% / "
              f"win {r['win_rate']:.0%} / max {r['max_forward']:+.2f}% / min {r['min_forward']:+.2f}%")
        for i, m in enumerate(r["top_matches"], 1):
            print(f"    #{i} {m['start_date']} ~ {m['end_date']}  corr={m['correlation']:+.3f}  "
                  f"5d fwd {m['forward_return']:+.2f}%")

    # 写 Markdown 报告
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    md_path = output_dir / f"patterns_{today}.md"
    lines = [
        f"# Historical Pattern Match - {today}",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n**Method**: Pearson correlation on 20-day daily returns, top 5 most similar windows, 5-day forward return",
        f"\n**Caution**: 统计上的相似,不等于因果。当前宏观环境 (rate, inflation, geopolitics) 跟历史可能不同。",
        f"\n---\n",
    ]
    for sym, r in results.items():
        lines.append(f"\n## {sym}\n")
        lines.append(f"Pattern ends: **{r['pattern_end']}**\n")
        lines.append(f"### 5d Forward (top 5 similar patterns)")
        lines.append(f"- avg {r['avg_forward_return']:+.2f}%")
        lines.append(f"- median {r['median_forward_return']:+.2f}%")
        lines.append(f"- **win rate: {r['win_rate']:.0%}**")
        lines.append(f"- range: {r['min_forward']:+.2f}% ~ {r['max_forward']:+.2f}%\n")
        lines.append("| # | start | end | corr | 5d fwd % |")
        lines.append("|---|-------|-----|------|----------|")
        for i, m in enumerate(r["top_matches"], 1):
            lines.append(f"| {i} | {m['start_date']} | {m['end_date']} | {m['correlation']:+.3f} | {m['forward_return']:+.2f}% |")
        lines.append("\n---\n")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"\n{'=' * 72}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  Report: {md_path}")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
