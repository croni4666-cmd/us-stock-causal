"""src/checks/vix_spike.py - P8-3 VIX 急升检测

读 data/raw/macro/_VIX.parquet, 检查:
- 当前 VIX > 30 (高恐慌) → warning
- 1 日涨跌幅 > 15% → warning
- 当前 VIX > 40 (极端恐慌) → error
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import alert_logger

VIX_PATH = PROJECT_ROOT / "data" / "raw" / "macro" / "_VIX.parquet"

# 阈值 (跟 v0.5.1 README 标注的 "高 VIX > 25" 略调高, 避免日常噪声)
HIGH_VIX = 30.0
EXTREME_VIX = 40.0
SPIKE_PCT = 15.0  # 1 日涨幅


def _read_vix_series():
    """读 _VIX.parquet, 返 (date_series, value_series). 读不到返 ([], [])"""
    try:
        import pandas as pd
        df = pd.read_parquet(VIX_PATH)
        # 列名尝试: 'Close' / 'close' / 'Adj Close' / 直接是 value
        for col in ["Close", "close", "Adj Close", "adj_close"]:
            if col in df.columns:
                vals = df[col]
                break
        else:
            # 找第一个 numeric 列
            num_cols = [c for c in df.columns if str(df[c].dtype).startswith(("float", "int"))]
            if not num_cols:
                return [], []
            vals = df[num_cols[0]]
        return list(df.index), list(vals)
    except Exception:
        return [], []


def check(date_str: str) -> list[dict]:
    """读 VIX, 阈值告警"""
    if not VIX_PATH.exists():
        return [alert_logger.make_alert(
            alert_type="vix_spike",
            subject="data/raw/macro/_VIX.parquet",
            message="VIX parquet 不存在, 跳过 spike 检查",
            severity="warning",
            details={"missing_file": "data/raw/macro/_VIX.parquet"},
        )]

    dates, values = _read_vix_series()
    if not values:
        return [alert_logger.make_alert(
            alert_type="vix_spike",
            subject="_VIX.parquet",
            message="VIX parquet 读不到 / 无数据",
            severity="warning",
            details={"file": "data/raw/macro/_VIX.parquet"},
        )]

    current = float(values[-1])
    alerts = []

    # 当前水平
    if current >= EXTREME_VIX:
        alerts.append(alert_logger.make_alert(
            alert_type="vix_spike",
            subject="VIX level",
            message=f"VIX {current:.2f} (>= {EXTREME_VIX} 极端恐慌)",
            severity="error",
            details={"current": current, "threshold": EXTREME_VIX, "kind": "level"},
        ))
    elif current >= HIGH_VIX:
        alerts.append(alert_logger.make_alert(
            alert_type="vix_spike",
            subject="VIX level",
            message=f"VIX {current:.2f} (>= {HIGH_VIX} 高恐慌)",
            severity="warning",
            details={"current": current, "threshold": HIGH_VIX, "kind": "level"},
        ))

    # 1 日涨幅 (用最后两个点)
    if len(values) >= 2:
        try:
            prev = float(values[-2])
            if prev > 0:
                pct = (current - prev) / prev * 100.0
                if abs(pct) >= SPIKE_PCT:
                    sev = "error" if pct > 0 else "warning"  # 涨是 spike, 跌是 "calm down" 不严重
                    direction = "spike" if pct > 0 else "crash"
                    alerts.append(alert_logger.make_alert(
                        alert_type="vix_spike",
                        subject="VIX 1d change",
                        message=f"VIX {prev:.2f} → {current:.2f} ({pct:+.1f}% {direction})",
                        severity=sev,
                        details={"prev": prev, "current": current, "pct": round(pct, 2), "kind": direction},
                    ))
        except (ValueError, TypeError):
            pass

    return alerts


__all__ = ["check", "HIGH_VIX", "EXTREME_VIX", "SPIKE_PCT"]
