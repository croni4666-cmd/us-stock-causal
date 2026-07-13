"""
src/signals.py - 多源信号聚合

Phase 2.3 (P2-8) 思路:
  单一信号不可靠 (历史胜率 ~50%),但多个信号一致时可靠性提升
  3 个短中期信号:
    1. Pattern match (P2-5) — 历史上类似 20d pattern 后续 5d 表现
    2. Threshold pressure (P2-6) — 200 SMA 偏离度,距超买多远
    3. Event proximity (P2-7) — 距下个高影响事件天数

  Contradiction score:
    3 源一致 = low (高信度)
    2 一致 1 相反 = medium
    3 各异 = high (低信度)

v0.3.3 简化版: 只生成 signal snapshot + contradiction 数字,不做"历史胜率回测"
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Optional

from src.thresholds import get_thresholds
from src.patterns import find_similar_patterns
from src.events import next_event


@dataclass
class SignalSnapshot:
    """单个信号快照"""
    name: str
    direction: str         # "bullish" / "bearish" / "neutral"
    confidence: float      # 0-1
    detail: str


@dataclass
class SignalAggregate:
    """多源信号聚合"""
    symbol: str
    as_of: str
    signals: list[SignalSnapshot]
    bullish_count: int
    bearish_count: int
    neutral_count: int
    contradiction_score: float  # 0-1, 越高越不一致
    verdict: str                # "high_conf_bull" / "high_conf_bear" / "mixed"
    summary: str


def _classify_pattern(snap: dict) -> SignalSnapshot:
    """从 pattern match 结果生成信号"""
    avg = snap["avg_forward_return"]
    win = snap["win_rate"]
    n = snap["n_matches"]
    if win >= 0.7 and avg > 0.005:  # 70%+ win, +0.5%+ avg
        direction = "bullish"
        conf = min(1.0, win * 1.2)
    elif win <= 0.3 and avg < -0.005:
        direction = "bearish"
        conf = min(1.0, (1 - win) * 1.2)
    else:
        direction = "neutral"
        conf = 0.5
    return SignalSnapshot(
        name="pattern_match",
        direction=direction,
        confidence=round(conf, 2),
        detail=f"top {n} similar 20d patterns, 5d forward avg {avg:+.2f}% / win {win:.0%}",
    )


def _classify_threshold(snap: dict) -> SignalSnapshot:
    """从 threshold 结果生成信号"""
    s200 = snap["vs_sma"]["sma_200"]["pct"]
    pos52w = snap["range_52w"]["position_pct"]
    # 200 SMA < -5% = bearish (below trend), > +10% = overbought risk (bearish)
    if s200 < -5:
        direction = "bearish"
        conf = min(1.0, abs(s200) / 15)
    elif s200 > 10:
        direction = "bearish"  # overbought
        conf = 0.5 + (s200 - 10) / 20
    elif s200 > 0:
        direction = "bullish"
        conf = min(0.8, s200 / 10)
    else:
        direction = "neutral"
        conf = 0.5
    return SignalSnapshot(
        name="threshold_pressure",
        direction=direction,
        confidence=round(conf, 2),
        detail=f"200 SMA {s200:+.2f}%, 52w position {pos52w}%",
    )


def _classify_event() -> Optional[SignalSnapshot]:
    """从 event 日历生成信号 (1 周内事件 = 风险预警,不是方向)"""
    ne = next_event()
    if ne is None:
        return None
    days = ne.days_until
    if days is None or days < 0:
        return None
    if days <= 3:
        direction = "bearish"  # 3 天内高影响事件,短期风险
        conf = 0.9
    elif days <= 7:
        direction = "bearish"
        conf = 0.6
    else:
        direction = "neutral"
        conf = 0.3
    return SignalSnapshot(
        name="event_proximity",
        direction=direction,
        confidence=round(conf, 2),
        detail=f"next {ne.kind} in {days}d ({ne.description})",
    )


def aggregate_signals(symbol: str) -> SignalAggregate:
    """聚合 3 源信号"""
    thresholds = get_thresholds(symbol)
    patterns = find_similar_patterns(symbol, pattern_length=20, n_matches=10, forecast_horizon=5)

    sigs = [
        _classify_pattern(patterns),
        _classify_threshold(thresholds),
    ]
    event_sig = _classify_event()
    if event_sig:
        sigs.append(event_sig)

    bull = sum(1 for s in sigs if s.direction == "bullish")
    bear = sum(1 for s in sigs if s.direction == "bearish")
    neut = sum(1 for s in sigs if s.direction == "neutral")

    n = len(sigs)
    if n == 0:
        verdict = "unknown"
        score = 0.0
    else:
        # 一致度: 同方向占比 - 0.5 * 不同方向占比
        max_count = max(bull, bear, neut)
        consistency = max_count / n
        # contradiction = 1 - consistency (但保证 ≥ 0)
        score = round(1.0 - consistency, 3)

        if consistency >= 0.8:
            if bull > 0:
                verdict = "high_conf_bull"
            elif bear > 0:
                verdict = "high_conf_bear"
            else:
                verdict = "high_conf_neutral"
        else:
            verdict = "mixed"

    # 拼 summary
    summary = (
        f"bullish={bull} bearish={bear} neutral={neut} "
        f"contradiction={score:.2f} verdict={verdict}"
    )

    return SignalAggregate(
        symbol=symbol,
        as_of=str(date.today()),
        signals=[asdict(s) if hasattr(s, '__dataclass_fields__') else s for s in sigs],
        bullish_count=bull,
        bearish_count=bear,
        neutral_count=neut,
        contradiction_score=score,
        verdict=verdict,
        summary=summary,
    )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    for sym in ["DIA", "QQQ", "RSP", "QQQE"]:
        agg = aggregate_signals(sym)
        print(f"\n=== {sym} ===")
        for s in agg.signals:
            if isinstance(s, dict):
                print(f"  {s['name']:20s} {s['direction']:8s} conf={s['confidence']:.2f}  {s['detail']}")
            else:
                print(f"  {s.name:20s} {s.direction:8s} conf={s.confidence:.2f}  {s.detail}")
        print(f"  --> {agg.summary}")
