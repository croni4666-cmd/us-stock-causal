"""
examples/gold_chart.py - 黄金 (GC=F) 1y K 线图 (单标的深度看图演示)

用途:
  - 测试 commodities_futures layer 的 K 线渲染
  - v0.6.0 (P6-6) 5 SMA 全套 + 200 SMA 红色 + 高清晰度 (DPI 200)
  - user 黄金深度分析

设计:
  - figsize 16x8 (大图清晰)
  - DPI 200 (高清晰度)
  - 5 SMA 全显示 + R1/S1 (kline._draw_thresholds 自动画)
  - 200 SMA 红色粗实线 (核心,user 强调醒目)
  - 标题显示全部 5 个 SMA 的 vs SMA%
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# 把项目根加进 path, 避免 import src.xxx 找不到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.kline import plot_single
from src.thresholds import get_thresholds


def main() -> None:
    symbol = "GC=F"
    layer = "commodities_futures"
    lookback_days = 252  # ~1y 交易日

    # 单图 — 16x8 + DPI 200 (v0.6.0 清晰度提升)
    fig, ax = plt.subplots(1, 1, figsize=(16, 8))
    plot_single(symbol, ax, layer=layer, lookback_days=lookback_days)

    # 标题 — 5 SMA 全显示
    t = get_thresholds(symbol, layer=layer)
    smas = t["smas"]
    vs = t["vs_sma"]
    pos52w = t["range_52w"]["position_pct"]
    parts = [f"close USD {t['last_close']:.2f}"]
    for w in [20, 50, 100, 150, 200]:
        v = smas.get(f"sma_{w}")
        p = vs.get(f"sma_{w}", {}).get("pct")
        if v is not None and p is not None and not pd.isna(v):
            parts.append(f"SMA{w} {p:+.1f}%")
    parts.append(f"52w {pos52w}%")
    title = f"{symbol}  1y  |  " + "  ".join(parts)
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left", pad=10)

    # 写到项目根 output/ (不是 CWD),避免被 workspace 截走
    project_root = Path(__file__).resolve().parent.parent
    output_path = project_root / "output" / "gold_1y_2026-07-13.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[gold_chart] saved: {output_path}")
    print(f"[gold_chart] last close: USD {t['last_close']:.2f}")
    print(f"[gold_chart] 52w range: {t['range_52w']['low']:.2f} - {t['range_52w']['high']:.2f}  (now at {pos52w}%)")
    print(f"[gold_chart] SMAs: {smas}")


if __name__ == "__main__":
    main()
