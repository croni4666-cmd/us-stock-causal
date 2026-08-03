"""src/residual_regression.py - 归因残差回归测试 (v0.6.8i P7-5)

设计:
- 捕获当前 4 指数 × 3 窗口 (1d/5d/20d) 残差 → 写 baseline JSON
- 任何 commit 后跑 compare: |current| > tolerance * |baseline| → 回归
- tolerance 默认 1.5 (50% 恶化, 留 buffer 给市场短期波动)

Why P7-5:
- v0.3.0 早期就发现 5d 残差偏大, 但不知道原因 (P6-3 v0.6.7 才诊断)
- v0.6.8e/f sector weights 真修后残差改善 8-54%, 但没有"锁住"的机制
- 未来如果误改 weights.json / 加新 ETF / 改归因公式, 残差会回弹
- 自动化 regression test 防止回弹

注意:
- baseline 是 absolute residual, 不是 % 改善 — 比较直接
- 容忍度 1.5x: 允许市场短期波动导致 50% 残差浮动, 超过则 fail
- 不做相对 % 改善比较: 旧残差 0.001%, 新残差 0.01% 是 10x 但绝对值很小, 不该 fail
"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attribution import attribute_all_indices, SECTOR_TICKERS  # noqa: F401


BASELINE_DIR = PROJECT_ROOT / "data" / "baseline"
DEFAULT_BASELINE = BASELINE_DIR / "residuals_v069.json"
INDICES = ["DIA", "QQQ", "RSP", "QQQE"]
WINDOWS = [1, 5, 20]


def capture_residuals(date: str = None) -> dict:
    """跑 attribute_all_indices 捕获当前 4 指数 × 3 窗口残差

    Returns:
        {
            "as_of": "2026-07-23",
            "sector_weights_version": "v0.6.8f",
            "residuals": {
                "DIA":  {"1": 0.124, "5": -0.548, "20": 0.209},
                "QQQ":  {"1": -0.113, "5": 0.118, "20": 0.903},
                "RSP":  {"1": 0.016, "5": -0.325, "20": 0.111},
                "QQQE": {"1": -0.310, "5": -0.379, "20": 1.472},
            },
            "avg_abs": {"1": 0.141, "5": 0.343, "20": 0.674}
        }
    """
    all_results = attribute_all_indices(date=None, lookback_days=1, symbols=INDICES)
    # All windows in one call? attribute_all_indices takes one lookback at a time
    # So we need 3 calls (1d, 5d, 20d)
    residuals = {idx: {} for idx in INDICES}
    for lb in WINDOWS:
        results = attribute_all_indices(date=None, lookback_days=lb, symbols=INDICES)
        for r in results:
            residuals[r["index"]][str(lb)] = round(r["residual_pct"], 4)

    # avg abs per window
    avg_abs = {}
    for lb in WINDOWS:
        lb_str = str(lb)
        abs_residuals = [abs(residuals[idx][lb_str]) for idx in INDICES]
        avg_abs[lb_str] = round(sum(abs_residuals) / len(abs_residuals), 4)

    return {
        "as_of": date or datetime.now().strftime("%Y-%m-%d"),
        "sector_weights_version": "v0.6.8f",  # update when baseline re-captured
        "indices": INDICES,
        "windows": WINDOWS,
        "residuals": residuals,
        "avg_abs": avg_abs,
    }


def save_baseline(snapshot: dict, path: Path = None) -> Path:
    """写 baseline JSON"""
    if path is None:
        path = DEFAULT_BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    return path


def load_baseline(path: Path = None) -> dict:
    """读 baseline JSON"""
    if path is None:
        path = DEFAULT_BASELINE
    if not path.exists():
        raise FileNotFoundError(
            f"baseline {path} 不存在, 先跑 `python -m src.residual_regression capture` 捕获"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compare_to_baseline(
    current: dict,
    baseline: dict,
    tolerance: float = 1.5,
    abs_floor: float = 0.05,
) -> tuple[bool, list[dict]]:
    """比较 current vs baseline

    tolerance: 1.5 = 允许 50% 残差恶化, 超过则 fail
    abs_floor: 0.05 = baseline < 0.05% 时, 任何 current > 0.10% 算 fail
              (避免 baseline 极小时分母过小放大效应)

    Returns:
        (pass: bool, violations: list[dict>])
    """
    violations = []
    for idx in INDICES:
        if idx not in baseline["residuals"] or idx not in current["residuals"]:
            continue
        for lb_str in [str(w) for w in WINDOWS]:
            base_val = abs(baseline["residuals"][idx].get(lb_str, 0))
            cur_val = abs(current["residuals"][idx].get(lb_str, 0))
            # 容忍: 当前 ≤ max(tolerance * baseline, abs_floor)
            threshold = max(tolerance * base_val, abs_floor)
            if cur_val > threshold:
                violations.append({
                    "index": idx,
                    "window": f"{lb_str}d",
                    "baseline_pct": round(base_val, 4),
                    "current_pct": round(cur_val, 4),
                    "threshold_pct": round(threshold, 4),
                    "regression_ratio": round(cur_val / base_val, 2) if base_val > 0 else "inf",
                })
    return (len(violations) == 0, violations)


def render_comparison(current: dict, baseline: dict, tolerance: float = 1.5) -> str:
    """渲染 markdown 对比表 (终端 / HTML 友好)"""
    lines = [
        f"# 残差回归对比 ({current['as_of']} vs baseline {baseline.get('as_of', '?')})",
        f"",
        f"Tolerance: {tolerance}x (允许 50% 恶化)",
        f"Sector weights: {current.get('sector_weights_version', '?')}",
        f"",
        f"| 指数 | 窗口 | baseline | current | 阈值 | 比值 | 状态 |",
        f"|------|------|---------:|--------:|-----:|-----:|:----:|",
    ]
    pass_count = 0
    fail_count = 0
    for idx in INDICES:
        for lb_str in [str(w) for w in WINDOWS]:
            base_val = baseline["residuals"][idx].get(lb_str, 0)
            cur_val = current["residuals"][idx].get(lb_str, 0)
            base_abs = abs(base_val)
            cur_abs = abs(cur_val)
            threshold = max(tolerance * base_abs, 0.05)
            ratio = cur_abs / base_abs if base_abs > 0 else float('inf')
            status = "[OK]" if cur_abs <= threshold else "[FAIL]"
            if cur_abs <= threshold:
                pass_count += 1
            else:
                fail_count += 1
            ratio_str = f"{ratio:.2f}x" if base_abs > 0 else "inf"
            lines.append(
                f"| {idx} | {lb_str}d | {base_val:+.3f}% | {cur_val:+.3f}% | "
                f"±{threshold:.3f}% | {ratio_str} | {status} |"
            )
    lines.append(f"| | | | | | |")
    lines.append(f"| **合计** | | | | | | {pass_count} pass / {fail_count} fail |")
    return "\n".join(lines)


def main():
    """CLI: capture / compare"""
    import argparse
    parser = argparse.ArgumentParser(description="Residual regression test (P7-5)")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    cap = subparsers.add_parser("capture", help="捕获当前残差作 baseline")
    cap.add_argument("--output", type=Path, default=None, help="输出 JSON 路径")

    cmp_ = subparsers.add_parser("compare", help="比较当前 vs baseline")
    cmp_.add_argument("--baseline", type=Path, default=None, help="baseline JSON 路径")
    cmp_.add_argument("--tolerance", type=float, default=1.5, help="容忍倍数 (默认 1.5)")

    args = parser.parse_args()

    if args.cmd == "capture":
        snapshot = capture_residuals()
        path = save_baseline(snapshot, args.output)
        print(f"[residual] baseline 写入: {path}")
        print(f"[residual] as_of: {snapshot['as_of']}")
        print(f"[residual] avg abs: {snapshot['avg_abs']}")
    elif args.cmd == "compare":
        baseline = load_baseline(args.baseline)
        current = capture_residuals()
        ok, violations = compare_to_baseline(current, baseline, args.tolerance)
        print(render_comparison(current, baseline, args.tolerance))
        print()
        if ok:
            print(f"[residual] [PASS] 全部通过 (tolerance {args.tolerance}x)")
            return 0
        else:
            print(f"[residual] [FAIL] {len(violations)} 处 regression:")
            for v in violations:
                print(f"  - {v['index']} {v['window']}: "
                      f"baseline {v['baseline_pct']:+.3f}% → current {v['current_pct']:+.3f}% "
                      f"(ratio {v['regression_ratio']}x)")
            return 1


if __name__ == "__main__":
    sys.exit(main())
