"""src/checks/residual.py - P8-2 残差回归 daily check (P7-5 reuse)

跟 v0.6.8i P7-5 一样用 capture_residuals + compare_to_baseline,
但 daily run 也会跑 (不只 test), 异常 → alert

threshold: tolerance=1.5x, abs_floor=0.05% (跟 P7-5 一致)
"""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import alert_logger
from src.residual_regression import capture_residuals, load_baseline, compare_to_baseline


def check(date_str: str) -> list[dict]:
    """跑当日残差回归, 跟 baseline 比对, 超过 tolerance → alert"""
    alerts = []
    try:
        current = capture_residuals(date_str)
    except Exception as e:
        # 残差捕获本身 fail → 1 个 error alert
        return [alert_logger.make_alert(
            alert_type="residual",
            subject="capture_residuals()",
            message=f"无法捕获残差: {e}",
            severity="error",
            details={"error": str(e)},
        )]

    try:
        baseline = load_baseline()
    except Exception as e:
        return [alert_logger.make_alert(
            alert_type="residual",
            subject="load_baseline()",
            message=f"无法读 baseline: {e}",
            severity="error",
            details={"error": str(e)},
        )]

    # compare_to_baseline 返 (ok: bool, violations: list)
    _, violations = compare_to_baseline(current, baseline)
    for v in violations:
        idx = v.get("index", "?")
        win = v.get("window", "?")
        # v0.9.5 RC1 prep: 字段名错 (R12 audit 修), compare_to_baseline 返
        # `current_pct` / `baseline_pct` / `regression_ratio`, 不是 `current` / `baseline` / `ratio`
        # 8/13-8/18 持续 6 天 alert 误报 (fallback 0.0/0.0/1.0 字段值)
        cur = v.get("current_pct", v.get("current", 0.0))
        bsl = v.get("baseline_pct", v.get("baseline", 0.0))
        ratio = v.get("regression_ratio", v.get("ratio", 1.0))
        # ratio="inf" (baseline=0 时) → 字符串, f-string format 会 crash, 转 "inf"
        ratio_str = f"{ratio:.2f}" if isinstance(ratio, (int, float)) else str(ratio)
        msg = f"{idx} {win}d: baseline {bsl:+.3f}% → current {cur:+.3f}% (ratio {ratio_str}x, >1.5x threshold)"
        alerts.append(alert_logger.make_alert(
            alert_type="residual",
            subject=f"{idx}/{win}d",
            message=msg,
            severity="warning",
            details={
                "index": idx,
                "window_days": win,
                "baseline_pct": bsl,
                "current_pct": cur,
                "regression_ratio": ratio,
            },
        ))
    return alerts


__all__ = ["check"]
