"""
src/report.py - 5 段制报告生成

Phase 2.3 (P2-9) 设计:
  每个标的 5 段:
    ① 5 日行情
    ② 5 日归因 (sector weights)
    ③ 关键阈值 (SMA + pivot + 52w)
    ④ 历史相似 (pattern match, 5d forward 统计)
    ⑤ 风险 (信号矛盾 + 下个事件 + 距离超买)

字数: ~120 字/段 × 5 = 600 字/标的
对比 v0.2 报告 3000+ 字,信息密度 5x

**因果优先原则**:
  - ①-④ 客观数据 (从 parquet 算的)
  - ⑤ 综合判断 (信号聚合 + 事件日历)
  - 不输出"看多/看空"结论
  - 输出"驱动 + 阈值 + 历史 + 风险",让用户自己判断
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from src.thresholds import get_thresholds, load_prices
from src.attribution import attribute_index
from src.patterns import find_similar_patterns
from src.events import next_event
from src.returns import compute_returns, cumulative_return
from src.signals import aggregate_signals


def _segment_1_market(symbol: str, layer: str, lookback_days: int) -> str:
    """① 5 日行情"""
    df = load_prices(symbol, layer)
    rets = compute_returns(df["close"], method="simple")
    daily = rets.iloc[-lookback_days:]

    cum = cumulative_return(daily, method="simple")
    best_idx = daily.idxmax()
    worst_idx = daily.idxmin()
    best_date = best_idx.date() if hasattr(best_idx, 'date') else str(best_idx)
    worst_date = worst_idx.date() if hasattr(worst_idx, 'date') else str(worst_idx)

    return (
        f"5 日累计 {cum*100:+.2f}%, "
        f"最好 {best_date} (+{daily[best_idx]*100:.2f}%), "
        f"最差 {worst_date} ({daily[worst_idx]*100:+.2f}%)"
    )


def _segment_2_attribution(symbol: str, lookback_days: int) -> str:
    """② 5 日归因"""
    r = attribute_index(symbol, lookback_days=lookback_days)
    # top 3 贡献(按绝对值)
    contribs = sorted(
        r["sector_contributions_pct"].items(),
        key=lambda x: -abs(x[1])
    )[:3]
    parts = []
    for s, v in contribs:
        if v > 0.05:
            parts.append(f"{s}+{v:.2f}%")
        elif v < -0.05:
            parts.append(f"{s}{v:.2f}%")
    contrib_str = " / ".join(parts) if parts else "(各 sector 贡献均 < 0.05%)"
    return (
        f"主升 {contrib_str}, "
        f"残差 {r['residual_pct']:+.2f}%"
    )


def _segment_3_thresholds(symbol: str, layer: str) -> str:
    """③ 关键阈值"""
    t = get_thresholds(symbol)
    s200 = t["vs_sma"]["sma_200"]
    s200_str = f"200 SMA {s200['position']} {s200['pct']:+.2f}%"
    pos52w = t["range_52w"]["position_pct"]
    p = t["pivots"]
    return (
        f"现价 ${t['last_close']}, "
        f"{s200_str}, 52w {pos52w}%, "
        f"R1 ${p['r1']} / S1 ${p['s1']}"
    )


def _segment_4_patterns(symbol: str, layer: str) -> str:
    """④ 历史相似"""
    p = find_similar_patterns(symbol, pattern_length=20, n_matches=10, forecast_horizon=5)
    return (
        f"20d pattern 相似 top {p['n_matches']}, "
        f"5d fwd avg {p['avg_forward_return']:+.2f}% / "
        f"win {p['win_rate']:.0%} / "
        f"max {p['max_forward']:+.2f}% / min {p['min_forward']:+.2f}%"
    )


def _segment_5_risk(symbol: str) -> str:
    """⑤ 风险"""
    agg = aggregate_signals(symbol)
    warnings = []

    # 信号矛盾
    if agg.contradiction_score >= 0.5:
        warnings.append(f"信号矛盾 score={agg.contradiction_score:.2f}({agg.verdict})")
    elif agg.contradiction_score >= 0.3:
        warnings.append(f"信号部分一致 score={agg.contradiction_score:.2f}")

    # 事件
    ne = next_event()
    if ne and ne.days_until is not None:
        if ne.days_until <= 7:
            warnings.append(f"{ne.days_until}d 后 {ne.kind}({ne.description})")
        elif ne.days_until <= 14:
            warnings.append(f"{ne.days_until}d 后 {ne.kind}")

    # 距离超买
    t = get_thresholds(symbol)
    s200_pct = t["vs_sma"]["sma_200"]["pct"]
    if s200_pct > 12:
        warnings.append(f"200 SMA {s200_pct:+.1f}% 距超买较近")

    return "; ".join(warnings) if warnings else "近期无重大风险"


def five_segment_report(symbol: str, layer: str = "indices", lookback_days: int = 5) -> dict:
    """生成 5 段制报告"""
    return {
        "symbol": symbol,
        "as_of": str(date.today()),
        "lookback_days": lookback_days,
        "segment_1_market": _segment_1_market(symbol, layer, lookback_days),
        "segment_2_attribution": _segment_2_attribution(symbol, lookback_days),
        "segment_3_thresholds": _segment_3_thresholds(symbol, layer),
        "segment_4_patterns": _segment_4_patterns(symbol, layer),
        "segment_5_risk": _segment_5_risk(symbol),
    }


def render_markdown(report: dict) -> str:
    """渲染单个指数 5 段制报告"""
    sym = report["symbol"]
    return f"""## {sym} — {report['as_of']} (5 日报告)

**① 5 日行情**: {report['segment_1_market']}

**② 5 日归因**: {report['segment_2_attribution']}

**③ 关键阈值**: {report['segment_3_thresholds']}

**④ 历史相似**: {report['segment_4_patterns']}

**⑤ 风险**: {report['segment_5_risk']}
"""


def render_full_report(symbols: list[str], layer: str = "indices") -> str:
    """渲染 4 指数完整 5 段制报告"""
    today = date.today()
    lines = [
        f"# 📊 美股每日分析报告 (5 段制) — {today}",
        f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**模型**: Phase 2 全套 (归因 v0.3.0 + 阈值/残差 v0.3.1 + 模式/事件 v0.3.2 + 信号/5段 v0.3.3)",
        f"**字数**: 每标的 ~600 字,5 段结构 (行情 / 归因 / 阈值 / 相似 / 风险)",
        f"\n---\n",
    ]
    for sym in symbols:
        report = five_segment_report(sym, layer=layer)
        lines.append(render_markdown(report))
        lines.append("\n---\n")
    lines.append(
        "\n*免责声明:本报告由自动化分析生成,基于历史数据 + 公开 sector weights。"
        "**不构成投资建议**。信号矛盾 score 越高,越要谨慎。事件前 1 周内的预测需打折。*\n"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    for sym in ["DIA", "QQQ", "RSP", "QQQE"]:
        print(render_markdown(five_segment_report(sym)))
        print()
