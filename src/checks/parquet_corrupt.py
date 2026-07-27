"""src/checks/parquet_corrupt.py - P8-5 parquet 完整性检测

扫 data/raw/*/ 所有 parquet, 用 pandas 读:
- 读失败 (IOError / pyarrow.lib.ArrowInvalid) → error alert
- 读成功但 0 行 → warning alert (空 parquet 通常是 fetch 失败)
"""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import alert_logger

DATA_RAW = PROJECT_ROOT / "data" / "raw"


def check(date_str: str) -> list[dict]:
    """扫 data/raw/*/ 所有 parquet, 检测 corrupt / empty"""
    alerts = []
    if not DATA_RAW.exists():
        return alerts

    try:
        import pandas as pd
    except ImportError:
        return [alert_logger.make_alert(
            alert_type="parquet_corrupt",
            subject="pandas import",
            message="pandas 没装, 跳过 corrupt check",
            severity="error",
            details={"hint": "pip install pandas pyarrow"},
        )]

    for sub_dir in sorted(DATA_RAW.iterdir()):
        if not sub_dir.is_dir() or sub_dir.name.startswith("."):
            continue
        for pq in sub_dir.glob("*.parquet"):
            try:
                df = pd.read_parquet(pq)
            except Exception as e:
                alerts.append(alert_logger.make_alert(
                    alert_type="parquet_corrupt",
                    subject=f"data/raw/{sub_dir.name}/{pq.name}",
                    message=f"Parquet 读失败: {type(e).__name__}: {e}",
                    severity="error",
                    details={
                        "file": f"data/raw/{sub_dir.name}/{pq.name}",
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                ))
                continue
            if len(df) == 0:
                alerts.append(alert_logger.make_alert(
                    alert_type="parquet_corrupt",
                    subject=f"data/raw/{sub_dir.name}/{pq.name}",
                    message="Parquet 0 行 (空文件, fetch 可能失败)",
                    severity="warning",
                    details={
                        "file": f"data/raw/{sub_dir.name}/{pq.name}",
                        "rows": 0,
                    },
                ))
    return alerts


__all__ = ["check"]
