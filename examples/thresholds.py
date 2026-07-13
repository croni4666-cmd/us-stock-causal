"""
examples/thresholds.py - 关键阈值 + 残差分析 (Phase 2.1)

输出:
  - 控制台: 4 指数当前水平 + SMA + Pivot + 52w range
  - 控制台: 残差统计 (mean / std / t-test / anomalies)
  - output/thresholds_<date>.md: 完整报告
  - output/thresholds_<date>.png: 4 指数 (价格 + SMA + pivot) 图

跑: python examples/thresholds.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from loguru import logger

from src import proxy  # noqa: F401
from src.thresholds import get_thresholds, load_prices
from src.residual import compute_residual_timeseries, assess_weight_health, detect_anomalies


def render_thresholds_table(results: list[dict]) -> str:
    """4 指数当前水平表"""
    lines = ["## 4 指数当前水平\n"]
    lines.append("| 指数 | 现价 | SMA20 | SMA50 | SMA200 | 200 SMA 位置 | Pivot | R1 | S1 | 52w Pos |")
    lines.append("|------|------|-------|-------|--------|-------------|-------|-----|-----|---------|")
    for t in results:
        s200 = t["smas"]["sma_200"]
        vs200 = t["vs_sma"]["sma_200"]
        pos_marker = "🟢" if vs200["above"] else "🔴"
        lines.append(
            f"| {t['symbol']} | ${t['last_close']} | ${t['smas']['sma_20']} | "
            f"${t['smas']['sma_50']} | ${s200} | {pos_marker} {vs200['pct']:+.2f}% | "
            f"${t['pivots']['pivot']} | ${t['pivots']['r1']} | ${t['pivots']['s1']} | "
            f"{t['range_52w']['position_pct']}% |"
        )
    return "\n".join(lines)


def render_residual_table(health: dict, anomalies: pd.DataFrame, idx: str) -> str:
    """单个指数的残差统计"""
    lines = [f"\n### {idx} 残差分析 (60d)\n"]
    h = health[idx]
    lines.append(f"- **mean residual**: {h['mean_residual_pct']:+.4f}% (t-test p={h['p_value']}, {h['t_stat']})")
    lines.append(f"- **std residual**: {h['std_residual_pct']:.3f}%")
    lines.append(f"- **健康度**: {h['health']} — {h['advice']}")
    if len(anomalies[idx]) > 0:
        lines.append(f"- **异常日** (|z| > 2σ, 共 {len(anomalies[idx])} 天):")
        for _, a in anomalies[idx].head(5).iterrows():
            lines.append(
                f"  - {a['date']}: actual {a['actual_pct']:+.2f}% / "
                f"predicted {a['predicted_pct']:+.2f}% / "
                f"residual {a['residual_pct']:+.2f}% (z={a['z_score']:+.2f})"
            )
    return "\n".join(lines)


def render_price_chart(results: list[dict], path: Path, lookback_days: int = 252) -> None:
    """4 subplot: 1y 收盘价 + SMA20/50/200 + pivot levels"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    axes = axes.flatten()

    for ax, t in zip(axes, results):
        df = load_prices(t["symbol"], "indices")
        recent = df.iloc[-lookback_days:]

        ax.plot(recent.index, recent["close"], color="black", linewidth=1.0, label="close")
        ax.plot(recent.index, recent["close"].rolling(20).mean(), color="blue", linewidth=0.7, alpha=0.7, label="SMA20")
        ax.plot(recent.index, recent["close"].rolling(50).mean(), color="orange", linewidth=0.7, alpha=0.7, label="SMA50")
        ax.plot(recent.index, recent["close"].rolling(200).mean(), color="red", linewidth=0.7, alpha=0.7, label="SMA200")

        # Pivot levels
        pivots = t["pivots"]
        ax.axhline(pivots["pivot"], color="gray", linestyle="--", linewidth=0.6, alpha=0.6)
        ax.axhline(pivots["r1"], color="green", linestyle=":", linewidth=0.6, alpha=0.6, label="R1")
        ax.axhline(pivots["s1"], color="red", linestyle=":", linewidth=0.6, alpha=0.6, label="S1")
        ax.axhline(pivots["r2"], color="green", linestyle=":", linewidth=0.4, alpha=0.4)
        ax.axhline(pivots["s2"], color="red", linestyle=":", linewidth=0.4, alpha=0.4)

        ax.set_title(f"{t['symbol']} - {t['date']} (close ${t['last_close']}, 200SMA {t['vs_sma']['sma_200']['pct']:+.2f}%)",
                     fontsize=10, fontweight="bold")
        ax.set_ylabel("Price")
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.suptitle(f"us-stock-causal v0.3.1 - Key Thresholds (1y chart, {results[0]['date']})",
                 fontsize=12, fontweight="bold", y=1.00)
    plt.tight_layout()
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.3.1 - thresholds + residual (Phase 2.1)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    t0 = time.time()

    # 1. 关键阈值
    print("\n[1/2] 4 指数关键阈值...")
    thresholds = [get_thresholds(idx) for idx in ["DIA", "QQQ", "RSP", "QQQE"]]
    print(render_thresholds_table(thresholds))

    # 2. 残差分析
    print("\n[2/2] 残差分析 (60 天)...")
    health = {}
    anomalies = {}
    for idx in ["DIA", "QQQ", "RSP", "QQQE"]:
        ts = compute_residual_timeseries(idx, lookback_days=60)
        health[idx] = assess_weight_health(ts)
        anomalies[idx] = detect_anomalies(ts, threshold_std=2.0)
        print(render_residual_table(health, anomalies, idx))

    # 3. 输出文件
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    today = thresholds[0]["date"]

    md_path = output_dir / f"thresholds_{today}.md"
    md_lines = [
        f"# Thresholds + Residual Report - {today}",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n**Model**: sector weights + SMA + pivot + 52w range + residual t-test",
        "\n---",
        render_thresholds_table(thresholds),
    ]
    for idx in ["DIA", "QQQ", "RSP", "QQQE"]:
        md_lines.append(render_residual_table(health, anomalies, idx))
        md_lines.append("\n---\n")
    md_lines.append(f"\n*Chart: see `output/thresholds_{today}.png`*\n")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    chart_path = output_dir / f"thresholds_{today}.png"
    render_price_chart(thresholds, chart_path)

    elapsed = time.time() - t0
    print(f"\n{'=' * 72}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  Report: {md_path}")
    print(f"  Chart:  {chart_path}")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
