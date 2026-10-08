"""
examples/gold_chart.py - 黄金 (GC=F) 2y K 线图 (单标的深度看图演示, v0.6.2 quality boost)

用途:
  - 测试 commodities_futures layer 的 K 线渲染
  - v0.6.0 (P6-6) 5 SMA 全套 + 200 SMA 红色
  - v0.6.1 fix: SMA 是真滑动平均 (ax.plot), 不是 hlines
  - v0.6.2 quality: PNG@300dpi + SVG (矢量) + anti-aliasing

设计:
  - figsize 16x8 (大图清晰)
  - lookback 500 (2y) 让 SMA200 滑动平均有足够数据
  - 双输出: PNG (高 DPI 兼容) + SVG (矢量清晰)
  - 5 SMA 全显示 + R1/S1 (kline._draw_thresholds 自动画)
  - 200 SMA 红色粗实线 (核心)
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

# 把项目根加进 path, 避免 import src 子包找不到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.kline import plot_single, savefig_multi_format, DEFAULT_DPI
from src.thresholds import get_thresholds, load_prices


def main() -> None:
    symbol = "GC=F"
    layer = "commodities_futures"
    lookback_days = 500  # 2y (SMA200 滑动平均需要数据)

    # 单图
    fig, ax = plt.subplots(1, 1, figsize=(16, 8))
    plot_single(symbol, ax, layer=layer, lookback_days=lookback_days)

    # Preserve the single instrument title and dedicated latest-close marker.
    t = get_thresholds(symbol, layer=layer)
    prices=load_prices(symbol,layer)
    as_of=str(prices.index[-1].date())
    smas=t['smas']

    # 写到项目根 output/ (不是 CWD),避免被 workspace 截走
    project_root = Path(__file__).resolve().parent.parent
    output_base = project_root / "output" / f"gold_2y_{as_of}"
    written = savefig_multi_format(
        fig, output_base,
        formats=("png", "svg"),  # 双输出
        png_dpi=DEFAULT_DPI,     # 300 dpi (v0.6.2 quality boost)
    )
    plt.close(fig)
    print(f"[gold_chart] saved {len(written)} formats:")
    for p in written:
        print(f"  - {p}")
    print(f"[gold_chart] last close: USD {t['last_close']:.2f}")
    print(f"[gold_chart] data as of: {as_of}; last futures close, not a live spot quote")
    print(f"[gold_chart] SMAs: {smas}")


if __name__ == "__main__":
    main()
