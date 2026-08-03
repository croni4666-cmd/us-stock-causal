"""src/checks/stale.py - P8-1 data staleness check

扫描 data/raw/*/ 所有 parquet 的 LastWriteTime:
- > threshold_days (calendar days) → alert (默认 3d 跟 ROADMAP P8-2 写的 ">3d" 一致)
- severity: error (>7d), warning (3-7d)
- subject: 子目录 (e.g. "data/raw/commodities_spot_etf")
- 跳过 .gitkeep, 隐藏文件, 非 parquet

设计 (ROADMAP P8-2):
- 用 calendar days, 不是 business days (周末数据不刷是"正常 0 笔", 但 LastWriteTime 老 4d
  仍然是 stale — 反正 market closed 也只是 file 不刷, 不影响 staleness 判断)
- 阈值 3d / 7d (calendar) 跟 ROADMAP 写的 ">3d" 对齐
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import alert_logger

DATA_RAW = PROJECT_ROOT / "data" / "raw"

# 默认: 3 calendar days (ROADMAP P8-2 写的 ">3d"), 7d+ → error
DEFAULT_THRESHOLD_DAYS = 3
ERROR_THRESHOLD_DAYS = 7

# 排除目录 (跨项目数据, 不属于 us-stock-causal 检查范围)
# 2026-08-03 add: nvda_cf_cache 是 paper-agent 的 NVDA cash flow cache, 不是我们的
# 未来加 exclude: 编辑此列表, 或在 config.yaml 配 (后续 P9.1.2 工作)
EXCLUDE_DIRS = {
    "nvda_cf_cache",  # paper-agent (paper-agent 项目)
    # 其它跨项目 cache 加这里
}


def _is_stale(last_write: datetime, ref: datetime) -> tuple[bool, int, str]:
    """判断 parquet 是否 stale (calendar days, 跳过同日)

    Returns:
        (is_stale, days_old, severity)
    """
    days = (ref.date() - last_write.date()).days
    if days <= DEFAULT_THRESHOLD_DAYS:
        return False, days, "ok"
    if days > ERROR_THRESHOLD_DAYS:
        return True, days, "error"
    return True, days, "warning"


def check(date_str: str) -> list[dict]:
    """扫描 data/raw/ 所有 parquet, 返回 alert list

    Args:
        date_str: YYYY-MM-DD (今天日期, 用来算 staleness)
    """
    if not DATA_RAW.exists():
        return []

    try:
        ref = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return []

    alerts = []
    for sub_dir in sorted(DATA_RAW.iterdir()):
        if not sub_dir.is_dir():
            continue
        # 跳过隐藏目录 (点开头)
        if sub_dir.name.startswith("."):
            continue
        # 跳过跨项目 cache (paper-agent 等其它项目的目录)
        if sub_dir.name in EXCLUDE_DIRS:
            continue
        for pq in sub_dir.glob("*.parquet"):
            try:
                mtime = datetime.fromtimestamp(pq.stat().st_mtime)
            except OSError:
                continue
            is_stale, days_old, severity = _is_stale(mtime, ref)
            if is_stale:
                msg = f"Last update {days_old} days ago ({mtime.strftime('%Y-%m-%d %H:%M')}), threshold {DEFAULT_THRESHOLD_DAYS} days"
                alerts.append(alert_logger.make_alert(
                    alert_type="stale",
                    subject=f"data/raw/{sub_dir.name}/{pq.name}",
                    message=msg,
                    severity=severity,
                    details={
                        "file": f"data/raw/{sub_dir.name}/{pq.name}",
                        "last_write": mtime.isoformat(timespec="seconds"),
                        "days_old": days_old,
                        "threshold_days": DEFAULT_THRESHOLD_DAYS,
                    },
                ))
    return alerts


__all__ = ["check", "DEFAULT_THRESHOLD_DAYS", "ERROR_THRESHOLD_DAYS"]
