"""src/checks/ticker_fail.py - P8-4 单 ticker 失败 / yfinance 限流检测

读:
- data/cache/yfinance_rate_limit.json (P7-6 限流状态) → 限流中 → alert
- data/raw/*/ 扫描小 parquet (< 1KB 通常是空 fetch 返回的占位)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import alert_logger
from src.yfinance_rate_limit import is_rate_limited, get_rate_limit_info

RATE_LIMIT_PATH = PROJECT_ROOT / "data" / "cache" / "yfinance_rate_limit.json"
DATA_RAW = PROJECT_ROOT / "data" / "raw"
TINY_PARQUET_BYTES = 1024  # < 1KB 通常是 fetch 失败占位


def _check_rate_limit() -> list[dict]:
    """查 P7-6 限流状态文件"""
    alerts = []
    info = get_rate_limit_info()
    if info:
        # info 包含 hit_count, expires_at, last_symbol
        last = info.get("last_symbol", "?")
        hits = info.get("hit_count", 0)
        exp = info.get("expires_at", "?")
        alerts.append(alert_logger.make_alert(
            alert_type="ticker_fail",
            subject="yfinance rate limit",
            message=f"yfinance 限流中 (last={last}, hits={hits}, expires={exp})",
            severity="error",
            details=info,
        ))
    return alerts


def _check_tiny_parquets() -> list[dict]:
    """扫 data/raw/ 子目录, 找 < 1KB 的 parquet (fetch 失败占位)"""
    alerts = []
    if not DATA_RAW.exists():
        return alerts
    for sub_dir in DATA_RAW.iterdir():
        if not sub_dir.is_dir() or sub_dir.name.startswith("."):
            continue
        for pq in sub_dir.glob("*.parquet"):
            try:
                size = pq.stat().st_size
            except OSError:
                continue
            if size < TINY_PARQUET_BYTES:
                alerts.append(alert_logger.make_alert(
                    alert_type="ticker_fail",
                    subject=f"data/raw/{sub_dir.name}/{pq.name}",
                    message=f"Parquet size {size} bytes (< {TINY_PARQUET_BYTES}), 可能 fetch 失败占位",
                    severity="warning",
                    details={
                        "file": f"data/raw/{sub_dir.name}/{pq.name}",
                        "size_bytes": size,
                    },
                ))
    return alerts


def check(date_str: str) -> list[dict]:
    """组合 限流状态 + 异常小 parquet 检测"""
    return _check_rate_limit() + _check_tiny_parquets()


__all__ = ["check", "TINY_PARQUET_BYTES"]
