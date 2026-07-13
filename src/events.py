"""
src/events.py - 宏观事件日历 (FOMC / CPI / NFP)

Phase 2.2 (P2-7) 事件日历:
  - FOMC 会议日期 (美联储,8 次/年,Fed 提前 1 年公布)
  - CPI 发布日期 (劳工统计局 BLS,每月 ~13 号)
  - NFP 非农就业 (劳工统计局 BLS,每月第一个周五)

**因果意义**:
  - 这些事件是高波动 / 高方向性事件的"已知日历"
  - 在事件前,残差会扩大 (市场观望),事件后,残差均值回归
  - 用户的归因模型里,事件日残差 = "事件特定冲击",不是 weights 错
  - "未来 5 天有什么事件" → 知道什么时候不该相信模型的预测

**v0.3.2 简化版**:
  - 硬编码 2026 日历 (Fed / BLS 公开)
  - 财报日 (per-stock) 留到 v0.3.3 (用 openbb.sec)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CALENDAR_PATH = PROJECT_ROOT / "config" / "events_2026.yaml"


@dataclass
class MacroEvent:
    date: date
    kind: str           # "FOMC" / "CPI" / "NFP" / "PCE" / "PPI" / etc.
    description: str    # e.g. "12月 CPI 公布"
    impact: str = "high"  # "high" / "medium" / "low"

    @property
    def days_until(self) -> int:
        return (self.date - date.today()).days

    def __str__(self) -> str:
        return f"{self.date} ({self.kind}) {self.description}"


def load_calendar() -> list[MacroEvent]:
    """读 config/events_2026.yaml"""
    if not CALENDAR_PATH.exists():
        logger.warning(f"{CALENDAR_PATH} 不存在,返回空")
        return []
    with open(CALENDAR_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    events = []
    for entry in data.get("events", []):
        d = entry["date"]
        if isinstance(d, date):
            d = d  # already date
        else:
            d = date.fromisoformat(d)
        events.append(MacroEvent(
            date=d,
            kind=entry["kind"],
            description=entry["description"],
            impact=entry.get("impact", "high"),
        ))
    return events


def upcoming_events(
    from_date: Optional[date] = None,
    lookahead_days: int = 30,
) -> list[MacroEvent]:
    """未来 N 天内的事件,按日期排序"""
    if from_date is None:
        from_date = date.today()
    end = from_date + timedelta(days=lookahead_days)
    cal = load_calendar()
    return sorted(
        [e for e in cal if from_date <= e.date <= end],
        key=lambda e: e.date,
    )


def past_events(
    from_date: Optional[date] = None,
    lookback_days: int = 30,
) -> list[MacroEvent]:
    """过去 N 天内的事件"""
    if from_date is None:
        from_date = date.today()
    start = from_date - timedelta(days=lookback_days)
    cal = load_calendar()
    return sorted(
        [e for e in cal if start <= e.date <= from_date],
        key=lambda e: e.date,
    )


def next_event(from_date: Optional[date] = None) -> Optional[MacroEvent]:
    """下一个高影响事件"""
    if from_date is None:
        from_date = date.today()
    cal = load_calendar()
    future = sorted([e for e in cal if e.date >= from_date], key=lambda e: e.date)
    return future[0] if future else None


if __name__ == "__main__":
    print(f"今日: {date.today()}")
    print(f"\n未来 30 天事件:")
    for e in upcoming_events(lookahead_days=30):
        print(f"  {e.date} ({e.days_until:+d}d) {e.kind}: {e.description}")
    print(f"\n过去 14 天事件:")
    for e in past_events(lookback_days=14):
        days_ago = -e.days_until
        print(f"  {e.date} ({days_ago}d ago) {e.kind}: {e.description}")
    ne = next_event()
    if ne:
        print(f"\n下一个事件: {ne}")
