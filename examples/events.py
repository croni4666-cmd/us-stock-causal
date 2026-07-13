"""
examples/events.py - 宏观事件日历 (Phase 2.2 P2-7)

输出: 未来 30/60 天 FOMC / CPI / NFP / PCE 事件
跑: python examples/events.py
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
from src.events import upcoming_events, past_events, next_event


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.3.2 - macro events (Phase 2.2 P2-7)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    today = date.today()
    print(f"\n今日: {today}\n")

    # 过去 14 天
    print("## 过去 14 天事件")
    past = past_events(lookback_days=14)
    if past:
        for e in past:
            days_ago = -e.days_until
            print(f"  {e.date} ({days_ago}d ago) [{e.kind}] {e.description}")
    else:
        print("  (无)")

    # 未来 30 天
    print("\n## 未来 30 天事件")
    up30 = upcoming_events(lookahead_days=30)
    if up30:
        print(f"  {'日期':12s} {'天数':>5s}  {'类型':6s}  描述")
        for e in up30:
            print(f"  {str(e.date):12s} {e.days_until:+5d}  {e.kind:6s}  {e.description}")
    else:
        print("  (无)")

    # 未来 60 天
    print("\n## 未来 60 天事件 (含 30-60 天)")
    up60 = upcoming_events(lookahead_days=60)
    extra = [e for e in up60 if e not in up30]
    for e in extra:
        print(f"  {str(e.date):12s} {e.days_until:+5d}  {e.kind:6s}  {e.description}")

    # 下一个高影响事件
    ne = next_event()
    if ne:
        print(f"\n## 下个事件")
        print(f"  {ne.date} ({ne.days_until:+d}d) [{ne.kind}] {ne.description}")
        if ne.days_until <= 7:
            print(f"  ⚠️ 1 周内,模型预测需谨慎 (事件驱动残差大)")

    # 写 Markdown
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    md_path = output_dir / f"events_{today.isoformat()}.md"
    lines = [
        f"# Macro Events - {today}",
        f"\n**Source**: config/events_2026.yaml (hardcoded FOMC/CPI/NFP/PCE schedule)",
        "\n---\n",
        "## 未来 60 天事件",
        "| 日期 | 天数 | 类型 | 描述 |",
        "|------|------|------|------|",
    ]
    for e in upcoming_events(lookahead_days=60):
        lines.append(f"| {e.date} | {e.days_until:+d} | {e.kind} | {e.description} |")
    if ne:
        lines.append(f"\n**下一个事件**: {ne.date} ({ne.days_until:+d}d) {ne.description}")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'=' * 72}")
    print(f"Report: {md_path}")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
